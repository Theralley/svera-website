#!/usr/bin/env python3
"""Scrape boat racing calendar from tam.svemo.se."""
import urllib.request
import urllib.parse
import json
import os
import re
import http.cookiejar
from datetime import datetime

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
CONFIG_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "config.json")

# Branch IDs for water sports
BRANCHES = {22: "Rundbana", 26: "Aquabike", 27: "Offshore"}


def load_config():
    with open(CONFIG_FILE) as f:
        return json.load(f)


def scrape_calendar():
    """Login to TAM and scrape boat racing competitions."""
    print("[svemo] Loading config...")
    cfg = load_config()
    tam = cfg["data_sources"]["svemo_tam"]
    username = tam["username"]
    password = tam["password"]

    cj = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    opener.addheaders = [("User-Agent", "SVERA-Bot/1.0")]

    # Step 1: GET login page for token
    print("[svemo] Fetching login page...")
    resp = opener.open(tam["login_url"], timeout=15)
    html = resp.read().decode()

    token_match = re.search(
        r'name="__RequestVerificationToken"\s+.*?value="([^"]+)"', html
    )
    if not token_match:
        print("[svemo] ERROR: Could not find verification token")
        return None
    token = token_match.group(1)

    # Step 2: POST login
    print("[svemo] Logging in...")
    login_data = urllib.parse.urlencode({
        "__RequestVerificationToken": token,
        "UserName": username,
        "Password": password,
        "RememberMe": "false",
    }).encode()
    req = urllib.request.Request(tam["login_url"], data=login_data, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    resp = opener.open(req, timeout=15)

    # Step 3: GET competition page
    print("[svemo] Fetching competition page...")
    resp = opener.open(tam["calendar_url"], timeout=15)
    html = resp.read().decode()

    # Step 4: POST search form — search all branches, current year
    token_match = re.search(
        r'name="__RequestVerificationToken"\s+.*?value="([^"]+)"', html
    )
    if token_match:
        token = token_match.group(1)

    # Try current year first, then next year
    all_comps = []
    for year in [str(datetime.now().year), str(datetime.now().year + 1)]:
        search_data = urllib.parse.urlencode({
            "__RequestVerificationToken": token,
            "SelectedBranchId": "",
            "SelectedYear": year,
            "SelectedDistrictId": "",
            "SelectedCompetitionType": "",
            "Name": "",
        }).encode()
        req = urllib.request.Request(tam["calendar_url"], data=search_data, method="POST")
        req.add_header("Content-Type", "application/x-www-form-urlencoded")
        req.add_header("HX-Request", "true")
        try:
            resp = opener.open(req, timeout=15)
            html = resp.read().decode()
            model_match = re.search(r"\$model\s*=\s*(\[.*?\]);", html, re.DOTALL)
            if model_match:
                comps = json.loads(model_match.group(1))
                all_comps.extend(comps)
                print(f"[svemo] Year {year}: found {len(comps)} competitions")
        except Exception as e:
            print(f"[svemo] Year {year} search failed: {e}")

    competitions = all_comps

    # Filter for boat racing branches
    today = datetime.now().strftime("%Y-%m-%d")
    events = []
    for comp in competitions:
        branch_id = comp.get("BranchId")
        if branch_id not in BRANCHES:
            continue
        date_str = comp.get("StartDate", "")
        # Only future events
        if date_str < today:
            continue
        events.append({
            "name": comp.get("Name", ""),
            "date": date_str,
            "end_date": comp.get("EndDate", ""),
            "location": comp.get("LocationName", ""),
            "organizer": comp.get("OrganizerName", ""),
            "branch": BRANCHES[branch_id],
            "branch_id": branch_id,
            "status": comp.get("StatusText", ""),
        })

    events.sort(key=lambda e: e["date"])
    print(f"[svemo] Found {len(events)} upcoming boat racing events")
    return events


def save(events):
    os.makedirs(DATA_DIR, exist_ok=True)
    out = os.path.join(DATA_DIR, "svemo_calendar.json")
    with open(out, "w") as f:
        json.dump(events, f, ensure_ascii=False, indent=2)
    print(f"[svemo] Saved to {out}")
    return out


if __name__ == "__main__":
    import sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
    from scrape_tracker import should_scrape, mark_scraped

    if not should_scrape("svemo_calendar") and "--force" not in sys.argv:
        print("[svemo_calendar] Skipping — scraped recently")
    else:
        events = scrape_calendar()
        if events:
            save(events)
            mark_scraped("svemo_calendar", count=len(events))
