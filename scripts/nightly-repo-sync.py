#!/usr/bin/env python3
"""
Nightly repo sync — agent-memories and agent-skills.

New architecture:
  /opt/data/repos/agent-skills/      # Git repo — tracks ONLY original work
  /opt/data/upstream-hermes-agent/   # Read-only sparse clone (skills/ only)
  /opt/data/skills/                  # Consumption directory — rebuilt nightly

agent-memories: commits everything (no upstream).
agent-skills: rebuilds consumption dir from upstream + originals, then
              commits only new/modified files vs upstream.
"""

import shutil
import subprocess
import json
import os
import sys
import tempfile
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

TODAY = datetime.now(timezone.utc).strftime("%Y-%m-%d")
BRANCH_NAME = f"update/{TODAY}"
GITHUB_USER = "5L-hermes01"


def _load_gh_token():
    """Get GitHub token via `gh auth token` — always current, properly scoped."""
    # Ensure gh can find its config (seen in cron where GH_CONFIG_DIR may be unset)
    if "GH_CONFIG_DIR" not in os.environ:
        os.environ.setdefault("GH_CONFIG_DIR", str(Path.home() / ".config" / "gh"))
    result = subprocess.run(
        ["gh", "auth", "token"],
        capture_output=True, text=True, timeout=10,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"gh auth token failed (exit {result.returncode}): "
            f"{result.stderr.strip()}"
        )
    token = result.stdout.strip()
    if not token:
        raise RuntimeError("gh auth token returned empty string")
    return token


PAT = _load_gh_token()


# ── Paths ────────────────────────────────────────────────────────────────────
UPSTREAM_REPO  = Path("/opt/data/upstream-hermes-agent")
UPSTREAM_SKILLS = UPSTREAM_REPO / "skills"
CONSUMPTION    = Path("/opt/data/skills")
SKILLS_REPO    = Path("/opt/data/repos/agent-skills")
MEMORIES_REPO  = Path("/opt/data/repos/agent-memories")
SCRIPTS_DIR    = Path("/opt/data/scripts")

# Files to skip when overlaying agent-skills onto consumption dir
GIT_SKIP = {'.git', '.gitignore', '.github', '.curator_state', '.usage.json',
            '.usage.json.lock', '.curator_backups', 'data'}

# Runtime state dirs that must survive the nightly consumption rebuild
# (they hold gitignored, day-over-day artifacts like car-tracker state).
CONSUMPTION_PRESERVE_DIRS = {'data'}

# Test file patterns to filter out during consumption directory rebuild.
# These are development-only files that should not be deployed to the
# live skills directory used by the agent.
TEST_SKIP_DIRS = {'tests', 'fixtures', '__pycache__', '.pytest_cache'}
TEST_SKIP_NAMES = {'conftest.py', 'pytest.ini', '.coverage'}


def _purge_artifacts():
    """Remove all build artifacts and junk from the consumption dir.
    Covers __pycache__, .pytest_cache, .egg-info, *.pyc,
    runtime cache/ dirs inside skills, .env files, and .jules/."""
    patterns = [
        '__pycache__', '.pytest_cache', '.jules',
    ]
    file_suffixes = ['.pyc', '.egg-info']
    file_names = ['.env']
    # cache/ is trickier — only purge it under skill dirs, not references/
    # We handle it by checking whether it's an immediate child of a skill
    # (i.e., media/ft-reader/cache/) vs a reference directory.

    removed_total = 0
    for root, dirs, files in os.walk(str(CONSUMPTION)):
        # Purge matching directories
        for d in list(dirs):
            full = Path(root) / d
            if d in patterns:
                pcount = sum(1 for _ in full.rglob("*") if _.is_file())
                shutil.rmtree(full)
                removed_total += pcount
                dirs.remove(d)
            # Purge cache/ dirs that are inside skill dirs (not references/)
            elif d == 'cache' and 'references' not in root.split(os.sep):
                pcount = sum(1 for _ in full.rglob("*") if _.is_file())
                shutil.rmtree(full)
                removed_total += pcount
                dirs.remove(d)

        # Purge matching files
        for f in list(files):
            full = Path(root) / f
            if f in file_names or any(f.endswith(s) for s in file_suffixes):
                full.unlink()
                removed_total += 1

    if removed_total:
        print(f"    Purged {removed_total} build artifact file(s)")


def _is_test_file(name):
    """Return True if name is a test file/dir that should be excluded."""
    if name in TEST_SKIP_DIRS:
        return True
    if name in TEST_SKIP_NAMES:
        return True
    if name.startswith('test_') and name.endswith('.py'):
        return True
    if name.endswith('_test.py'):
        return False


def _force_rmtree(path):
    """Remove a directory tree, handling read-only files/dirs gracefully."""
    for root, dirs, files in os.walk(path):
        for d in dirs:
            os.chmod(os.path.join(root, d), 0o755)
        for f in files:
            os.chmod(os.path.join(root, f), 0o644)
    shutil.rmtree(path)


def ignore_test_files(dir_path, names):
    """shutil.copytree ignore callable — filters test files and dirs."""
    return {n for n in names if _is_test_file(n)}


def run(cmd, cwd=None, check=True):
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=120)
    if check and r.returncode != 0:
        raise RuntimeError(f"Command failed: {' '.join(cmd)}\n{r.stderr}")
    return r.stdout.strip(), r.stderr.strip(), r.returncode


def gh_api(path, method="GET", data=None):
    url = f"https://api.github.com{path}"
    req = urllib.request.Request(url, method=method)
    req.add_header("Authorization", f"token {PAT}")
    req.add_header("Accept", "application/vnd.github+json")
    if data:
        req.add_header("Content-Type", "application/json")
        req.data = json.dumps(data).encode()
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())


# ── Consumption directory rebuild ────────────────────────────────────────────

SYMLINK_MAP = {
    # target under skills/ ->  source in secrets/
    "media/ft-reader/.env":     "/opt/data/secrets/ft-cookie.env",
    "media/wsj-reader/.env":    "/opt/data/secrets/wsj-cookie.env",
}

# Runtime state symlinks: consumption copy -> canonical repo copy.
# Keeps a single source of truth so day-over-day state (car-tracker etc.)
# survives the nightly consumption rebuild without split-brain.
STATE_SYMLINK_MAP = {
    "data/seen_listings.json": "/opt/data/repos/agent-skills/data/seen_listings.json",
}

def _restore_dotenv_symlinks():
    """Recreate .env symlinks that the rebuild purges."""
    for rel_path, source in SYMLINK_MAP.items():
        link = CONSUMPTION / rel_path
        if not link.exists() and not link.is_symlink():
            if Path(source).exists():
                link.parent.mkdir(parents=True, exist_ok=True)
                link.symlink_to(source)
                print(f"    Restored .env symlink: {rel_path} -> {source}")
            else:
                print(f"    WARNING: source {source} missing, cannot restore {rel_path}")

def _restore_state_symlinks():
    """Recreate runtime state symlinks (e.g. car-tracker seen_listings.json)
    that the consumption rebuild would otherwise leave as a stale/divergent copy."""
    for rel_path, source in STATE_SYMLINK_MAP.items():
        link = CONSUMPTION / rel_path
        if link.exists() or link.is_symlink():
            if link.is_symlink():
                continue  # already correct
            # It's a real file (divergent copy) — replace with symlink to canonical
            link.unlink()
        if Path(source).exists():
            link.parent.mkdir(parents=True, exist_ok=True)
            link.symlink_to(source)
            print(f"    Restored state symlink: {rel_path} -> {source}")

# ── Venv dependency installer ────────────────────────────────────────────────

PIP_CMD = "/opt/data/wsj-venv/bin/pip"
READER_PACKAGES = [
    "ft-reader",
    "nyt-reader",
    "wsj-reader",
]


def _install_reader_deps():
    """Install media-reader packages in the wsj-venv so system-Python skills
    can import news_reader_base and the reader CLIs.

    Uses --no-deps to avoid pip resolving broken relative-path dependencies
    (news-reader-base @ file:../news-reader-base) — the shared base is already
    installed in the venv. Only installs packages whose source directory exists
    in the freshly rebuilt consumption dir.
    """
    if not Path(PIP_CMD).exists():
        print("    WARNING: wsj-venv pip not found, skipping reader deps install")
        return

    for name in READER_PACKAGES:
        pkg_dir = CONSUMPTION / "media" / name
        if not pkg_dir.is_dir():
            print(f"    SKIP: {name} — source dir not found at {pkg_dir}")
            continue
        try:
            out, err, rc = run(
                [PIP_CMD, "install", "--no-deps", "-e", str(pkg_dir)],
                check=False,
            )
            if rc == 0:
                print(f"    Installed {name} (editable, --no-deps)")
            else:
                # Collapse multi-line output for the summary
                summary = (out + err)[:300].replace("\n", " | ")
                print(f"    WARNING: {name} install returned {rc}: {summary}")
        except Exception as e:
            print(f"    WARNING: {name} install failed: {e}")


def rebuild_consumption_dir():
    """Rebuild /opt/data/skills/ from upstream + agent-skills originals."""
    print("  Rebuilding consumption directory...")

    # Clear existing content (keep the dir itself, and preserve runtime state dirs)
    for item in CONSUMPTION.iterdir():
        if item.name in CONSUMPTION_PRESERVE_DIRS:
            continue
        if item.is_dir():
            _force_rmtree(item)
        else:
            item.unlink()

    # 1. Copy upstream skills as base (filter out test files)
    for item in UPSTREAM_SKILLS.iterdir():
        dest = CONSUMPTION / item.name
        if item.is_dir():
            shutil.copytree(item, dest, dirs_exist_ok=True,
                            ignore=ignore_test_files)
        else:
            shutil.copy2(item, dest)

    _purge_artifacts()
    up_count = sum(1 for _ in CONSUMPTION.rglob("*") if _.is_file())
    print(f"    Upstream base: {up_count} files")

    # 2. Overlay agent-skills originals on top (our files win, test files filtered)
    for item in SKILLS_REPO.iterdir():
        if item.name in GIT_SKIP:
            continue
        dest = CONSUMPTION / item.name
        if item.is_dir():
            shutil.copytree(item, dest, dirs_exist_ok=True,
                            ignore=ignore_test_files)
        else:
            shutil.copy2(item, dest)

    _purge_artifacts()
    total_count = sum(1 for _ in CONSUMPTION.rglob("*") if _.is_file())
    print(f"    Total after overlay: {total_count} files")

    # 3. Restore .env symlinks that get lost in the rebuild
    _restore_dotenv_symlinks()
    # 3b. Restore runtime state symlinks (single source of truth for state files)
    _restore_state_symlinks()


# ── agent-memories (no upstream, commit everything) ──────────────────────────

def process_memories():
    name = "agent-memories"
    path = str(MEMORIES_REPO)
    print(f"\n{'='*50}\nProcessing: {name}\n{'='*50}")

    run(["git", "fetch", "origin", "main"], cwd=path)
    run(["git", "checkout", "main"], cwd=path)
    run(["git", "pull", "origin", "main"], cwd=path)
    run(["git", "add", "-A"], cwd=path)

    diff_stat, _, _ = run(["git", "diff", "--cached", "--stat"], cwd=path, check=False)
    if not diff_stat:
        print(f"  No changes, skipping.")
        return None

    diff_numstat, _, _ = run(["git", "diff", "--cached", "--numstat"], cwd=path, check=False)
    lines = diff_numstat.strip().split("\n")
    added = sum(int(l.split()[0]) for l in lines if l.split()[0] != "-")
    deleted = sum(int(l.split()[1]) for l in lines if l.split()[1] != "-")
    files_changed = len(lines)

    run(["git", "checkout", "-B", BRANCH_NAME], cwd=path)
    run(["git", "commit", "-m", f"Nightly update {TODAY}\n\n{files_changed} files, +{added}/-{deleted}"], cwd=path)
    run(["git", "push", "origin", BRANCH_NAME, "--force"], cwd=path)

    pr = open_pr(f"{GITHUB_USER}/{name}", BRANCH_NAME, TODAY, diff_stat, files_changed, added, deleted)
    run(["git", "checkout", "main"], cwd=path)

    return format_summary(name, files_changed, added, deleted, diff_numstat, pr)


# ── agent-skills (compare against upstream, commit only originals) ───────────

def process_skills():
    name = "agent-skills"
    path = str(SKILLS_REPO)
    print(f"\n{'='*50}\nProcessing: {name}\n{'='*50}")

    # Step 1: Rebuild consumption directory from upstream + originals
    try:
        rebuild_consumption_dir()
        _install_reader_deps()
    except Exception as e:
        print(f"  WARNING: consumption rebuild failed: {e}")
        print(f"  Continuing with existing /opt/data/skills/ content...")

    # Step 2: Fetch latest upstream (sparse, skills/ only)
    run(["git", "fetch", "--depth", "1", "origin", "main"], cwd=str(UPSTREAM_REPO))
    run(["git", "checkout", "origin/main"], cwd=str(UPSTREAM_REPO))

    # Step 3: Fetch/pull our repo with clean working tree
    run(["git", "fetch", "origin", "main"], cwd=path)
    run(["git", "checkout", "main"], cwd=path)

    # PRESERVE sync-unsafe state files across the hard reset below.
    # These are untracked runtime artifacts (gitignored) that must survive
    # the nightly wipe — e.g. car-tracker's seen_listings.json. We stash
    # them aside and restore after the reset so downstream cron jobs keep
    # their day-over-day comparison history.
    _PRESERVE_REL = [
        "data/seen_listings.json",
    ]
    _preserved = {}
    for rel in _PRESERVE_REL:
        p = Path(path) / rel
        if p.exists():
            tmp = Path(tempfile.gettempdir()) / f"sync-preserve-{abs(hash(rel))}.json"
            shutil.copy2(p, tmp)
            _preserved[rel] = tmp

    # Reset to origin/main — handles both fast-forward and divergence.
    # Local commits are discarded because the repo tracks ONLY original
    # work (cron jobs commit to feature branches). Review local-branch
    # PRs for anything worth keeping before they're swept.
    run(["git", "reset", "--hard", "origin/main"], cwd=path)

    # Restore preserved state files.
    for rel, tmp in _preserved.items():
        dest = Path(path) / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(tmp, dest)
        tmp.unlink(missing_ok=True)
        print(f"  Restored preserved state: {rel}")

    # Step 4: Build upstream file map: relative path -> content bytes
    upstream_map = {}
    for root, dirs, files in os.walk(str(UPSTREAM_SKILLS)):
        dirs[:] = [d for d in dirs if not d.startswith('.')]
        for f in files:
            full = os.path.join(root, f)
            rel = os.path.relpath(full, str(UPSTREAM_SKILLS))
            upstream_map[rel] = Path(full).read_bytes()

    # Step 5: Compare our repo files against upstream
    repo_path = path  # /opt/data/repos/agent-skills/
    new_files = []
    modified_files = []

    for root, dirs, files in os.walk(repo_path):
        dirs[:] = [d for d in dirs if not d.startswith('.') and d != '.git']
        for f in files:
            full = os.path.join(root, f)
            rel = os.path.relpath(full, repo_path)

            # Skip repo-level infrastructure
            if rel.startswith(('.github/', '.git')) or rel in ('.gitignore', '.bundled_manifest',
                '.curator_state', '.usage.json', '.usage.json.lock'):
                continue

            our_content = Path(full).read_bytes()

            if rel not in upstream_map:
                new_files.append(rel)
            elif our_content != upstream_map[rel]:
                modified_files.append(rel)

    if not new_files and not modified_files:
        print(f"  No local changes vs upstream, skipping.")
        return None

    # Drop gitignored paths (runtime state, build artifacts, caches) BEFORE
    # staging or reporting — otherwise egg-info/pycache/state files appear in
    # the nightly message even though the PR itself is already filtered.
    candidates = new_files + modified_files
    if candidates:
        proc = subprocess.run(
            ["git", "-C", path, "check-ignore", "-z", "--stdin"],
            input=("\0".join(candidates) + "\0").encode(),
            capture_output=True,
        )
        ignored = set(proc.stdout.decode(errors="replace").split("\0"))
        ignored.discard("")
        if ignored:
            new_files = [f for f in new_files if f not in ignored]
            modified_files = [f for f in modified_files if f not in ignored]
            print(f"  Excluded {len(ignored)} gitignored path(s) from sync/report")
            if not new_files and not modified_files:
                print("  Nothing left after ignore filter, skipping.")
                return None

    print(f"  New files (custom skills): {len(new_files)}")
    print(f"  Modified vs upstream: {len(modified_files)}")

    def stage_and_pr(branch_name, files_list, pr_title, body_note):
        """Stage files, commit, push, open PR."""
        if not files_list:
            return None, None
        run(["git", "checkout", "main"], cwd=path)
        run(["git", "checkout", "-B", branch_name], cwd=path)
        skipped = 0
        for f in files_list:
            _, _, rc = run(["git", "check-ignore", "-q", f], cwd=path, check=False)
            if rc == 0:
                skipped += 1
                continue
            run(["git", "add", f], cwd=path)
        if skipped:
            print(f"    skipped {skipped} gitignored file(s)")
        diff_stat, _, _ = run(["git", "diff", "--cached", "--stat"], cwd=path, check=False)
        if not diff_stat:
            print(f"  Nothing staged for {branch_name}, skipping.")
            run(["git", "checkout", "main"], cwd=path)
            return branch_name, None
        diff_numstat, _, _ = run(["git", "diff", "--cached", "--numstat"], cwd=path, check=False)
        lines = diff_numstat.strip().split("\n")
        added = sum(int(l.split()[0]) for l in lines if l.split()[0] != "-")
        deleted = sum(int(l.split()[1]) for l in lines if l.split()[1] != "-")
        files_changed = len(lines)
        file_list_str = "\n".join(f"  {x}" for x in files_list)
        run(["git", "commit", "-m", f"{pr_title}\n\n{file_list_str}"], cwd=path)
        run(["git", "push", "origin", branch_name, "--force"], cwd=path)
        pr = open_pr(f"{GITHUB_USER}/{name}", branch_name, TODAY, diff_stat,
                     files_changed, added, deleted,
                     title=pr_title, body_suffix=body_note)
        return branch_name, pr

    summary_parts = []
    pr_links = []

    # Pass 1: upstream sync (files modified vs upstream)
    up_branch = f"update/upstream-{TODAY}"
    _, upstream_pr = stage_and_pr(
        up_branch, modified_files,
        f"Upstream sync {TODAY}",
        "---\nAuto-merged when smoke tests pass."
    )
    if upstream_pr:
        summary_parts.append(f"  Upstream sync ({len(modified_files)} files):")
        for f in modified_files:
            summary_parts.append(f"    ~ {f}")
        pr_links.append(f"  PR (upstream): {upstream_pr}")

    # Pass 2: local customizations (new files, no upstream equivalent)
    local_branch = f"update/local-{TODAY}"
    _, local_pr = stage_and_pr(
        local_branch, new_files,
        f"Local customizations {TODAY}",
        "---\nRequires review — not auto-merged."
    )
    if local_pr:
        summary_parts.append(f"  New custom skills ({len(new_files)}):")
        for f in new_files:
            summary_parts.append(f"    + {f}")
        pr_links.append(f"  PR (local): {local_pr}")

    run(["git", "checkout", "main"], cwd=path)

    summary = [
        f"**{name}** — {len(modified_files)} upstream, {len(new_files)} local",
        "",
    ]
    summary.extend(summary_parts)
    summary.extend(pr_links)
    summary.append("")
    return "\n".join(summary)


def open_pr(repo, branch, date_str, diff_stat, files_changed, added, deleted,
            title=None, body_suffix=""):
    if title is None:
        title = f"Nightly update {date_str}"
    pr_body = f"""## {title}

**{files_changed} files changed**, +{added} / -{deleted}

### Changes
```{diff_stat}```

{body_suffix}"""
    try:
        pr = gh_api(f"/repos/{repo}/pulls", method="POST", data={
            "title": title,
            "body": pr_body,
            "head": branch,
            "base": "main",
        })
        print(f"  PR: #{pr['number']} — {pr['html_url']}")
        return pr["html_url"]
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        if "A pull request already exists" in body:
            existing = gh_api(f"/repos/{repo}/pulls?head={GITHUB_USER}:{branch}&state=open")
            if existing:
                print(f"  PR already exists: {existing[0]['html_url']}")
                return existing[0]["html_url"]
        print(f"  PR error: {body[:200]}")
        return f"https://github.com/{repo}/pulls"


def format_summary(name, files_changed, added, deleted, diff_numstat, pr_url):
    summary = [
        f"**{name}** — {files_changed} files, +{added}/-{deleted}",
        "",
    ]
    for line in diff_numstat.strip().split("\n"):
        parts = line.split("\t")
        if len(parts) >= 3:
            summary.append(f"  {parts[2]} (+{parts[0]}/-{parts[1]})")
    summary.append(f"  PR: {pr_url}")
    summary.append("")
    return "\n".join(summary)


# ── PR Review Check ──────────────────────────────────────────────────────────
#
# After the sync, check open PRs for reviewer feedback. Writes findings to
# a well-known path so the follow-up nightly-pr-review agent job can act on it.

PR_REVIEW_FILE = os.path.expanduser("~/.hermes/cron/pr-reviews-needed.json")

def check_open_prs():
    """Scan open PRs for reviewer feedback needing action.

    Returns a dict with findings (or empty dict if none). Also writes
    PR_REVIEW_FILE for the downstream agent job to pick up.
    """
    repos = [
        f"{GITHUB_USER}/agent-skills",
        f"{GITHUB_USER}/agent-memories",
    ]
    findings = {}

    for repo in repos:
        try:
            prs = gh_api(f"/repos/{repo}/pulls?state=open&per_page=20")
        except Exception as e:
            print(f"  [PR check] {repo}: could not list PRs — {e}")
            continue

        for pr in prs:
            num = pr["number"]
            title = pr["title"]
            branch = pr["head"]["ref"]
            pr_url = pr["html_url"]

            try:
                reviews = gh_api(f"/repos/{repo}/pulls/{num}/reviews")
            except Exception:
                reviews = []

            # Reviews that signal work needed
            actionable = [r for r in reviews
                          if r.get("state") in ("CHANGES_REQUESTED", "COMMENTED")]

            if not actionable:
                continue

            entry = {
                "repo": repo,
                "number": num,
                "title": title,
                "branch": branch,
                "url": pr_url,
                "reviews": [
                    {
                        "user": r.get("user", {}).get("login", "?"),
                        "state": r.get("state"),
                        "body": (r.get("body") or "")[:2000],
                    }
                    for r in actionable
                ],
            }
            # Check if any feedback touches security boundaries
            sec_keywords = [
                "credential", "password", "secret", "token", "api.key",
                "ssh", "auth", "permission", "acl", "rbac", "encrypt",
                "firewall", "sandbox", "injection", "exploit", "cve",
                "pii", "gdrp", "hipaa", "soc2", "certificate", "tls",
                "ssl", "oath", "privilege", "sudo", "chmod", "chown",
                "root", "admin", "0385", "cors", "csrf", "xss",
            ]
            body_lower = entry["reviews"][0]["body"].lower()
            entry["security_flag"] = any(kw in body_lower for kw in sec_keywords)

            key = f"{repo}#{num}"
            findings[key] = entry

    # Write to well-known path
    Path(PR_REVIEW_FILE).write_text(json.dumps(findings, indent=2))

    if findings:
        flagged = [k for k, v in findings.items() if v.get("security_flag")]
        review_count = len(findings)
        sec_count = len(flagged)
        sec_warn = f" ⚠ {sec_count} flagged for security review" if sec_count else ""
        print(f"  PR reviews needing attention: {review_count}{sec_warn}")
        for k, v in findings.items():
            flag = " 🔒" if v.get("security_flag") else ""
            print(f"    {k}: {v['title']}{flag}")
            for r in v["reviews"]:
                body_snip = (r["body"][:120] + "..") if len(r["body"]) > 120 else r["body"]
                print(f"      [{r['state']}] {r['user']}: {body_snip}")
    else:
        print(f"  No pending PR reviews.")
        # Write empty so downstream knows there's nothing to do
        Path(PR_REVIEW_FILE).write_text("{}")

    return findings


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    reports = []
    errors = []

    for fn in [process_memories, process_skills]:
        name = fn.__name__.replace("process_", "")
        try:
            result = fn()
            if result:
                reports.append(result)
        except Exception as e:
            errors.append(f"**{name}** — ERROR: {e}")
            print(f"  ERROR: {e}", file=sys.stderr)

    # Step 3: Check open PRs for reviewer feedback
    print(f"\n{'='*50}\nPR Review Check\n{'='*50}")
    try:
        check_open_prs()
    except Exception as e:
        errors.append(f"**pr-review** — ERROR: {e}")
        print(f"  ERROR: {e}", file=sys.stderr)

    if not reports and not errors:
        msg = f"Nightly sync {TODAY} — no changes in either repo."
    else:
        parts = [f"Nightly sync {TODAY}\n"]
        if reports:
            parts.append("Changes:\n")
            parts.extend(reports)
        if errors:
            parts.append("Errors:\n")
            parts.extend(errors)
        msg = "\n".join(parts)

    print(f"\n{'='*50}\nFINAL OUTPUT\n{'='*50}")
    print(msg)

    out_path = os.path.expanduser("~/.hermes/cron/last-nightly-sync.txt")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    Path(out_path).write_text(msg)


if __name__ == "__main__":
    main()