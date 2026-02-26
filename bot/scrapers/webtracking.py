#!/usr/bin/env python3
"""Scrape race data from webtracking.se API."""
import urllib.request
import json
import os
import time

API_URL = "https://webtracking.se/pbl"
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")


def fetch_json(url, retries=3):
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "SVERA-Bot/1.0"})
            resp = urllib.request.urlopen(req, timeout=15)
            return json.loads(resp.read().decode())
        except Exception as e:
            if attempt == retries - 1:
                print(f"  ERROR fetching {url}: {e}")
                return None
            time.sleep(2)


def sanitize(s):
    """Remove control characters and problematic chars from strings."""
    if not isinstance(s, str):
        return s
    return s.replace("\n", " ").replace("\r", "").replace("\t", " ").replace("'", "").replace('"', '').replace("\\", "").strip()


def classify_race(name):
    nl = name.lower()
    if "offshore" in nl or "saltsjö" in nl:
        return "Offshore"
    if "runban" in nl or "circuit" in nl:
        return "Rundbana"
    return "Tävling"


def scrape_races():
    """Fetch all races from webtracking.se."""
    print("[webtracking] Fetching all races...")
    data = fetch_json(f"{API_URL}?reqType=rc&date=all")
    if not data:
        print("[webtracking] FAILED to fetch races")
        return None

    races = []
    for r in data:
        d = r.get("date", "")
        formatted = f"{d[:4]}-{d[4:6]}-{d[6:8]}" if len(d) >= 8 else d
        name = sanitize(r["raceName"])
        races.append({
            "idx": r["raceIdx"],
            "name": name,
            "date": formatted,
            "year": d[:4],
            "type": classify_race(name),
        })

    print(f"[webtracking] Found {len(races)} races")
    return races


def scrape_entrants(race_idx):
    """Fetch entrants for a specific race."""
    data = fetch_json(f"{API_URL}?reqType=en&action=all&raceIdx={race_idx}")
    if not data or not isinstance(data, list):
        return []
    return data


def save(races):
    os.makedirs(DATA_DIR, exist_ok=True)
    out = os.path.join(DATA_DIR, "webtracking_races.json")
    with open(out, "w") as f:
        json.dump(races, f, ensure_ascii=False, indent=2)
    print(f"[webtracking] Saved to {out}")
    return out


if __name__ == "__main__":
    import sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
    from scrape_tracker import should_scrape, mark_scraped

    if not should_scrape("webtracking_races") and "--force" not in sys.argv:
        print("[webtracking] Skipping — scraped recently")
    else:
        races = scrape_races()
        if races:
            save(races)
            mark_scraped("webtracking_races", count=len(races))
