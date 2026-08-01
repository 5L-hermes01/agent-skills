#!/usr/bin/env python3
"""Wrapper: daily car bulletin from the agent-skills repo workdir.

Pre-flight checks Visor API key availability before running publish_deals.py.
Exits 1 on missing/invalid credentials so the cron job surfaces the failure
instead of silently producing empty bulletins.
"""
import subprocess, sys, os

# --- Pre-flight: API key check ---
# Source the secret store env file for the Visor key
secret_env = "/opt/data/secrets/car-tracker.env"
if os.path.exists(secret_env):
    with open(secret_env) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, val = line.partition("=")
                val = val.strip().strip('"').strip("'")
                if key and val:
                    os.environ[key] = val

# Check both possible env var names
api_key = os.environ.get("VISOR_VIN_API_KEY") or os.environ.get("VISOR_API_KEY")
if not api_key:
    print("[-] FATAL: Visor API key not found.", file=sys.stderr)
    print(f"[-] Expected VISOR_VIN_API_KEY in {secret_env} (file {'exists' if os.path.exists(secret_env) else 'missing'}).", file=sys.stderr)
    print("[-] The daily car bulletin cannot run without a valid API key.", file=sys.stderr)
    sys.exit(1)

# Propagate to the name publish_deals.py expects
os.environ.setdefault("VISOR.VIN_API_KEY", api_key)

# --- Run publish_deals.py ---
script = "/opt/data/repos/agent-skills/research/car_tracker/scripts/publish_deals.py"
workdir = "/opt/data/repos/agent-skills/research/car_tracker"

result = subprocess.run([sys.executable, script], cwd=workdir, capture_output=True, text=True)
print(result.stdout, end="")
if result.stderr:
    print(result.stderr, file=sys.stderr, end="")
sys.exit(result.returncode)
