#!/usr/bin/env python3
"""Scrape boat racing calendar from tam.svemo.se.

TAM API returns competitions as JSON with camelCase field names.
We filter for water sport branches (Rundbana=22, Aquabike=26, Offshore=27)
and extract upcoming events with class lists.
"""
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
    seen_ids = set()
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
                for c in comps:
                    cid = c.get("id")
                    if cid and cid not in seen_ids:
                        seen_ids.add(cid)
                        all_comps.append(c)
                print(f"[svemo] Year {year}: found {len(comps)} competitions")
        except Exception as e:
            print(f"[svemo] Year {year} search failed: {e}")

    competitions = all_comps

    # Filter for boat racing branches
    # API uses camelCase: branchId, name, fromDate, arena, organizer
    today = datetime.now().strftime("%Y-%m-%d")
    events = []
    for comp in competitions:
        branch_id = comp.get("branchId")
        if branch_id not in BRANCHES:
            continue

        # Parse date from ISO format "2026-05-01T00:00:00"
        from_date = comp.get("fromDate", "")
        date_str = from_date[:10] if from_date else ""

        # Skip past events
        if date_str < today:
            continue

        # Skip cancelled events
        if comp.get("workflowStateCancelled"):
            continue

        # Extract class names from competitionClasses
        classes_list = []
        for cc in comp.get("competitionClasses", []):
            cc_name = cc.get("name", "")
            if cc_name:
                # Clean up: "3A" from "3A" or "Träningsläger (Offshore)" etc.
                classes_list.append(cc_name)

        events.append({
            "competition_id": comp.get("id"),
            "name": comp.get("name", ""),
            "date": date_str,
            "end_date": "",  # Not available in list view
            "location": comp.get("arena", ""),
            "organizer": comp.get("organizer", ""),
            "branch": BRANCHES[branch_id],
            "branch_id": branch_id,
            "status": "Inställd" if comp.get("workflowStateCancelled") else "Planerad",
            "classes": classes_list,
            "open_for_registration": comp.get("openForRegistration", False),
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
        if events is not None:
            save(events)
            mark_scraped("svemo_calendar", count=len(events))
