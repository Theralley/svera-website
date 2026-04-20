#!/usr/bin/env python3
"""Fetch TikTok profile data for the SVERA social page.

Scrapes public profile info (nickname, bio, avatar, stats) from TikTok
using the SSR data embedded in the profile page. No API key needed.

Run: python3 bot/scrapers/social_tiktok.py [--force]

Outputs: bot/data/social_tiktok.json
"""
import json
import os
import re
import sys
import urllib.request
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BOT_DIR = os.path.dirname(SCRIPT_DIR)
DATA_DIR = os.path.join(BOT_DIR, "data")
OUTPUT_FILE = os.path.join(DATA_DIR, "social_tiktok.json")

# Accounts to track — add more as needed
# Format: (username, tag)
# Tags: news, team, driver, copilot
ACCOUNTS = [
    ("rasmushamren", "driver"),
]

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)


def fetch_profile(username):
    """Fetch profile data from TikTok SSR."""
    url = f"https://www.tiktok.com/@{username}"
    req = urllib.request.Request(url, headers={
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "en-US,en;q=0.9",
    })

    try:
        resp = urllib.request.urlopen(req, timeout=15)
        html = resp.read().decode("utf-8", errors="replace")
    except Exception as e:
        print(f"  [{username}] Fetch failed: {e}")
        return None

    # Extract SSR data
    match = re.search(
        r'<script id="__UNIVERSAL_DATA_FOR_REHYDRATION__"[^>]*>(.*?)</script>',
        html,
    )
    if not match:
        print(f"  [{username}] No SSR data found")
        return None

    try:
        data = json.loads(match.group(1))
    except json.JSONDecodeError:
        print(f"  [{username}] Failed to parse SSR JSON")
        return None

    ds = data.get("__DEFAULT_SCOPE__", {})
    user_detail = ds.get("webapp.user-detail", {})
    user_info = user_detail.get("userInfo", {})
    user = user_info.get("user", {})
    stats = user_info.get("stats", {})

    if not user.get("uniqueId"):
        print(f"  [{username}] No user data in SSR")
        return None

    profile = {
        "username": user.get("uniqueId", username),
        "nickname": user.get("nickname", username),
        "bio": user.get("signature", ""),
        "avatar": user.get("avatarLarger", ""),
        "verified": user.get("verified", False),
        "url": f"https://www.tiktok.com/@{username}",
        "stats": {
            "followers": stats.get("followerCount", 0),
            "following": stats.get("followingCount", 0),
            "likes": stats.get("heartCount", 0),
            "videos": stats.get("videoCount", 0),
        },
    }

    print(f"  [{username}] {profile['nickname']} — "
          f"{profile['stats']['followers']} followers, "
          f"{profile['stats']['videos']} videos, "
          f"{profile['stats']['likes']} likes")
    return profile


def scrape():
    """Fetch all tracked TikTok profiles."""
    print(f"[social_tiktok] Fetching {len(ACCOUNTS)} profile(s)...")

    profiles = []
    for username, tag in ACCOUNTS:
        profile = fetch_profile(username)
        if profile:
            profile["tag"] = tag
            profiles.append(profile)

    if not profiles:
        print("[social_tiktok] No profiles fetched")
        return False

    result = {
        "scraped_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "profiles": profiles,
    }

    os.makedirs(DATA_DIR, exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    print(f"[social_tiktok] Saved {len(profiles)} profile(s) to {OUTPUT_FILE}")
    return True


if __name__ == "__main__":
    scrape()
