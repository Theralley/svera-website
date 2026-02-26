#!/usr/bin/env python3
"""Scrape offshore calendar from uim.sport."""
import urllib.request
import urllib.parse
import json
import os
import re
from datetime import datetime

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
URL = "https://www.uim.sport/CalendarList.aspx"


def scrape_calendar():
    """Fetch UIM calendar and filter for offshore events."""
    print("[uim] Fetching calendar page...")
    req = urllib.request.Request(URL, headers={"User-Agent": "SVERA-Bot/1.0"})
    resp = urllib.request.urlopen(req, timeout=20)
    html = resp.read().decode()

    # Extract __VIEWSTATE and __EVENTVALIDATION
    vs_match = re.search(r'id="__VIEWSTATE"\s+value="([^"]*)"', html)
    ev_match = re.search(r'id="__EVENTVALIDATION"\s+value="([^"]*)"', html)

    if not vs_match or not ev_match:
        print("[uim] WARNING: No viewstate found, parsing initial page only")

    # Parse events from the page HTML
    # The calendar uses a RadGrid - extract table rows
    events = []

    # Look for event rows in the grid
    row_pattern = re.compile(
        r'<tr[^>]*class="[^"]*rgRow[^"]*"[^>]*>(.*?)</tr>', re.DOTALL
    )
    alt_pattern = re.compile(
        r'<tr[^>]*class="[^"]*rgAltRow[^"]*"[^>]*>(.*?)</tr>', re.DOTALL
    )
    cell_pattern = re.compile(r'<td[^>]*>(.*?)</td>', re.DOTALL)

    for pattern in [row_pattern, alt_pattern]:
        for row_match in pattern.finditer(html):
            cells = cell_pattern.findall(row_match.group(1))
            if len(cells) >= 4:
                # Clean HTML tags from cells
                clean = [re.sub(r'<[^>]+>', '', c).strip() for c in cells]
                event = {
                    "date": clean[0] if len(clean) > 0 else "",
                    "name": clean[1] if len(clean) > 1 else "",
                    "venue": clean[2] if len(clean) > 2 else "",
                    "country": clean[3] if len(clean) > 3 else "",
                    "discipline": "Offshore",
                }
                if event["name"]:
                    events.append(event)

    # If we got events from initial load, try postback for offshore filter
    if not events:
        print("[uim] No events in initial HTML, attempting postback...")
        # Try posting with discipline filter
        if vs_match and ev_match:
            post_data = urllib.parse.urlencode({
                "__VIEWSTATE": vs_match.group(1),
                "__EVENTVALIDATION": ev_match.group(1),
                "__EVENTTARGET": "",
                "__EVENTARGUMENT": "",
            }).encode()
            req2 = urllib.request.Request(URL, data=post_data, method="POST")
            req2.add_header("User-Agent", "SVERA-Bot/1.0")
            req2.add_header("Content-Type", "application/x-www-form-urlencoded")
            try:
                resp2 = urllib.request.urlopen(req2, timeout=20)
                html2 = resp2.read().decode()
                for pattern in [row_pattern, alt_pattern]:
                    for row_match in pattern.finditer(html2):
                        cells = cell_pattern.findall(row_match.group(1))
                        if len(cells) >= 4:
                            clean = [re.sub(r'<[^>]+>', '', c).strip() for c in cells]
                            event = {
                                "date": clean[0],
                                "name": clean[1],
                                "venue": clean[2],
                                "country": clean[3],
                                "discipline": "Offshore",
                            }
                            if event["name"]:
                                events.append(event)
            except Exception as e:
                print(f"[uim] Postback failed: {e}")

    # Filter for current year and forward
    current_year = str(datetime.now().year)
    events = [e for e in events if current_year in e.get("date", "")]

    print(f"[uim] Found {len(events)} events")
    return events


def save(events):
    os.makedirs(DATA_DIR, exist_ok=True)
    out = os.path.join(DATA_DIR, "uim_calendar.json")
    with open(out, "w") as f:
        json.dump(events, f, ensure_ascii=False, indent=2)
    print(f"[uim] Saved to {out}")
    return out


if __name__ == "__main__":
    import sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
    from scrape_tracker import should_scrape, mark_scraped

    if not should_scrape("uim_calendar") and "--force" not in sys.argv:
        print("[uim_calendar] Skipping — scraped recently")
    else:
        events = scrape_calendar()
        if events:
            save(events)
            mark_scraped("uim_calendar", count=len(events))
