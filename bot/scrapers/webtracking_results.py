#!/usr/bin/env python3
"""Scrape actual race RESULTS (positions, laps, times) from webtracking.se.

The API endpoint reqType=rs returns checkpoint crossing data.
We process this into computed race results: position, laps, total time per class.
"""
import urllib.request
import json
import os
import time
from collections import defaultdict

API_URL = "https://webtracking.se/pbl"
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")

# Classes to EXCLUDE from results (not real competitors)
EXCLUDED_CLASSES = {"PB", "R", "Patrol", "Rescue", "pb", "r"}


def fetch_json(url, retries=3):
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "SVERA-Bot/1.0"})
            resp = urllib.request.urlopen(req, timeout=20)
            return json.loads(resp.read().decode())
        except Exception as e:
            if attempt == retries - 1:
                return None
            time.sleep(1)


def fetch_all_results(race_idx):
    """Fetch ALL result records for a race (paginated, 100 per page)."""
    all_records = []
    res_idx = 0
    while True:
        url = f"{API_URL}?reqType=rs&resIdx={res_idx}&raceIdx={race_idx}"
        data = fetch_json(url)
        if not data:
            break
        all_records.extend(data)
        if len(data) < 100:
            break
        res_idx = data[-1]["resIdx"]
        time.sleep(0.1)
    return all_records


def compute_results(records):
    """Process raw checkpoint records into ranked results per class.

    Returns dict: { "classname": [ {nr, pilot, coPilot, club, laps, time_s, time_str}, ... ] }
    sorted by position (most laps, then least time).
    """
    if not records:
        return {}

    # Gather start times and finish crossings per (class, entrant)
    starts = {}  # (grp, devIdx) -> earliest start time
    finishes = defaultdict(list)  # (grp, devIdx) -> [checkpoint_times]
    info = {}  # (grp, devIdx) -> {pilot, coPilot, dispName}

    for r in records:
        grp = r.get("grp", "")
        dev = r.get("devIdx", 0)

        # Skip system records and excluded classes
        if dev == 0:
            continue
        if grp in EXCLUDED_CLASSES:
            continue

        key = (grp, dev)

        # Store entrant info
        if key not in info:
            info[key] = {
                "nr": r.get("dispName", ""),
                "pilot": r.get("pilot", ""),
                "coPilot": r.get("coPilot", ""),
            }

        cp_idx = r.get("checkPIdx", 0)
        cp_time = r.get("checkPTime", 0)

        if cp_idx == 1 and r.get("checkPName") == "Start":
            # Per-entrant start (offshore) or per-class start (circuit)
            if key not in starts:
                starts[key] = cp_time
        elif cp_idx == 2:
            # Checkpoint/finish crossing = one lap
            finishes[key].append(cp_time)

    # For circuit races, start time may only exist as class-wide start
    # (devIdx=0 record). Let's also gather those:
    class_starts = {}  # (grp, heatType) -> start time
    for r in records:
        if r.get("devIdx") == 0 and r.get("checkPIdx") == 1 and r.get("checkPName") == "Start":
            ht = r.get("heatType", "")
            grp = r.get("grp", "")
            class_starts[(grp, ht)] = r.get("checkPTime", 0)

    # Build results per class
    classes = defaultdict(list)
    for (grp, dev), times in finishes.items():
        if not times:
            continue
        laps = len(times)
        last_t = max(times)

        # Find start time: per-entrant first, then class-wide
        start_t = starts.get((grp, dev))
        if not start_t:
            # Try class-wide start for any heat type
            for ht in ["h1", "h2", "h3", "h4", ""]:
                if (grp, ht) in class_starts:
                    start_t = class_starts[(grp, ht)]
                    break

        total_s = (last_t - start_t) if start_t and start_t < last_t else 0

        # Format time
        if total_s > 0:
            mins = int(total_s // 60)
            secs = total_s % 60
            time_str = f"{mins}:{secs:05.2f}"
        else:
            time_str = "-"

        entry = info.get((grp, dev), {})
        classes[grp].append({
            "nr": entry.get("nr", "?"),
            "p": entry.get("pilot", "?"),
            "cp": entry.get("coPilot", ""),
            "laps": laps,
            "ts": round(total_s, 2),
            "t": time_str,
        })

    # Sort each class: most laps desc, then least time asc
    for grp in classes:
        classes[grp].sort(key=lambda x: (-x["laps"], x["ts"] if x["ts"] > 0 else 999999))

    return dict(classes)


def scrape_all_results(races, existing=None, only_recent_years=0):
    """Scrape results for all races. Returns {raceIdx: {class: [results]}}.

    If existing is provided, only scrape races not already in the cache.
    If only_recent_years > 0, only scrape races from the last N years.
    """
    from datetime import datetime
    all_results = dict(existing) if existing else {}

    to_scrape = []
    current_year = datetime.now().year
    for race in races:
        idx = str(race["idx"])
        race_year = int(race.get("year", 0) or 0)

        # Skip if already cached (unless it's from current or last year — might still update)
        if idx in all_results and race_year < current_year - 1:
            continue

        # If only_recent_years set, skip old races
        if only_recent_years > 0 and race_year < current_year - only_recent_years:
            continue

        to_scrape.append(race)

    if not to_scrape:
        print(f"[results] All {len(races)} races already cached, nothing to scrape")
        return all_results

    total = len(to_scrape)
    print(f"[results] Scraping {total} races ({len(races) - total} already cached)...")

    for i, race in enumerate(to_scrape):
        idx = race["idx"]
        print(f"  [{i+1}/{total}] Race {idx}: {race['name'][:50]}...", end=" ", flush=True)

        records = fetch_all_results(idx)
        if not records:
            print("no data")
            continue

        results = compute_results(records)
        if results:
            # Sanitize strings (remove newlines, quotes that break JS)
            for cls_entries in results.values():
                for entry in cls_entries:
                    for key in ["nr", "p", "cp", "t"]:
                        val = entry.get(key, "")
                        if isinstance(val, str):
                            entry[key] = val.replace("\n", " ").replace("\r", "").replace("\t", " ").replace("'", "").replace('"', "").replace("\\", "").strip()

            all_results[str(idx)] = results
            total_entries = sum(len(v) for v in results.values())
            print(f"{len(results)} classes, {total_entries} entries")
        else:
            print("no finishers")

        time.sleep(0.15)

    return all_results


def save_results(results):
    os.makedirs(DATA_DIR, exist_ok=True)
    out = os.path.join(DATA_DIR, "webtracking_results.json")
    with open(out, "w") as f:
        json.dump(results, f, ensure_ascii=False, separators=(",", ":"))
    size_kb = os.path.getsize(out) / 1024
    print(f"[results] Saved {len(results)} races to {out} ({size_kb:.0f} KB)")
    return out


if __name__ == "__main__":
    import sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
    from scrape_tracker import should_scrape, mark_scraped

    force = "--force" in sys.argv
    full = "--full" in sys.argv

    if not should_scrape("webtracking_results") and not force:
        print("[results] Skipping — scraped recently")
        exit(0)

    # Load race list
    races_file = os.path.join(DATA_DIR, "webtracking_races.json")
    if not os.path.exists(races_file):
        print("Run webtracking.py first to get race list")
        exit(1)

    with open(races_file) as f:
        races = json.load(f)

    # Load existing cached results (incremental mode)
    existing = {}
    results_file = os.path.join(DATA_DIR, "webtracking_results.json")
    if os.path.exists(results_file) and not full:
        with open(results_file) as f:
            existing = json.load(f)
        print(f"[results] Loaded {len(existing)} cached races")

    print(f"[results] Processing {len(races)} races (incremental={not full})...")
    results = scrape_all_results(races, existing=existing if not full else None)
    save_results(results)
    mark_scraped("webtracking_results", count=len(results))
