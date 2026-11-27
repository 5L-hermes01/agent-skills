#!/usr/bin/env python3
"""Cron shim: HN Brief WEEKLY corpus for the #hacker-news-weekly aggregator.

The cron validator requires a REAL file directly inside HERMES_HOME/scripts/, so
this is a thin shim; the implementation ships with the skill:
  /opt/data/skills/research/hn-brief-dataset/scripts/hn-brief-period.py

Prints (stdout -> injected into the cron agent's prompt) the last 7 days of
top headlines plus a bounded excerpt of each day's digest.
"""
import runpy
import sys

CANONICAL = "/opt/data/skills/research/hn-brief-dataset/scripts/hn-brief-period.py"
ARGS = ["--days", "7", "--label", "weekly", "--headlines", "20", "--digest-chars", "3000"]

if __name__ == "__main__":
    sys.argv = [CANONICAL, *ARGS, *sys.argv[1:]]
    runpy.run_path(CANONICAL, run_name="__main__")
