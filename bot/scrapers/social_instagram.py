#!/usr/bin/env python3
"""Fetch Instagram profile data for the SVERA social page.

Uses the 'facebookexternalhit' User-Agent to get Open Graph metadata
from public Instagram profiles (name, bio, image, followers, posts).
No API key needed.

Run: python3 bot/scrapers/social_instagram.py

Outputs: bot/data/social_instagram.json
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
OUTPUT_FILE = os.path.join(DATA_DIR, "social_instagram.json")

# Instagram accounts to track
# Format: (username, tag)
# Tags: news, team, driver, copilot
ACCOUNTS = [
    ("powerboatracingworld", "news"),
]

USER_AGENT = "facebookexternalhit/1.1"


def decode_text(text):
    """Decode HTML entities."""
    text = html_mod.unescape(text)
    return text.strip()


def parse_ig_description(description):
    """Parse Instagram OG description for stats.

    Format: '2,648 Followers, 730 Following, 338 Posts - See Instagram photos...'
    """
    stats = {"followers": 0, "following": 0, "posts": 0}

    m = re.search(r'([\d,.\s]+)\s*Followers', description)
    if m:
        stats["followers"] = int(m.group(1).replace(",", "").replace(".", "").replace(" ", ""))

    m = re.search(r'([\d,.\s]+)\s*Following', description)
    if m:
        stats["following"] = int(m.group(1).replace(",", "").replace(".", "").replace(" ", ""))

    m = re.search(r'([\d,.\s]+)\s*Posts', description)
    if m:
        stats["posts"] = int(m.group(1).replace(",", "").replace(".", "").replace(" ", ""))

    return stats


def fetch_profile(username):
    """Fetch Instagram profile data via OG tags."""
    url = f"https://www.instagram.com/{username}/"
    req = urllib.request.Request(url, headers={
        "User-Agent": USER_AGENT,
        "Accept": "text/html",
    })

    try:
        resp = urllib.request.urlopen(req, timeout=15)
        html = resp.read().decode("utf-8", errors="replace")
    except Exception as e:
        print(f"  [{username}] Fetch failed: {e}")
        return None

    # Extract OG meta tags
    og = {}
    for match in re.finditer(
        r'<meta\s+(?:property|name)="(og:[^"]*?)"\s+content="([^"]*?)"', html
    ):
        og[match.group(1)] = decode_text(match.group(2))

    title = og.get("og:title", "")
    description = og.get("og:description", "")
    image = og.get("og:image", "")

    if not title:
        print(f"  [{username}] No OG data found")
        return None

    # Extract display name from title: "Name (@handle) • Instagram photos and videos"
    name_match = re.match(r'^(.*?)\s*\(@', title)
    display_name = name_match.group(1).strip() if name_match else username

    # Parse stats from description
    stats = parse_ig_description(description)

    profile = {
        "username": username,
        "nickname": display_name,
        "image": image,
        "url": f"https://www.instagram.com/{username}/",
        "stats": stats,
    }

    print(f"  [{username}] {display_name} — "
          f"{stats['followers']} followers, "
          f"{stats['posts']} posts")
    return profile


def scrape():
    """Fetch all tracked Instagram profiles."""
    print(f"[social_instagram] Fetching {len(ACCOUNTS)} profile(s)...")

    profiles = []
    for username, tag in ACCOUNTS:
        profile = fetch_profile(username)
        if profile:
            profile["tag"] = tag
            profiles.append(profile)

    if not profiles:
        print("[social_instagram] No profiles fetched")
        return False

    result = {
        "scraped_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "profiles": profiles,
    }

    os.makedirs(DATA_DIR, exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    print(f"[social_instagram] Saved {len(profiles)} profile(s) to {OUTPUT_FILE}")
    return True


if __name__ == "__main__":
    scrape()
