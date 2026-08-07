#!/usr/bin/env python3
"""Quick seed: fetch VINs for current trims and save to state file without enrichment overhead."""
import json, os, requests, time

api_key = os.getenv("VISOR.VIN_API_KEY") or os.getenv("VISOR_API_KEY")
project_root = "/opt/data/repos/agent-skills"
state_path = os.path.join(project_root, "data", "seen_listings.json")

# Load existing state
seen = {}
if os.path.exists(state_path):
    with open(state_path) as f:
        data = json.load(f)
        if isinstance(data, dict):
            seen = data
        elif isinstance(data, list):
            seen = {vin: {} for vin in data}

# Load config
config_path = os.path.join(project_root, "research", "car_tracker", "config", "target_profiles.json")
if os.path.exists(config_path):
    with open(config_path) as f:
        data = json.load(f)
        targets = list(data.values()) if isinstance(data, dict) else data
else:
    targets = []

headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}

for t in targets:
    make = t.get("make", "")
    model = t.get("model", "")
    trim = t.get("trim", "")
    print(f"Fetching {make} {model} {trim}...")
    
    params = {
        "make": make,
        "model": model,
        "trim": trim,
        "year_min": t.get("year", 2026),
        "limit": 100,
        "sold": "false",
        "inventory_type": "new",
    }
    
    try:
        r = requests.get("https://api.visor.vin/v1/listings", headers=headers, params=params, timeout=15)
        if r.status_code == 200:
            data = r.json()
            listings = data.get("data", [])
            count = 0
            for car in listings:
                vin = car.get("vin") or car.get("id")
                if vin and vin not in seen:
                    seen[vin] = {}
                    count += 1
            print(f"  Added {count} new VINs ({len(listings)} total in response)")
        else:
            print(f"  API error: {r.status_code}")
    except Exception as e:
        print(f"  Error: {e}")
    
    time.sleep(0.5)

# Save
os.makedirs(os.path.dirname(state_path), exist_ok=True)
with open(state_path, "w") as f:
    json.dump(seen, f, indent=2)
print(f"\nSaved {len(seen)} VINs to {state_path}")
