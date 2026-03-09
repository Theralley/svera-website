#!/usr/bin/env python3
"""Scrape SVEMO public calendar from ta.svemo.se (no auth required).

Used as a secondary verification source for the TAM-based scraper.
Compares public data against TAM data and logs discrepancies.

Usage:
    python3 bot/scrapers/svemo_calendar_public.py [--force]
"""
import urllib.request
import json
import os
import re
from datetime import datetime
from html.parser import HTMLParser

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")

# Public ta.svemo.se URLs — no auth needed
BASE_URL = "https://ta.svemo.se/public/pages/competition/competitions.aspx"
BRANCHES = {
    "Offshore": f"{BASE_URL}?Branch=Offshore&Columns=CompetitionInfo,Branch,Name,Organizer,FromDateShort&Season={{year}}&pagesize=100&IsArrangeable=true&Datefilter=CUSTOM&ShowSearch=true&Style=SvemoWebsite",
    "Rundbana": f"{BASE_URL}?Branch=Rundbana&Columns=CompetitionInfo,Branch,Name,Organizer,FromDateShort&Season={{year}}&pagesize=100&IsArrangeable=true&Datefilter=CUSTOM&ShowSearch=true&Style=SvemoWebsite",
    "Aquabike": f"{BASE_URL}?Branch=Aquabike&Columns=CompetitionInfo,Branch,Name,Organizer,Arena,FromDateShort&Season={{year}}&pagesize=100&IsArrangeable=true&Datefilter=CUSTOM&ShowSearch=true&Style=SvemoWebsite",
}


class TelerikGridParser(HTMLParser):
    """Parse Telerik RadGrid HTML table to extract competition rows."""

    def __init__(self):
        super().__init__()
        self.in_table = False
        self.in_tbody = False
        self.in_row = False
        self.in_cell = False
        self.in_header = False
        self.current_row = []
        self.current_cell = ""
        self.rows = []
        self.current_link = None

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        cls = attrs_dict.get("class", "")

        if tag == "table" and "rgMasterTable" in cls:
            self.in_table = True
        if self.in_table and tag == "thead":
            self.in_header = True
        if self.in_table and tag == "tbody":
            self.in_tbody = True
            self.in_header = False
        if self.in_tbody and tag == "tr" and ("rgRow" in cls or "rgAltRow" in cls):
            self.in_row = True
            self.current_row = []
        if self.in_row and tag == "td":
            self.in_cell = True
            self.current_cell = ""
            self.current_link = None
        if self.in_cell and tag == "a":
            href = attrs_dict.get("href", "")
            if "CompetitionId" in href:
                self.current_link = href

    def handle_data(self, data):
        if self.in_cell:
            self.current_cell += data.strip()

    def handle_endtag(self, tag):
        if tag == "td" and self.in_cell:
            self.in_cell = False
            self.current_row.append({
                "text": self.current_cell.strip(),
                "link": self.current_link,
            })
        if tag == "tr" and self.in_row:
            self.in_row = False
            if self.current_row:
                self.rows.append(self.current_row)
        if tag == "tbody":
            self.in_tbody = False
        if tag == "table":
            self.in_table = False


def fetch_branch(branch, year):
    """Fetch competition list for a branch from the public page."""
    url = BRANCHES[branch].format(year=year)
    req = urllib.request.Request(url)
    req.add_header("User-Agent", "SVERA-Bot/1.0 (svera.nu)")

    try:
        resp = urllib.request.urlopen(req, timeout=20)
        html = resp.read().decode("utf-8", errors="replace")
    except Exception as e:
        print(f"[svemo_public] ERROR fetching {branch}: {e}")
        return []

    parser = TelerikGridParser()
    parser.feed(html)

    events = []
    for row in parser.rows:
        # Column order: FromDateShort, Organizer, Branch, Name, CompetitionInfo
        # (Aquabike has Arena between Organizer and FromDateShort)
        if len(row) < 4:
            continue

        # Extract CompetitionId from link
        comp_id = None
        for cell in row:
            if cell.get("link") and "CompetitionId=" in cell["link"]:
                match = re.search(r"CompetitionId=(\d+)", cell["link"])
                if match:
                    comp_id = match.group(1)

        # Find date cell (YYYY-MM-DD format)
        date_str = ""
        name = ""
        organizer = ""
        for cell in row:
            text = cell["text"]
            if re.match(r"\d{4}-\d{2}-\d{2}", text):
                date_str = text
            elif text == branch:
                continue  # Skip the branch column
            elif text == "Tävlingsinfo":
                continue  # Skip the link text
            elif not organizer:
                organizer = text
            elif not name:
                name = text

        if date_str and name:
            events.append({
                "name": name,
                "date": date_str,
                "organizer": organizer,
                "branch": branch,
                "competition_id": comp_id,
                "source": "public",
            })

    return events


def scrape_public():
    """Scrape all branches from public SVEMO pages."""
    year = str(datetime.now().year)
    all_events = []

    for branch in BRANCHES:
        print(f"[svemo_public] Fetching {branch} ({year})...")
        events = fetch_branch(branch, year)
        print(f"[svemo_public] {branch}: {len(events)} events")
        all_events.extend(events)

    all_events.sort(key=lambda e: e["date"])
    return all_events


def verify_against_tam(public_events):
    """Compare public data against TAM data and report discrepancies."""
    tam_path = os.path.join(DATA_DIR, "svemo_calendar.json")
    if not os.path.exists(tam_path):
        print("[svemo_public] No TAM data to verify against")
        return None

    with open(tam_path) as f:
        tam_events = json.load(f)

    # Build lookup sets by (date, branch, normalized_name)
    def normalize(name):
        return re.sub(r"\s+", " ", name.strip().lower())

    tam_set = {}
    for e in tam_events:
        key = (e["date"], e["branch"])
        tam_set.setdefault(key, []).append(normalize(e["name"]))

    public_set = {}
    for e in public_events:
        key = (e["date"], e["branch"])
        public_set.setdefault(key, []).append(normalize(e["name"]))

    discrepancies = []

    # Events in public but not in TAM
    for key, names in public_set.items():
        tam_names = tam_set.get(key, [])
        for name in names:
            if not any(name in tn or tn in name for tn in tam_names):
                discrepancies.append({
                    "type": "missing_in_tam",
                    "date": key[0],
                    "branch": key[1],
                    "name": name,
                })

    # Events in TAM but not in public
    for key, names in tam_set.items():
        pub_names = public_set.get(key, [])
        for name in names:
            if not any(name in pn or pn in name for pn in pub_names):
                discrepancies.append({
                    "type": "missing_in_public",
                    "date": key[0],
                    "branch": key[1],
                    "name": name,
                })

    return discrepancies


def save(events, discrepancies=None):
    """Save public events and verification report."""
    os.makedirs(DATA_DIR, exist_ok=True)

    out = os.path.join(DATA_DIR, "svemo_calendar_public.json")
    with open(out, "w") as f:
        json.dump(events, f, ensure_ascii=False, indent=2)
    print(f"[svemo_public] Saved {len(events)} events to {out}")

    if discrepancies is not None:
        report = os.path.join(DATA_DIR, "svemo_verification.json")
        result = {
            "verified_at": datetime.now().isoformat(timespec="seconds"),
            "public_count": len(events),
            "discrepancies": discrepancies,
            "status": "ok" if not discrepancies else "discrepancies_found",
        }
        with open(report, "w") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

        if discrepancies:
            print(f"[svemo_public] DISCREPANCIES FOUND ({len(discrepancies)}):")
            for d in discrepancies:
                print(f"  [{d['type']}] {d['date']} {d['branch']}: {d['name']}")
        else:
            print("[svemo_public] Verification OK — TAM and public data match")


if __name__ == "__main__":
    import sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
    from scrape_tracker import should_scrape, mark_scraped

    if not should_scrape("svemo_calendar_public") and "--force" not in sys.argv:
        print("[svemo_calendar_public] Skipping — checked recently")
    else:
        events = scrape_public()
        discrepancies = verify_against_tam(events)
        save(events, discrepancies)
        mark_scraped("svemo_calendar_public", count=len(events),
                     extra={"discrepancies": len(discrepancies) if discrepancies else 0})
