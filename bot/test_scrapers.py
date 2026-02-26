#!/usr/bin/env python3
"""Test all scrapers to verify they connect and return valid data.

Run: python3 bot/test_scrapers.py
"""
import sys
import os
import json
import time

# Add bot/ to path
sys.path.insert(0, os.path.dirname(__file__))

PASS = 0
FAIL = 0


def test(name, func):
    global PASS, FAIL
    print(f"\n{'='*60}")
    print(f"TEST: {name}")
    print(f"{'='*60}")
    try:
        result = func()
        if result:
            PASS += 1
            print(f"  PASS: {result}")
        else:
            FAIL += 1
            print(f"  FAIL: returned falsy")
    except Exception as e:
        FAIL += 1
        print(f"  FAIL: {e}")


def test_webtracking_races():
    from scrapers.webtracking import fetch_json, API_URL
    data = fetch_json(f"{API_URL}?reqType=rc&date=all")
    assert data and isinstance(data, list), "No race data returned"
    assert len(data) > 200, f"Too few races: {len(data)}"
    # Check structure
    r = data[0]
    assert "raceIdx" in r, "Missing raceIdx"
    assert "raceName" in r, "Missing raceName"
    assert "date" in r, "Missing date"
    return f"{len(data)} races found"


def test_webtracking_results():
    from scrapers.webtracking_results import fetch_all_results, compute_results
    # Test with a known race (Saltsjöloppet 2024, idx 284)
    records = fetch_all_results(284)
    assert records and len(records) > 50, f"Too few records: {len(records) if records else 0}"
    results = compute_results(records)
    assert results, "No computed results"
    assert "A" in results, "Missing class A"
    # Check winner of class A
    winner = results["A"][0]
    assert winner["laps"] > 0, "Winner has 0 laps"
    assert winner["p"], "Winner has no pilot name"
    # Verify PB and R are excluded
    assert "PB" not in results, "PB (Patrol Boat) should be excluded"
    assert "R" not in results, "R (Rescue) should be excluded"
    classes = list(results.keys())
    return f"{len(classes)} classes, winner A: {winner['p']} ({winner['laps']} laps)"


def test_webtracking_api_base():
    """Verify the API is at /pbl not /wrl/pbl."""
    from scrapers.webtracking import fetch_json
    good = fetch_json("https://webtracking.se/pbl?reqType=rc&raceIdx=284")
    assert good, "API at /pbl should work"
    assert good.get("raceIdx") == 284, "Wrong race returned"
    return f"API base /pbl confirmed, race: {good.get('raceName')}"


def test_svemo_calendar():
    from scrapers.svemo_calendar import scrape_calendar
    events = scrape_calendar()
    # May return empty if SVEMO is down or has no events
    if events is None:
        return "WARNING: Could not connect to SVEMO (may be down)"
    return f"{len(events)} events found"


def test_uim_calendar():
    from scrapers.uim_calendar import scrape_calendar
    events = scrape_calendar()
    if events is None:
        return "WARNING: Could not connect to UIM (may be down)"
    return f"{len(events)} events found"


def test_scrape_tracker():
    from scrape_tracker import should_scrape, mark_scraped, get_last_scraped
    # Test mark + check cycle
    mark_scraped("_test_source", count=42, status="ok")
    assert not should_scrape("_test_source"), "Should not need scraping right after marking"
    assert should_scrape("_test_source", force=True), "Force should always return True"
    last = get_last_scraped("_test_source")
    assert last is not None, "Should have a timestamp"
    # Clean up
    log_file = os.path.join(os.path.dirname(__file__), "scrape_log.json")
    with open(log_file) as f:
        log = json.load(f)
    del log["_test_source"]
    with open(log_file, "w") as f:
        json.dump(log, f, indent=2)
    return "mark/check/force/timestamp all work"


def test_build_resultat():
    from builders.build_resultat import load_json
    races = load_json("webtracking_races.json")
    results = load_json("webtracking_results.json")
    assert races, "No cached race data"
    assert results, "No cached results data"
    assert len(races) > 200, f"Too few cached races: {len(races)}"
    assert len(results) > 200, f"Too few cached results: {len(results)}"
    return f"Cache OK: {len(races)} races, {len(results)} results"


def test_resultat_html():
    """Verify resultat.html has valid embedded data."""
    html_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "resultat.html")
    assert os.path.exists(html_path), "resultat.html not found"
    with open(html_path) as f:
        html = f.read()
    assert "var RACES=" in html, "Missing RACES data"
    assert "var RESULTS=" in html, "Missing RESULTS data"
    assert "ENTS" not in html, "Old ENTS variable still present"
    assert "function render()" in html, "Missing render function"
    assert "function renderRaceBody(idx)" in html, "Missing renderRaceBody() function"
    assert "function ft(" in html, "Missing type filter function ft()"
    assert "var aT=" in html, "Missing type filter state variable aT"
    assert 'id="typeFilters"' in html, "Missing typeFilters container"
    assert "typeCounts" in html, "Missing dynamic type filter builder"
    assert "var SVEMO=" in html, "Missing SVEMO data"
    assert "function renderSvemo()" in html, "Missing renderSvemo function"
    size_kb = len(html) / 1024
    return f"Valid ({size_kb:.0f} KB)"


if __name__ == "__main__":
    print("SVERA Scraper Test Suite")
    print(f"Time: {time.strftime('%Y-%m-%d %H:%M:%S')}")

    test("Scrape Tracker", test_scrape_tracker)
    test("Cached Data", test_build_resultat)
    test("resultat.html Structure", test_resultat_html)
    test("WebTracking API Base", test_webtracking_api_base)
    test("WebTracking Races", test_webtracking_races)
    test("WebTracking Results", test_webtracking_results)
    test("SVEMO Calendar", test_svemo_calendar)
    test("UIM Calendar", test_uim_calendar)

    print(f"\n{'='*60}")
    print(f"RESULTS: {PASS} passed, {FAIL} failed")
    print(f"{'='*60}")
    sys.exit(1 if FAIL > 0 else 0)
