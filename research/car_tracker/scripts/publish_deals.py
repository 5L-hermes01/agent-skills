import os
import sys
import json
import argparse
import requests
import time
from dotenv import load_dotenv

# Base coordinate for distance calculation (Yonkers, NY)
YONKERS_LAT = 40.9312
YONKERS_LON = -73.8987

def get_distance(lat2, lon2):
    import math
    if lat2 is None or lon2 is None:
        return float('inf')
    R = 3958.8  # Earth radius in miles
    dlat = math.radians(lat2 - YONKERS_LAT)
    dlon = math.radians(lon2 - YONKERS_LON)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(YONKERS_LAT)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c * 1.18

def extract_color(car):
    """Best-effort extraction of paint color from the listing VDP URL and details."""
    text = (car.get("vdp_url") or car.get("vdpUrl") or "").lower()
    trim = (car.get("trim") or "").lower()
    
    color_map = {
        "wind chill": "Wind Chill Pearl",
        "wind-chill": "Wind Chill Pearl",
        "cloudburst": "Cloudburst Gray",
        "caviar": "Caviar Black",
        "eminent white": "Eminent White Pearl",
        "eminent-white": "Eminent White Pearl",
        "nightshade": "Midnight Black (Nightshade)",
        "blueprint": "Blueprint Blue",
        "supersonic red": "Supersonic Red",
        "supersonic-red": "Supersonic Red",
        "velvet red": "Velvet Red Pearl",
        "velvet-red": "Velvet Red Pearl",
        "fathom blue": "Fathom Blue Pearl",
        "fathom-blue": "Fathom Blue Pearl",
        "bright white": "Bright White Clearcoat",
        "bright-white": "Bright White Clearcoat",
        "granite crystal": "Granite Crystal Metallic",
        "granite-crystal": "Granite Crystal Metallic",
        "storm cloud": "Storm Cloud Gray",
        "storm-cloud": "Storm Cloud Gray",
        "silver sterling": "Silver Sterling Metallic",
        "silver-sterling": "Silver Sterling Metallic",
        "celestial silver": "Celestial Silver Metallic",
        "celestial-silver": "Celestial Silver Metallic",
        "midnight black": "Midnight Black Metallic",
        "midnight-black": "Midnight Black Metallic",
        "supersonic": "Supersonic Red",
        "supersonicred": "Supersonic Red",
        "white": "White",
        "black": "Black",
        "gray": "Gray",
        "grey": "Gray",
        "silver": "Silver",
        "blue": "Blue",
        "red": "Red",
        "bronze": "Bronze",
    }
    
    for key, val in color_map.items():
        if key in text or key in trim:
            return val
            
    return "TBD"

# Global cache for listing details
details_cache = {}

def seed_details_cache(project_root):
    # Try seeding from national discount analysis first to avoid hitting API rate limits
    paths = [
        os.path.join(project_root, "national_discount_analysis.json"),
        os.path.join(project_root, "data", "national_discount_analysis.json"),
        "national_discount_analysis.json"
    ]
    for path in paths:
        if os.path.exists(path):
            try:
                with open(path, "r") as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    for key, cars in data.items():
                        for car in cars:
                            vin = car.get("vin")
                            if vin:
                                details_cache[vin] = {
                                    "vehicle": {
                                        "build": {
                                            "exterior_color": car.get("exteriorColor") or car.get("exterior_color"),
                                            "combined_msrp": car.get("msrp") or car.get("reference_msrp")
                                        }
                                    }
                                }
                                if car.get("id"):
                                    details_cache[car.get("id")] = details_cache[vin]
                print(f"[+] Loaded/Seeded details cache from {path}", file=sys.stderr)
                break
            except Exception as e:
                print(f"[-] Warning: Failed to seed details cache from {path}: {e}", file=sys.stderr)

def get_color_and_options(car, api_key):
    vin = car.get("vin")
    if vin and vin in seen_listings_db and seen_listings_db[vin].get("color"):
        return seen_listings_db[vin]["color"]
        
    listing_id = car.get("id")
    details = None
    if listing_id and listing_id in details_cache:
        details = details_cache[listing_id]
    elif vin and vin in details_cache:
        details = details_cache[vin]
        
    if details is None and listing_id and api_key:
        url = f"https://api.visor.vin/v1/listings/{listing_id}"
        headers = {"Authorization": f"Bearer {api_key}"}
        try:
            r = requests.get(url, headers=headers, timeout=10)
            if r.status_code == 200:
                details = r.json().get("data", {})
                details_cache[listing_id] = details
                if vin:
                    details_cache[vin] = details
                time.sleep(0.5)  # small rate-limit spacing
            else:
                details = {}
        except Exception:
            details = {}
            
    color = None
    if details:
        vehicle = details.get("vehicle", {})
        build = vehicle.get("build", {})
        color = build.get("exterior_color")
        
    if not color:
        color = extract_color(car)
        
    if vin and color:
        if vin not in seen_listings_db:
            seen_listings_db[vin] = {}
        seen_listings_db[vin]["color"] = color
        
    return color

def get_msrp_info(car, api_key):
    vin = car.get("vin")
    if vin and vin in seen_listings_db and seen_listings_db[vin].get("msrp"):
        return seen_listings_db[vin]["msrp"]
        
    # Ensure color/options fetching has populated cache
    get_color_and_options(car, api_key)
    
    details = None
    listing_id = car.get("id")
    if listing_id and listing_id in details_cache:
        details = details_cache[listing_id]
    elif vin and vin in details_cache:
        details = details_cache[vin]
        
    msrp = None
    if details:
        # Check vehicle build combined_msrp
        vehicle = details.get("vehicle", {})
        build = vehicle.get("build", {})
        msrp = build.get("combined_msrp") or build.get("base_msrp")
        if not msrp:
            # Check pricing line_items
            pricing = details.get("pricing", {})
            if pricing:
                for item in pricing.get("line_items", []):
                    if item.get("role") == "pricing_anchor" or item.get("subtype") == "msrp":
                        msrp = item.get("amount_usd")
                        break
                        
    if msrp and vin:
        if vin not in seen_listings_db:
            seen_listings_db[vin] = {}
        seen_listings_db[vin]["msrp"] = msrp
        
    return msrp

def abbreviate_color(color_name):
    if not color_name:
        return "TBD"
    c = color_name.upper().strip()
    if "WIND CHILL" in c or "PEARL" in c:
        return "Pearl"
    if "BLACK" in c or "CAVIAR" in c:
        return "Black"
    if "SILVER" in c:
        return "Silver"
    if "STORM" in c:
        return "Storm"
    if "CEMENT" in c:
        return "Cement"
    if "BLUE" in c:
        return "Blue"
    if "RED" in c or "RUBY" in c or "MATADOR" in c:
        return "Red"
    if "GRAY" in c or "GREY" in c or "INCOGNITO" in c or "CLOUDBURST" in c:
        return "Gray"
    if "WHITE" in c:
        return "White"
    return color_name[:8]

def get_features_summary(car, make, model, api_key):
    vin = car.get("vin")
    if vin and vin in seen_listings_db and seen_listings_db[vin].get("features"):
        return seen_listings_db[vin]["features"]
        
    vdp_url = car.get("vdp_url") or car.get("vdpUrl") or ""
    options_text = ""
    listing_id = car.get("id")
    
    details = None
    if listing_id and listing_id in details_cache:
        details = details_cache[listing_id]
    elif vin and vin in details_cache:
        details = details_cache[vin]
        
    if details:
        options_list = details.get("vehicle", {}).get("build", {}).get("options")
        if isinstance(options_list, list):
            options_text += " ".join(str(o) for o in options_list)
        elif isinstance(options_list, str):
            options_text += options_list
            
    text_to_scan = f"{vdp_url} {car.get('trim') or ''} {options_text}".upper()
    
    features_str = "C: 0/0 | O: 0/0"
    
    if make.lower() == "toyota" and "highlander" in model.lower():
        pano_keywords = ["PANORAMIC ROOF", "PANORAMIC SUNROOF", "PANORAMIC MOONROOF", "PANO ROOF", "MOONROOF", "SUNROOF", "PANO-ROOF"]
        pvm_keywords = ["PANORAMIC VIEW", "PVM", "360 CAMERA", "SURROUND VIEW", "360-CAMERA", "360-DEGREE"]
        capt_keywords = ["CAPTAIN", "7-PASSENGER", "7 PASSENGER", "7-SEAT", "7 SEAT", "CAPTAINS"]
        
        has_pano = any(kw in text_to_scan for kw in pano_keywords)
        has_pvm = any(kw in text_to_scan for kw in pvm_keywords)
        has_capt = any(kw in text_to_scan for kw in capt_keywords)
        
        if (not has_pano or not has_pvm or not has_capt) and vdp_url and vdp_url.startswith("http"):
            try:
                headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:151.0) Gecko/20100101 Firefox/151.0"}
                r = requests.get(vdp_url, headers=headers, timeout=3)
                if r.status_code == 200:
                    html_text = r.text.upper()
                    if not has_pano: has_pano = any(kw in html_text for kw in pano_keywords)
                    if not has_pvm: has_pvm = any(kw in html_text for kw in pvm_keywords)
                    if not has_capt: has_capt = any(kw in html_text for kw in capt_keywords)
            except Exception:
                pass
                
        crit_matched = 2
        if has_capt: crit_matched += 1
        
        opt_matched = 0
        if has_pano: opt_matched += 1
        if has_pvm: opt_matched += 1
        
        features_str = f"C: {crit_matched}/3 | O: {opt_matched}/2"
        
    elif make.lower() == "lexus" and "tx" in model.lower():
        ml_keywords = ["MARK LEVINSON", "LEVINSON", "MARK-LEVINSON"]
        tech_keywords = ["TECHNOLOGY PACKAGE", "TECH PACKAGE", "TECH PKG", "TECHNOLOGY PKG", "TECH-PACKAGE"]
        capt_keywords = ["CAPTAIN", "CAPTAINS", "6-PASSENGER", "6 PASSENGER", "6-SEAT", "6 SEAT"]
        
        has_ml = any(kw in text_to_scan for kw in ml_keywords)
        has_tech = any(kw in text_to_scan for kw in tech_keywords)
        has_capt = any(kw in text_to_scan for kw in capt_keywords)
        
        if (not has_ml or not has_tech or not has_capt) and vdp_url and vdp_url.startswith("http"):
            try:
                headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:151.0) Gecko/20100101 Firefox/151.0"}
                r = requests.get(vdp_url, headers=headers, timeout=3)
                if r.status_code == 200:
                    html_text = r.text.upper()
                    if not has_ml: has_ml = any(kw in html_text for kw in ml_keywords)
                    if not has_tech: has_tech = any(kw in html_text for kw in tech_keywords)
                    if not has_capt: has_capt = any(kw in html_text for kw in capt_keywords)
            except Exception:
                pass
                
        crit_matched = 2
        opt_matched = 0
        if has_ml: opt_matched += 1
        if has_tech: opt_matched += 1
        if has_capt: opt_matched += 1
        
        features_str = f"C: {crit_matched}/2 | O: {opt_matched}/3"
        
    elif make.lower() == "chrysler" and "pacifica" in model.lower():
        hk_keywords = ["HARMAN KARDON", "HARMAN/KARDON", "HK SOUND", "HK AUDIO", "19-SPEAKER", "19 SPEAKER"]
        
        has_hk = any(kw in text_to_scan for kw in hk_keywords)
        if not has_hk and vdp_url and vdp_url.startswith("http"):
            try:
                headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:151.0) Gecko/20100101 Firefox/151.0"}
                r = requests.get(vdp_url, headers=headers, timeout=3)
                if r.status_code == 200:
                    html_text = r.text.upper()
                    has_hk = any(kw in html_text for kw in hk_keywords)
            except Exception:
                pass
                
        if not has_hk and "PINNACLE" in (car.get("trim") or "").upper():
            has_hk = True
            
        crit_matched = 2
        opt_matched = 1 if has_hk else 0
        
        features_str = f"C: {crit_matched}/2 | O: {opt_matched}/1"
        
    if vin and features_str:
        if vin not in seen_listings_db:
            seen_listings_db[vin] = {}
        seen_listings_db[vin]["features"] = features_str
        
    return features_str

def car_matches_profile(car, make, model, trim, vin_prefix, req_keywords, requires_awd, requires_hybrid):
    car_trim = (car.get("trim") or "").lower()
    car_vin = (car.get("vin") or "").upper()
    price = car.get("price")
    car_type = (car.get("inventory_type", car.get("inventoryType", "used")) or "used").lower()
    
    if price is None or not car_vin:
        return False
        
    # Powertrain matching
    if vin_prefix and len(car_vin) > 9:
        if make.lower() == "toyota" or make.lower() == "lexus":
            if len(vin_prefix) > 4 and car_vin[3:5] != vin_prefix[3:5]:
                return False
        elif make.lower() == "chrysler":
            if len(vin_prefix) > 5 and car_vin[5] != vin_prefix[5]:
                return False
                
    # Condition matching (strictly new)
    if car_type != "new":
        return False
        
    # Match trim keywords
    listing_text = f"{model} {car_trim}".upper()
    if req_keywords:
        if not any(k.upper() in listing_text for k in req_keywords):
            return False
            
    # Match AWD
    if requires_awd:
        is_awd_flag = car.get("is_awd") or (car.get("drivetrain") or "").upper() in ("AWD", "4WD", "4X4", "ALL-WHEEL DRIVE")
        if not is_awd_flag:
            vdp_url = car.get("vdp_url") or car.get("vdpUrl") or ""
            awd_text = f"{model} {car_trim} {vdp_url}".upper()
            is_awd_flag = any(token in awd_text for token in ("AWD", "4WD", "4X4"))
        if not is_awd_flag and len(car_vin) > 6:
            if car_vin.startswith(("5TDAA", "5TDAC", "5TDAD")):
                is_awd_flag = (car_vin[6] == "B")
        if not is_awd_flag:
            return False
            
    # Match Hybrid
    if requires_hybrid:
        hybrid_text = f"{model} {car_trim}".upper()
        is_hybrid_flag = "HYBRID" in hybrid_text or car_vin.startswith(("5TDAC", "5TDAD"))
        if not is_hybrid_flag:
            return False
            
    return True

def get_listings_for_trim(target, api_key, project_root):
    make = target["make"]
    model = target["model"]
    trim = target["trim"]
    vin_prefix = target.get("vin_prefix") or target.get("sample_vin")
    
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    listings = []
    limit = 100
    offset = 0
    
    # Query up to 15 pages to find matches across entire inventory
    if api_key:
        for page in range(15):
            url = f"https://api.visor.vin/v1/listings?make={make}&model={model}&limit={limit}&offset={offset}"
            try:
                r = requests.get(url, headers=headers, timeout=10)
                if r.status_code == 200:
                    data = r.json().get("data", [])
                    if not data:
                        break
                    listings.extend(data)
                    offset += limit
                    time.sleep(1.0) # sleep 1.0s between pages to stay under rate limits
                else:
                    print(f"[-] Warning: Visor API request failed with status code {r.status_code}", file=sys.stderr)
                    break
            except Exception as e:
                print(f"[-] Warning: Visor API request failed with error: {e}", file=sys.stderr)
                break
                
    # Filter by trim keywords, AWD, Hybrid, and powertrain prefix
    matching = []
    
    # Extract criteria from target configuration
    req_keywords = target.get("required_trim_keywords")
    if req_keywords is None:
        trim_lower = trim.lower()
        if "platinum" in trim_lower or "plat" in trim_lower:
            req_keywords = ["plat"]
        elif "limited" in trim_lower or "ltd" in trim_lower:
            req_keywords = ["limit"]
        elif "pinnacle" in trim_lower or "pinn" in trim_lower:
            req_keywords = ["pinn"]
        elif "350" in trim_lower:
            req_keywords = ["350"]
        else:
            trim_words = trim_lower.split()
            req_keywords = [w for w in trim_words if w not in ["awd", "4wd", "hybrid", "max"]]
            
    requires_awd = target.get("requires_awd")
    if requires_awd is None:
        requires_awd = "awd" in trim.lower() or "4wd" in trim.lower() or "4x4" in trim.lower()
        
    requires_hybrid = target.get("requires_hybrid")
    if requires_hybrid is None:
        requires_hybrid = "hybrid" in trim.lower()
        
    for car in listings:
        if car_matches_profile(car, make, model, trim, vin_prefix, req_keywords, requires_awd, requires_hybrid):
            lat = car.get("latitude")
            lon = car.get("longitude")
            dist = get_distance(lat, lon)
            car["computed_distance"] = dist
            matching.append(car)
            
    # Also load from saved file if API has fewer matches
    saved_path = os.path.join(project_root, "data", "comprehensive_search_results.json")
    if os.path.exists(saved_path):
        try:
            with open(saved_path, "r") as f:
                saved_data = json.load(f)
                
            # Flatten lists and search under all keys
            for key in saved_data:
                for car in saved_data[key]:
                    car_make = car.get("make", "")
                    car_model = car.get("model", "")
                    
                    if car_make.lower() != make.lower() or model.lower() not in car_model.lower():
                        continue
                        
                    if car_matches_profile(car, make, model, trim, vin_prefix, req_keywords, requires_awd, requires_hybrid):
                        lat = car.get("latitude")
                        lon = car.get("longitude")
                        dist = get_distance(lat, lon)
                        car["computed_distance"] = dist
                        # Prevent duplicate VINs
                        if not any(x.get("vin") == car.get("vin") for x in matching):
                            matching.append(car)
        except Exception as e:
            print(f"[-] Warning: Failed to load comprehensive_search_results.json: {e}", file=sys.stderr)

    # Sort matching by price ascending
    matching.sort(key=lambda x: x.get("price", float('inf')))
    return matching

# Global state cache database
seen_listings_db = {}

def load_seen_listings(state_path):
    global seen_listings_db
    if os.path.exists(state_path):
        try:
            with open(state_path, "r") as f:
                data = json.load(f)
                if isinstance(data, list):
                    seen_listings_db = {vin: {} for vin in data}
                    return set(data)
                elif isinstance(data, dict):
                    seen_listings_db = data
                    return set(data.keys())
        except Exception:
            return set()
    return set()

def save_seen_listings(seen_set, state_path):
    global seen_listings_db
    # Ensure all seen vins are in the db
    for vin in seen_set:
        if vin not in seen_listings_db:
            seen_listings_db[vin] = {}
    try:
        os.makedirs(os.path.dirname(state_path), exist_ok=True)
        with open(state_path, "w") as f:
            json.dump(seen_listings_db, f, indent=2)
    except Exception as e:
        print(f"[-] Error saving state file: {e}", file=sys.stderr)

def main():
    # Resolve project root dynamically to ensure path portability
    current = os.path.dirname(os.path.abspath(__file__))
    project_root = os.getcwd()
    while current and current != os.path.dirname(current):
        if os.path.exists(os.path.join(current, ".git")) or os.path.exists(os.path.join(current, ".agents")):
            project_root = current
            break
        current = os.path.dirname(current)

    dotenv_path = os.path.join(project_root, ".env")
    if os.path.exists(dotenv_path):
        load_dotenv(dotenv_path)
    else:
        load_dotenv()
        
    # Seed our details cache from national discount analysis JSON
    seed_details_cache(project_root)
        
    api_key = os.getenv("VISOR.VIN_API_KEY") or os.getenv("VISOR_API_KEY")
    if not api_key:
        print("[-] Warning: VISOR_API_KEY environment variable is not set. Visor API live search will be skipped.", file=sys.stderr)
        
    parser = argparse.ArgumentParser(description="Daily Car Tracker - Publishes new and cheapest car deals.")
    parser.add_argument("--trims", type=str, help="Path to JSON config of trims to monitor")
    args = parser.parse_args()
    
    default_trims = [
        {
            "key": "grand_highlander_hybrid_limited_awd",
            "year": 2026,
            "make": "Toyota",
            "model": "Grand Highlander",
            "trim": "Hybrid Limited AWD",
            "target_otd_price": 58450.85,
            "sample_vin": "5TDACAB53TS25G407",
            "must_haves": [
                "Hybrid powertrain",
                "AWD",
                "Limited trim",
                "Panoramic Moonroof",
                "Panoramic View Monitor (360 Cam)",
                "7-Passenger Seating (Captain's Chairs)",
                "Available or inbound unit that is not already sold/reserved"
            ],
            "required_trim_keywords": ["LIMITED"],
            "requires_awd": True,
            "requires_hybrid": True
        },
        {
            "key": "grand_highlander_hybrid_nightshade_awd",
            "year": 2026,
            "make": "Toyota",
            "model": "Grand Highlander",
            "trim": "Hybrid Nightshade AWD",
            "target_otd_price": 56109.95,
            "sample_vin": "5TDACAB59TS26E172",
            "must_haves": [
                "Hybrid powertrain",
                "AWD",
                "Nightshade trim",
                "Panoramic Moonroof",
                "Panoramic View Monitor (360 Cam)",
                "7-Passenger Seating (Captain's Chairs)",
                "Available or inbound unit that is not already sold/reserved"
            ],
            "required_trim_keywords": ["NIGHTSHADE"],
            "requires_awd": True,
            "requires_hybrid": True
        },
        {
            "key": "chrysler_pacifica_pinnacle_awd",
            "year": 2027,
            "make": "Chrysler",
            "model": "Pacifica",
            "trim": "Pinnacle AWD",
            "target_otd_price": None,
            "sample_vin": "2C4RC3PG8TR233685",
            "must_haves": [
                "AWD",
                "Pinnacle trim",
                "Harman Kardon Premium Sound",
                "Available or inbound unit that is not already sold/reserved"
            ],
            "required_trim_keywords": ["PINNACLE"],
            "requires_awd": True,
            "requires_hybrid": False
        },
        {
            "key": "lexus_tx_350_awd",
            "year": 2026,
            "make": "Lexus",
            "model": "TX",
            "trim": "350 AWD",
            "target_otd_price": None,
            "sample_vin": "5TDAAAB50RS004172",
            "must_haves": [
                "AWD",
                "350 trim",
                "Technology Package",
                "Captain's Chairs",
                "Mark Levinson Premium Sound",
                "Available or inbound unit that is not already sold/reserved"
            ],
            "required_trim_keywords": ["base", "premium", "luxury", "f sport", "f-sport", "350"],
            "requires_awd": True,
            "requires_hybrid": False
        }
    ]

    # Load monitored trims/profiles from configuration file
    trims_path = args.trims
    if not trims_path:
        for loc in [
            os.path.join(project_root, "config", "target_profiles.json"),
            os.path.join(project_root, "data", "target_profiles.json"),
            os.path.join(project_root, "target_profiles.json"),
            os.path.join(project_root, "data", "tracked_trims.json"),
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "target_profiles.json"),
            os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "target_profiles.json"),
            os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config", "target_profiles.json"),
            os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "tracked_trims.json")
        ]:
            if os.path.exists(loc):
                trims_path = loc
                break
                
    if trims_path and os.path.exists(trims_path):
        try:
            with open(trims_path, "r") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    # Convert profile dict to list of profile targets
                    monitored_trims = list(data.values())
                else:
                    monitored_trims = data
        except Exception as e:
            print(f"[-] Warning: Failed to load config from {trims_path}: {e}. Using defaults.", file=sys.stderr)
            monitored_trims = default_trims
    else:
        print("[!] Config file not found. Falling back to default target profiles.", file=sys.stderr)
        monitored_trims = default_trims
        
    # State tracking
    state_path = os.path.join(project_root, "data", "seen_listings.json")
    seen_vins = load_seen_listings(state_path)
    new_seen_vins = set(seen_vins)
    
    print("# Daily Car Market Bulletin (New Listings)")
    print(f"*Report generated for Yonkers, NY coordinates. Target distance comparisons sorted by proximity.*")
    
    first = True
    for target in monitored_trims:
        if not first:
            time.sleep(2.0)
        first = False
        
        make = target["make"]
        model = target["model"]
        trim = target["trim"]
        
        target_otd = target.get("target_otd_price")
        otd_str = f" — target ${target_otd:,.0f}" if target_otd else ""
        print(f"\n## 🚙 {make} {model} ({trim}){otd_str}")
        
        # Get listings
        listings = get_listings_for_trim(target, api_key, project_root)
        
        if not listings:
            print("*No active new inventory matching specifications found.*")
            continue
            
        cheapest_price = listings[0]["price"]
        
        # 1. Identify New Arrivals
        new_arrivals = []
        for car in listings:
            vin = car.get("vin")
            if vin not in seen_vins:
                new_arrivals.append(car)
                new_seen_vins.add(vin)
                
        # Print New Arrivals — top 2 by proximity, phone-width format, URLs after table
        print("\n### 🆕 New Arrivals (Top 2 Closest)")
        if new_arrivals:
            new_arrivals.sort(key=lambda x: x.get("computed_distance", float('inf')))
            top_new = new_arrivals[:2]
            urls = []
            print(f"| {'#':>2} | {'Dealer (mi)':<20} | {'Price':>8} | {'Δ':>6} | {'Color':<7} | {'C/O':>7} |")
            print(f"| {'-' * 2} | {'-' * 20} | {'-' * 8} | {'-' * 6} | {'-' * 7} | {'-' * 7} |")
            for car in top_new:
                c_price = car.get("price")
                c_dist = car.get("computed_distance", float('inf'))
                c_state = car.get("state", "??")
                c_dealer = car.get("dealer_name") or "Dealer"
                c_dealer_lbl = f"{c_dealer[:14]} {c_state} {c_dist:.0f}mi"
                c_vin = car.get("vin", "")
                c_vin_short = c_vin[-8:] if len(c_vin) >= 8 else c_vin
                delta = c_price - cheapest_price
                c_vdp = car.get("vdp_url") or car.get("vdpUrl") or ""
                c_color_raw = get_color_and_options(car, api_key)
                c_color = abbreviate_color(c_color_raw)
                c_feats = get_features_summary(car, make, model, api_key)
                # Compact C/O: "C:3/3 O:2/2" -> "3/3,2/2"
                c_feats_compact = c_feats.replace("C: ","").replace(" | O: ",",")
                urls.append((c_vin_short, c_vdp))
                row_num = len(urls)
                print(f"| {row_num:>2} | {c_dealer_lbl:<20} | ${c_price:,.0f} | ${delta:,.0f} | {c_color:<7} | {c_feats_compact:>7} |")
            if urls:
                print()
                for i, (vid, url) in enumerate(urls, 1):
                    if url:
                        print(f"{i}. {url}")
            # Benchmark: cheapest active listing on market
            cheapest_dealer = listings[0].get("dealer_name") or "Dealer"
            cheapest_state = listings[0].get("state", "??")
            cheapest_dist = listings[0].get("computed_distance", float('inf'))
            print(f"\n*Benchmark: cheapest active ${cheapest_price:,.0f} — {cheapest_dealer[:18]} {cheapest_state} {cheapest_dist:.0f}mi*")
        else:
            print("*No new listings appeared on the market since last check.*")
        
    # Update global state of seen VINs
    save_seen_listings(new_seen_vins, state_path)

if __name__ == "__main__":
    main()
