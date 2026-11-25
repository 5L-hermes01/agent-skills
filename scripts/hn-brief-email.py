#!/usr/bin/env python3
"""Cron entry point for the HN Brief daily email.

The cron runner requires a REAL file directly inside HERMES_HOME/scripts/
(a symlink resolving outside that directory is rejected as path traversal), so
this is a thin shim. The implementation ships with the skill:
  /opt/data/skills/research/hn-brief-dataset/scripts/hn-brief-email.py
"""
import runpy
import sys

CANONICAL = "/opt/data/skills/research/hn-brief-dataset/scripts/hn-brief-email.py"

if __name__ == "__main__":
    sys.argv[0] = CANONICAL
    runpy.run_path(CANONICAL, run_name="__main__")
