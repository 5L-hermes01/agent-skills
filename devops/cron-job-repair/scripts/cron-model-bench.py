#!/usr/bin/env python3
"""cron-model-bench.py — run real cron jobs under alternate models and record
wall-clock time, token usage and the produced output.

For each (job, arm) it:
  1. snapshots the job's model/provider/deliver settings from cron/jobs.json
  2. applies the arm with `hermes cron edit` and forces delivery to `local`
     (so a benchmark never posts to Signal/Discord)
  3. force-fires the job with `hermes cron run` and waits for its audit row
  4. records duration_ms, prompt/completion tokens, error, silence flag and the
     output artifact
  5. restores the original job definition

Usage:
  cron-model-bench.py --jobs b8adeca9096f,e92568122077 [--arms default,qwen,inkling]
                      [--timeout-min 30] [--out /opt/data/cache/cron-model-bench/results.jsonl]
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

HOME = Path("/opt/data")
JOBS = HOME / "cron/jobs.json"
AUDIT = HOME / "cron/usage_audit.jsonl"
OUTPUT_DIR = HOME / "cron/output"
HERMES = "hermes"

ARMS: dict[str, dict[str, list[str]]] = {
    # unpinned → the config default (model.default / model.provider in config.yaml)
    "default": {"edit": ["--unpin", "--provider", "nous"]},
    # local inference box, big qwen
    "qwen": {"edit": ["--model", "qwen3.8-27b-instruct", "--provider", "ollama-qwen3.6:27b", "--pin"]},
    # local inference box, small inkling
    "inkling": {"edit": ["--model", "inkling-mini", "--provider", "ollama-qwen3.6:27b", "--pin"]},
    # cheaper hosted candidates (prices are USD per million tokens, from the live
    # /v1/models pricing block; ":batch" variants bill at a discount)
    "v41batch": {"edit": ["--model", "deepseek/deepseek-v4.1-flash:batch", "--provider", "nous", "--pin"]},
    "qwen37f": {"edit": ["--model", "qwen/qwen3.7-flash", "--provider", "nous", "--pin"]},
    "glmflash": {"edit": ["--model", "~z-ai/glm-flash-latest", "--provider", "nous", "--pin"]},
    "oss120b": {"edit": ["--model", "openai/gpt-oss-120b:batch", "--provider", "nous", "--pin"]},
    "hy4flash": {"edit": ["--model", "tencent/hy4-flash", "--provider", "nous", "--pin"]},
}


def run(cmd: list[str], timeout: int = 600) -> tuple[int, str]:
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    return p.returncode, (p.stdout + p.stderr).strip()


def load_job(job_id: str) -> dict:
    data = json.loads(JOBS.read_text())
    for j in data["jobs"]:
        if j["id"] == job_id:
            return j
    raise SystemExit(f"job {job_id} not found")


def audit_rows() -> list[dict]:
    rows = []
    for line in AUDIT.read_text().splitlines():
        line = line.strip()
        if line:
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return rows


def wait_for_audit(job_id: str, after_ts: str, timeout_s: int) -> dict | None:
    """Poll for an audit row for this job newer than after_ts (ISO string compare)."""
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        for row in reversed(audit_rows()):
            if row.get("job_id") == job_id and str(row.get("ts", "")) > after_ts:
                return row
        time.sleep(10)
    return None


def newest_output(job_id: str, after: float) -> str | None:
    d = OUTPUT_DIR / job_id
    files: list[Path] = []
    if d.is_dir():
        files = [p for p in d.rglob("*") if p.is_file() and p.stat().st_mtime >= after]
    files += [p for p in OUTPUT_DIR.glob(f"{job_id}_*") if p.is_file() and p.stat().st_mtime >= after]
    if not files:
        return None
    newest = max(files, key=lambda p: p.stat().st_mtime)
    return str(newest)


def snapshot(job: dict) -> dict:
    return {k: job.get(k) for k in ("model", "provider", "deliver", "failure_deliver", "model_snapshot", "provider_snapshot")}


def apply_restore(job_id: str, snap: dict) -> list[str]:
    cmd = [HERMES, "cron", "edit", job_id, "--deliver", snap.get("deliver") or "local"]
    fd = snap.get("failure_deliver")
    cmd += ["--failure-deliver", fd if fd else ""]
    if snap.get("model"):
        cmd += ["--model", snap["model"], "--pin"]
    else:
        cmd += ["--unpin"]
    if snap.get("provider"):
        cmd += ["--provider", snap["provider"]]
    return cmd


def bench_one(job_id: str, arm: str, timeout_min: int, out_path: Path) -> dict:
    job = load_job(job_id)
    snap = snapshot(job)
    name = job.get("name")
    started_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    started = time.time()
    rec: dict = {
        "job_id": job_id, "job": name, "arm": arm, "schedule": job.get("schedule_display"),
        "started": started_iso, "restored": False,
    }
    try:
        # 1. apply the arm, suppress delivery to real channels
        rc, out = run([HERMES, "cron", "edit", job_id, *ARMS[arm]["edit"], "--deliver", "local",
                       "--failure-deliver", "local"], timeout=120)
        rec["edit_rc"] = rc
        if rc != 0:
            rec["error"] = f"cron edit failed: {out[-400:]}"
            return rec
        time.sleep(2)
        # 2. force-fire ('Triggered job' can return non-zero — the audit row is the truth)
        rc, out = run([HERMES, "cron", "run", job_id])
        rec["run_rc"] = rc
        rec["run_out"] = out[-200:]
        # 3. wait for the audit row (scheduler tick + model latency + model load)
        row = wait_for_audit(job_id, started_iso, timeout_min * 60)
        if row is None:
            # give a straggler a little longer before cancelling
            row = wait_for_audit(job_id, started_iso, 180)
        if row is None:
            run([HERMES, "cron", "cancel", job_id], timeout=60)
            rec["error"] = f"no audit row within {timeout_min} min (cancelled)"
            return rec
        rec.update({
            "duration_ms": row.get("duration_ms"),
            "prompt_tokens": row.get("prompt_tokens"),
            "completion_tokens": row.get("completion_tokens"),
            "total_tokens": row.get("total_tokens"),
            "silent": row.get("response_silent"),
            "model_used": row.get("model"),
            "error": row.get("error"),
            "audit_ts": row.get("ts"),
        })
        rec["output"] = newest_output(job_id, started)
        if rec.get("output"):
            body = Path(str(rec["output"])).read_text(errors="ignore")
            rec["output_chars"] = len(body)
            rec["output_head"] = body[:600]
    except subprocess.TimeoutExpired:
        rec["error"] = "bench step timed out"
    finally:
        rc, out = run(apply_restore(job_id, snap), timeout=120)
        rec["restore_rc"] = rc
        rec["restored"] = rc == 0
        if rc != 0:
            rec["restore_error"] = out[-300:]
        rec["wall_s"] = round(time.time() - started, 1)
        with out_path.open("a") as fh:
            fh.write(json.dumps(rec, default=str) + "\n")
    return rec


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--jobs", required=True, help="comma-separated job ids")
    ap.add_argument("--arms", default="default,qwen,inkling")
    ap.add_argument("--timeout-min", type=int, default=30, help="per-run wait limit")
    ap.add_argument("--out", default="/opt/data/cache/cron-model-bench/results.jsonl")
    args = ap.parse_args()
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    jobs = [j.strip() for j in args.jobs.split(",") if j.strip()]
    arms = [a.strip() for a in args.arms.split(",") if a.strip()]
    done: set[tuple[str, str]] = set()
    if out_path.exists():  # resume: never re-run a (job, arm) pair already captured
        for line in out_path.read_text().splitlines():
            try:
                r = json.loads(line)
                done.add((r.get("job_id"), r.get("arm")))
            except json.JSONDecodeError:
                pass
    for jid in jobs:
        for arm in arms:
            if (jid, arm) in done:
                print(f"skip {jid} {arm} (already captured)", flush=True)
                continue
            rec = bench_one(jid, arm, args.timeout_min, out_path)
            status = rec.get("error") or "ok"
            print(f"[{datetime.now().strftime('%H:%M:%S')}] {rec['job']} arm={arm} "
                  f"{rec.get('duration_ms')}ms tok={rec.get('prompt_tokens')}/{rec.get('completion_tokens')} "
                  f"silent={rec.get('silent')} restored={rec.get('restored')} -> {str(status)[:90]}",
                  flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
