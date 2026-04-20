#!/usr/bin/env python3
"""Fetch Facebook page data for the SVERA social page.

Uses the 'facebookexternalhit' User-Agent to get Open Graph metadata
from public Facebook pages (name, description, image, follower count).
No API key needed.

Run: python3 bot/scrapers/social_facebook.py

Outputs: bot/data/social_facebook.json
"""
import html as html_mod
import json
import os
import re
import urllib.request
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BOT_DIR = os.path.dirname(SCRIPT_DIR)
DATA_DIR = os.path.join(BOT_DIR, "data")
OUTPUT_FILE = os.path.join(DATA_DIR, "social_facebook.json")

# Facebook pages to track — add more as needed
# Format: (page_id, tag)
# Tags: news, team, driver, copilot
PAGES = [
    ("smugglerracing", "team"),
]

# Facebook serves OG metadata to its own crawler UA
USER_AGENT = "facebookexternalhit/1.1"


def decode_fb_text(text):
    """Decode Facebook's HTML entities (&#xa0; etc)."""
    text = html_mod.unescape(text)
    text = text.replace("\xa0", " ")
    return text.strip()


def parse_follower_count(description):
    """Extract follower/like count from OG description text."""
    # Patterns: "1 661 gillar", "1,661 likes", "2.3K likes"
    match = re.search(r'([\d\s\xa0,.]+)\s*(?:gillar|likes|like)', description)
    if match:
        num_str = match.group(1).replace(" ", "").replace("\xa0", "").replace(",", "").replace(".", "")
        try:
            return int(num_str)
        except ValueError:
            pass
    return 0


def fetch_page(page_id):
    """Fetch Facebook page metadata via OG tags."""
    url = f"https://www.facebook.com/{page_id}"
    req = urllib.request.Request(url, headers={
        "User-Agent": USER_AGENT,
        "Accept": "text/html",
    })

    try:
        resp = urllib.request.urlopen(req, timeout=15)
        html = resp.read().decode("utf-8", errors="replace")
    except Exception as e:
        print(f"  [{page_id}] Fetch failed: {e}")
        return None

    # Extract OG meta tags
    og = {}
    for match in re.finditer(
        r'<meta\s+(?:property|name)="(og:[^"]*?)"\s+content="([^"]*?)"', html
    ):
        og[match.group(1)] = decode_fb_text(match.group(2))

    name = og.get("og:title", page_id)
    description = og.get("og:description", "")
    image = og.get("og:image", "")

    if not name or name == page_id:
        print(f"  [{page_id}] No OG data found")
        return None

    # Parse follower count from description
    followers = parse_follower_count(description)

    # Clean description — remove the follower count prefix
    clean_desc = re.sub(
        r'^.*?(?:gillar|likes)\s*[·.]\s*\d+\s*(?:pratar om detta|talking about this)\s*[·.]\s*',
        '', description
    ).strip()
    if not clean_desc:
        clean_desc = description

    page_data = {
        "page_id": page_id,
        "name": name,
        "description": clean_desc,
        "image": image,
        "url": f"https://www.facebook.com/{page_id}",
        "stats": {
            "followers": followers,
        },
    }

    print(f"  [{page_id}] {name} — {followers} followers")
    return page_data


def scrape():
    """Fetch all tracked Facebook pages."""
    print(f"[social_facebook] Fetching {len(PAGES)} page(s)...")

    pages = []
    for page_id, tag in PAGES:
        page = fetch_page(page_id)
        if page:
            page["tag"] = tag
            pages.append(page)

    if not pages:
        print("[social_facebook] No pages fetched")
        return False

    result = {
        "scraped_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "pages": pages,
    }

    os.makedirs(DATA_DIR, exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    print(f"[social_facebook] Saved {len(pages)} page(s) to {OUTPUT_FILE}")
    return True


if __name__ == "__main__":
    scrape()
