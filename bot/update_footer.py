#!/usr/bin/env python3
"""Update the 'Senast Uppdaterad' date in all HTML page footers.

Reads the most recent scrape date from scrape_log.json and stamps it
into the footer of every HTML file in the project root.

Run: python3 bot/update_footer.py
"""
import os
import json
import re
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)
LOG_FILE = os.path.join(SCRIPT_DIR, "scrape_log.json")

# Pattern to match the copyright + update line in footers
# Matches both with and without the "Senast uppdaterad" part
FOOTER_PATTERN = re.compile(
    r'&copy; 2026 SVERA — Svenska Evenemang &amp; Racerbåtsarkivet\..*?(?=\n)',
    re.DOTALL
)

def get_last_update_date():
    """Get the most recent scrape date from scrape_log.json."""
    if not os.path.exists(LOG_FILE):
        return datetime.now().strftime("%Y-%m-%d")

    try:
        with open(LOG_FILE) as f:
            log = json.load(f)
    except (json.JSONDecodeError, IOError):
        return datetime.now().strftime("%Y-%m-%d")

    latest = None
    for entry in log.values():
        ts = entry.get("last_scraped")
        if ts:
            dt = datetime.fromisoformat(ts)
            if latest is None or dt > latest:
                latest = dt

    if latest:
        return latest.strftime("%Y-%m-%d")
    return datetime.now().strftime("%Y-%m-%d")


def update_html_file(filepath, date_str):
    """Update the footer copyright line in a single HTML file."""
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    new_line = f"&copy; 2026 SVERA — Svenska Evenemang &amp; Racerbåtsarkivet. Senast uppdaterad {date_str}."

    updated = FOOTER_PATTERN.sub(new_line, content)

    if updated != content:
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(updated)
        return True
    return False


def main():
    date_str = get_last_update_date()
    print(f"Update date: {date_str}")

    html_files = [f for f in os.listdir(PROJECT_DIR) if f.endswith(".html")]
    updated = 0
    for fname in sorted(html_files):
        fpath = os.path.join(PROJECT_DIR, fname)
        if update_html_file(fpath, date_str):
            print(f"  Updated: {fname}")
            updated += 1
        else:
            print(f"  Skipped: {fname} (no match or already current)")

    print(f"\n{updated}/{len(html_files)} files updated with date {date_str}")
    return updated


if __name__ == "__main__":
    main()
