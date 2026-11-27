#!/usr/bin/env python3
"""Cron shim: HN Brief MONTHLY corpus for the #hacker-news-monthly aggregator.

The cron validator requires a REAL file directly inside HERMES_HOME/scripts/, so
this is a thin shim; the implementation ships with the skill:
  /opt/data/skills/research/hn-brief-dataset/scripts/hn-brief-period.py

Prints (stdout -> injected into the cron agent's prompt) the last 30 published
days of top headlines plus a bounded excerpt of each day's digest. Fewer
headlines and a shorter excerpt than the weekly window keep the corpus bounded.
"""
import runpy
import sys

CANONICAL = "/opt/data/skills/research/hn-brief-dataset/scripts/hn-brief-period.py"
ARGS = ["--days", "30", "--label", "monthly", "--headlines", "12", "--digest-chars", "1500"]

if __name__ == "__main__":
    sys.argv = [CANONICAL, *ARGS, *sys.argv[1:]]
    runpy.run_path(CANONICAL, run_name="__main__")
