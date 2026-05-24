"""
Soil Health Card Scraper — soilhealth.dac.gov.in
Usage:
  python scrape.py --state Maharashtra
  python scrape.py --state Maharashtra --district Satara
  python scrape.py --state Maharashtra --district Satara --cycle 2025-26
  python scrape.py --state Maharashtra --district Satara --cycle 2025-26 --nutrient Nitrogen

NOTE: Update WMS_BASE and API_BASE from DevTools before each session (they rotate).
"""

import argparse, csv, time, sys
import requests

# ── Refresh these from DevTools > Network before each session ─────────────
WMS_BASE = "https://soilhealth.dac.gov.in/jW8X3zM5Y7pQvLr4K2Tn6HqPbD0tZmN9R6JfO1wCiG8xV5eTk2CdMoF9YsQr0Z7LmN1YxU4pTb2K5LvHqX7F3aCmGzR4Pw0D8UtYnJ9oZ2SvNlQ7Tz1PjR5LcX0Qf8HkV9OrG4V7YxU3pJk6TnMm5CdX8B9tRi1Lw2Qn7F4ZzJk8WvP1GrZ6Sx0JoH5C3oV7fNi2/shc/wms/wms"
API_BASE = "https://soilhealth.dac.gov.in/q8ZdH3f0mX1y7nJrP2K5BvW9aQpLb-6TsFcYzC4oUtN_MwRiDgGZ0xVsJe7Xy8nMk2TjPqFbD1C5LvOr9WQ6Xa3lYsN7V1sRmJez4OtUbY0Qn9hPk6WfLd2Y8oSvK3UtGmX5C7bT9Pn6xV0JfZ1TzQm8LrV9aGkM2JpXeN4fUoQ8SwCiRzN7VtPk1XgW5"
GRAPH_QL = "https://soilhealth4.dac.gov.in/"
# ─────────────────────────────────────────────────────────────────────────

HEADERS = {
    "Referer": "https://soilhealth.dac.gov.in/slusi-visualisation/",
    "User-Agent": "Mozilla/5.0",
}

# Nutrients: fixed by GoI Soil Health Card guidelines (not from portal)
NUTRIENTS = {
    "Nitrogen":       {"style": "N",  "unit": "kg/ha", "low": 280,  "high": 560},
    "Phosphorus":     {"style": "P",  "unit": "kg/ha", "low": 10,   "high": 25},
    "Potassium":      {"style": "K",  "unit": "kg/ha", "low": 108,  "high": 280},
    "Organic Carbon": {"style": "OC", "unit": "%",     "low": 0.5,  "high": 0.75},
    "pH":             {"style": "pH", "unit": "",      "low": 6.5,  "high": 7.5},
    "Sulphur":        {"style": "S",  "unit": "ppm",   "low": 10,   "high": 20},
    "Zinc":           {"style": "Zn", "unit": "ppm",   "low": 0.6,  "high": 1.2},
    "Boron":          {"style": "B",  "unit": "ppm",   "low": 0.5,  "high": 1.0},
    "Iron":           {"style": "Fe", "unit": "ppm",   "low": 4.5,  "high": 9.0},
    "Manganese":      {"style": "Mn", "unit": "ppm",   "low": 2.0,  "high": 4.0},
    "Copper":         {"style": "Cu", "unit": "ppm",   "low": 0.2,  "high": 0.4},
    "EC":             {"style": "EC", "unit": "dS/m",  "low": 0.8,  "high": 1.6},
}


# ── Discovery via GraphQL ─────────────────────────────────────────────────

def gql(query, variables={}):
    r = requests.post(GRAPH_QL, json={"query": query, "variables": variables},
                      headers=HEADERS, timeout=10)
    r.raise_for_status()
    return r.json()["data"]


def get_states():
    """Returns {state_name_lower: {"code": ..., "_id": ...}}"""
    data = gql("query GetState($getStateId: String, $code: String) { getState(id: $getStateId, code: $code) }")
    return {s["name"].lower(): {"code": s["code"], "_id": s["_id"]}
            for s in data["getState"]}


def get_districts(state_id):
    """Returns {district_name_lower: district_code}"""
    q = """query GetdistrictAndSubdistrictBystate($state: ID) {
      getdistrictAndSubdistrictBystate(state: $state)
    }"""
    data = gql(q, {"state": state_id})
    return {d["name"].lower(): d["code"]
            for d in data["getdistrictAndSubdistrictBystate"]}


def get_layer_info(state_code, district_code):
    """Returns (cycles_list, bbox_tuple) for a district."""
    r = requests.get(f"{API_BASE}/public/layers",
                     params={"state_code": state_code, "district_code": district_code},
                     headers=HEADERS, timeout=10)
    r.raise_for_status()
    d = r.json()
    b = d["bbox"]
    return d["shcLayers"], (b["minx"], b["miny"], b["maxx"], b["maxy"])


# ── Classification ────────────────────────────────────────────────────────

def classify(nutrient, value):
    t = NUTRIENTS[nutrient]
    if value < t["low"]:   return "Low"
    if value <= t["high"]: return "Medium"
    return "High"


# ── WMS scraping ──────────────────────────────────────────────────────────

def fetch(layer, lon, lat, delta=0.05):
    try:
        r = requests.get(WMS_BASE, headers=HEADERS, timeout=15, params={
            "service": "WMS", "version": "1.1.1", "request": "GetFeatureInfo",
            "layers": layer, "query_layers": layer, "srs": "EPSG:4326",
            "bbox": f"{lon-delta},{lat-delta},{lon+delta},{lat+delta}",
            "width": "101", "height": "101", "X": "50", "Y": "50",
            "feature_count": "50", "info_format": "application/json",
            "HIDE_GEOMETRY": "true",
        })
        return r.json().get("features", [])
    except Exception as e:
        print(f"  WARN: fetch failed at ({lat:.3f},{lon:.3f}): {e}")
        return []


def scrape(state_code, district_code, cycle, bbox):
    layer = f"{state_code}_{district_code}_shc_{cycle}"
    lons = [round(bbox[0] + i*0.05, 5) for i in range(int((bbox[2]-bbox[0])/0.05)+2)]
    lats = [round(bbox[1] + i*0.05, 5) for i in range(int((bbox[3]-bbox[1])/0.05)+2)]
    grid = [(lon, lat) for lat in lats for lon in lons]
    print(f"  Layer: {layer} | Grid: {len(grid)} cells")

    seen, records = set(), []
    for i, (lon, lat) in enumerate(grid, 1):
        for f in fetch(layer, lon, lat):
            fid = f.get("id", "")
            if not fid or fid in seen:
                continue
            seen.add(fid)
            p = f["properties"]
            row = {"village": p.get("village", ""), "feature_id": fid}
            for n, info in NUTRIENTS.items():
                s = info["style"]
                val = p.get(s, "")
                row[s] = val
                try:    row[f"{s}_category"] = classify(n, float(val))
                except: row[f"{s}_category"] = ""
            records.append(row)
        if i % 50 == 0:
            print(f"  [{i}/{len(grid)}] records={len(records)}")
        time.sleep(0.3)
    return records


# ── Output ────────────────────────────────────────────────────────────────

def save_samples(records, state, district, cycle, nutrient_filter, path):
    nutrients = [nutrient_filter] if nutrient_filter else list(NUTRIENTS.keys())
    rows = []
    for r in records:
        for n in nutrients:
            s = NUTRIENTS[n]["style"]
            rows.append({
                "State": state, "District": district, "Cycle": cycle,
                "Nutrient": n, "Village": r["village"],
                "Value": r.get(s, ""), "Category": r.get(f"{s}_category", ""),
                "Low_Threshold": NUTRIENTS[n]["low"],
                "High_Threshold": NUTRIENTS[n]["high"],
                "Unit": NUTRIENTS[n]["unit"],
                "Feature_ID": r["feature_id"],
            })
    if not rows: return
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader(); w.writerows(rows)
    print(f"  Samples → {path} ({len(rows)} rows)")


def save_summary(records, state, district, cycle, nutrient_filter, path):
    from collections import defaultdict
    nutrients = [nutrient_filter] if nutrient_filter else list(NUTRIENTS.keys())
    counts = defaultdict(lambda: {"Low": 0, "Medium": 0, "High": 0})
    for r in records:
        for n in nutrients:
            cat = r.get(f"{NUTRIENTS[n]['style']}_category", "")
            if cat in counts[n]: counts[n][cat] += 1
    rows = []
    for n in nutrients:
        c = counts[n]
        rows.append({
            "State": state, "District": district, "Cycle": cycle, "Nutrient": n,
            "Low_Count": c["Low"], "Medium_Count": c["Medium"], "High_Count": c["High"],
            "Total": c["Low"] + c["Medium"] + c["High"],
            "Low_Threshold": NUTRIENTS[n]["low"],
            "High_Threshold": NUTRIENTS[n]["high"],
            "Unit": NUTRIENTS[n]["unit"],
        })
    if not rows: return
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader(); w.writerows(rows)
    print(f"  Summary → {path} ({len(rows)} rows)")


# ── Main ──────────────────────────────────────────────────────────────────

def main():
    p = argparse.ArgumentParser(description="Soil Health Card scraper")
    p.add_argument("--state",    required=True,  help="State name e.g. Maharashtra")
    p.add_argument("--district", default=None,   help="District name (optional)")
    p.add_argument("--cycle",    default=None,   help="Cycle e.g. 2025-26 (optional)")
    p.add_argument("--nutrient", default=None,   choices=list(NUTRIENTS.keys()),
                                                 help="Nutrient name (optional)")
    args = p.parse_args()

    # ── 1. Resolve state ──────────────────────────────────────────────────
    print("Fetching states...")
    states = get_states()
    state_info = states.get(args.state.lower())
    if not state_info:
        # Try partial match
        matches = {k: v for k, v in states.items() if args.state.lower() in k}
        if len(matches) == 1:
            state_info = next(iter(matches.values()))
        else:
            sys.exit(f"State '{args.state}' not found. Available: {sorted(states.keys())}")
    state_code = state_info["code"]
    state_id   = state_info["_id"]
    print(f"State: {args.state} → code={state_code}")

    # ── 2. Resolve districts ──────────────────────────────────────────────
    print("Fetching districts...")
    all_districts = get_districts(state_id)

    if args.district:
        code = all_districts.get(args.district.lower())
        if not code:
            matches = {k: v for k, v in all_districts.items() if args.district.lower() in k}
            if len(matches) == 1:
                code = next(iter(matches.values()))
            else:
                sys.exit(f"District '{args.district}' not found. Available: {sorted(all_districts.keys())}")
        district_list = [(args.district, code)]
    else:
        district_list = [(name.title(), code) for name, code in all_districts.items()]

    print(f"Districts to scrape: {len(district_list)}")

    # ── 3. Scrape ─────────────────────────────────────────────────────────
    for district_name, district_code in district_list:
        print(f"\n{'='*55}\nDistrict: {district_name} (code={district_code})")
        try:
            cycles, bbox = get_layer_info(state_code, district_code)
        except Exception as e:
            print(f"  Skipping — could not fetch layer info: {e}")
            continue

        if not cycles:
            print("  No SHC cycles found. Skipping.")
            continue

        cycles_to_run = [args.cycle] if (args.cycle and args.cycle in cycles) else cycles
        if args.cycle and args.cycle not in cycles:
            print(f"  Cycle '{args.cycle}' not available. Available: {cycles}")
            continue

        print(f"  Cycles: {cycles_to_run}")

        for cycle in cycles_to_run:
            print(f"\n  ── Cycle: {cycle} ──")
            records = scrape(state_code, district_code, cycle, bbox)
            print(f"  Done: {len(records)} unique records")

            tag  = f"{args.state}_{district_name}_{cycle}".replace(" ", "_")
            save_samples(records, args.state, district_name, cycle,
                         args.nutrient, f"samples_{tag}.csv")
            save_summary(records, args.state, district_name, cycle,
                         args.nutrient, f"summary_{tag}.csv")


if __name__ == "__main__":
    main()