#!/usr/bin/env python3
"""Scrape official race results from SVEMO TA (ta.svemo.se).

Uses TAM authentication to get the list of competitions with published results,
then fetches per-class results from the public ta.svemo.se results pages.

Data flow:
  1. Login to tam.svemo.se to get competition list (requires auth)
  2. For each competition, fetch public results from ta.svemo.se/Resultat/Tavling/{id}
  3. For each class with results, fetch entrant details
  4. Save to bot/data/svemo_results.json
"""
import urllib.request
import urllib.parse
import json
import os
import re
import time
import http.cookiejar
import html as htmlmod

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
CONFIG_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "config.json")

TA_BASE = "https://ta.svemo.se"


def load_config():
    with open(CONFIG_FILE) as f:
        return json.load(f)


def fetch_url(url, opener=None, timeout=15):
    """Fetch URL content, return decoded HTML string."""
    if opener:
        resp = opener.open(url, timeout=timeout)
    else:
        req = urllib.request.Request(url, headers={"User-Agent": "SVERA-Bot/1.0"})
        resp = urllib.request.urlopen(req, timeout=timeout)
    return resp.read().decode()


def login_tam(cfg):
    """Login to TAM and return authenticated opener."""
    tam = cfg["data_sources"]["svemo_tam"]
    cj = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    opener.addheaders = [("User-Agent", "SVERA-Bot/1.0")]

    # GET login page for CSRF token
    html = fetch_url(tam["login_url"], opener)
    token_match = re.search(
        r'name="__RequestVerificationToken"\s+.*?value="([^"]+)"', html
    )
    if not token_match:
        print("[svemo_results] ERROR: Could not find verification token")
        return None
    token = token_match.group(1)

    # POST login
    login_data = urllib.parse.urlencode({
        "__RequestVerificationToken": token,
        "UserName": tam["username"],
        "Password": tam["password"],
        "RememberMe": "false",
    }).encode()
    req = urllib.request.Request(tam["login_url"], data=login_data, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    opener.open(req, timeout=15)

    return opener


def fetch_competition_list(opener):
    """Fetch list of competitions with results from TAM (paginated)."""
    competitions = []
    for page in range(1, 20):
        url = f"https://tam.svemo.se/Result/Competition?page={page}"
        html = fetch_url(url, opener)

        pattern = (
            r'href="/Result/CompetitionDetail/(\d+)".*?'
            r'<h4[^>]*>(.*?)</h4>.*?'
            r'<b>([\d-]+)</b>.*?'
            r'label[^>]*>(.*?)</span>'
        )
        matches = re.findall(pattern, html, re.DOTALL)

        if not matches:
            break

        for m in matches:
            competitions.append({
                "id": int(m[0]),
                "name": htmlmod.unescape(m[1].strip()),
                "date": m[2].strip(),
                "branch": htmlmod.unescape(m[3].strip()),
            })
        print(f"[svemo_results] Page {page}: {len(matches)} competitions")

    return competitions


def fetch_competition_events(comp_id):
    """Fetch list of classes/events with results for a competition (public)."""
    url = f"{TA_BASE}/Resultat/Tavling/{comp_id}"
    try:
        html = fetch_url(url)
    except Exception as e:
        print(f"[svemo_results] Failed to fetch events for {comp_id}: {e}")
        return []

    # Parse RadGrid table for classes with results
    table_match = re.search(r"rgMasterTable.*?</table>", html, re.DOTALL)
    if not table_match:
        return []

    table = table_match.group(0)
    events = re.findall(
        r"<td>([^<]+)</td><td>\s*<a[^>]*EventId=(\d+)",
        table,
    )

    return [{"class_name": e[0].strip(), "event_id": int(e[1])} for e in events]


def fetch_event_results(comp_id, event_id):
    """Fetch individual results for a class/event (public).

    Returns list of dicts: [{pos, nr, driver, club, boat, class, nat, points}]
    """
    url = (
        f"{TA_BASE}/Public/Pages/Competition/Default/EventResult.aspx"
        f"?CompetitionId={comp_id}&EventId={event_id}"
    )
    try:
        html = fetch_url(url)
    except Exception as e:
        print(f"  Failed to fetch event {event_id}: {e}")
        return []

    # Find the detailed results table (has "Förare" column)
    tables = re.findall(r"<table[^>]*>(.*?)</table>", html, re.DOTALL)
    for table in tables:
        rows = re.findall(r"<tr[^>]*>(.*?)</tr>", table, re.DOTALL)
        if len(rows) < 2:
            continue

        # Check header for "Förare"
        header_cells = re.findall(r"<th[^>]*>(.*?)</th>", rows[0], re.DOTALL)
        headers = [re.sub(r"<[^>]+>", "", c).strip() for c in header_cells]

        if "Förare" not in headers:
            continue

        # Parse data rows
        entries = []
        for row in rows[1:]:
            cells = re.findall(r"<td[^>]*>(.*?)</td>", row, re.DOTALL)
            vals = [
                htmlmod.unescape(re.sub(r"<[^>]+>", "", c).strip())
                for c in cells
            ]
            if len(vals) >= 8:
                entries.append({
                    "pos": vals[0],
                    "nr": vals[1],
                    "driver": vals[2],
                    "club": vals[3],
                    "boat": vals[4],
                    "class": vals[5],
                    "nat": vals[6],
                    "points": vals[7],
                })
            elif len(vals) >= 4:
                # Minimal format (team results)
                entries.append({
                    "pos": vals[0],
                    "nr": vals[1],
                    "driver": vals[2],
                    "club": "",
                    "boat": "",
                    "class": "",
                    "nat": "",
                    "points": vals[3] if len(vals) > 3 else "",
                })
        return entries

    return []


def scrape_all():
    """Main scrape function: login, get competitions, fetch all results."""
    cfg = load_config()

    print("[svemo_results] Logging in to TAM...")
    opener = login_tam(cfg)
    if not opener:
        return None

    print("[svemo_results] Fetching competition list...")
    competitions = fetch_competition_list(opener)
    print(f"[svemo_results] Found {len(competitions)} competitions with results")

    # Load existing cache for incremental scraping
    cache_file = os.path.join(DATA_DIR, "svemo_results.json")
    existing = {}
    if os.path.exists(cache_file):
        with open(cache_file) as f:
            existing = json.load(f)
        print(f"[svemo_results] Loaded {len(existing.get('competitions', []))} cached competitions")

    # Build set of cached competition IDs
    cached_ids = set()
    if "competitions" in existing:
        cached_ids = {c["id"] for c in existing["competitions"]}

    result_data = {
        "competitions": list(existing.get("competitions", [])),
        "scraped_at": time.strftime("%Y-%m-%d %H:%M"),
    }

    # Keep existing competitions, add new ones
    existing_map = {c["id"]: c for c in result_data["competitions"]}

    for comp in competitions:
        comp_id = comp["id"]

        if comp_id in cached_ids:
            continue

        print(f"\n[svemo_results] {comp['date']} — {comp['name']}")

        events = fetch_competition_events(comp_id)
        if not events:
            print(f"  No classes with results")
            continue

        print(f"  {len(events)} classes with results")

        comp_data = {
            "id": comp_id,
            "name": comp["name"],
            "date": comp["date"],
            "branch": comp["branch"],
            "classes": {},
        }

        for event in events:
            class_name = event["class_name"]
            event_id = event["event_id"]

            entries = fetch_event_results(comp_id, event_id)
            if entries:
                comp_data["classes"][class_name] = entries
                print(f"  {class_name}: {len(entries)} entries")
            time.sleep(0.2)

        if comp_data["classes"]:
            existing_map[comp_id] = comp_data

        time.sleep(0.3)

    # Rebuild list sorted by date (newest first)
    result_data["competitions"] = sorted(
        existing_map.values(),
        key=lambda c: c["date"],
        reverse=True,
    )

    return result_data


def save(data):
    os.makedirs(DATA_DIR, exist_ok=True)
    out = os.path.join(DATA_DIR, "svemo_results.json")
    with open(out, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    total_entries = sum(
        sum(len(entries) for entries in c["classes"].values())
        for c in data["competitions"]
    )
    print(
        f"\n[svemo_results] Saved {len(data['competitions'])} competitions, "
        f"{total_entries} total entries to {out}"
    )
    return out


if __name__ == "__main__":
    import sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
    from scrape_tracker import should_scrape, mark_scraped

    force = "--force" in sys.argv

    if not should_scrape("svemo_results") and not force:
        print("[svemo_results] Skipping — scraped recently")
    else:
        data = scrape_all()
        if data and data["competitions"]:
            save(data)
            mark_scraped("svemo_results", count=len(data["competitions"]))
        else:
            print("[svemo_results] No results found")
