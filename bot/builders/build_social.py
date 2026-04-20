#!/usr/bin/env python3
"""Build social.html — inject social media profile cards into the feed section.

Reads: bot/data/social_tiktok.json, bot/data/social_facebook.json
Updates: social.html — replaces content between SOCIAL FEED markers
"""
import json
import os
import re
from html import escape

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BOT_DIR = os.path.dirname(SCRIPT_DIR)
PROJECT_DIR = os.path.dirname(BOT_DIR)
DATA_DIR = os.path.join(BOT_DIR, "data")
TIKTOK_FILE = os.path.join(DATA_DIR, "social_tiktok.json")
FACEBOOK_FILE = os.path.join(DATA_DIR, "social_facebook.json")
SOCIAL_FILE = os.path.join(PROJECT_DIR, "social.html")


def format_number(n):
    """Format large numbers: 1234 -> '1.2K', 1234567 -> '1.2M'."""
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}K"
    return str(n)


def build_facebook_cards(pages):
    """Generate HTML cards for Facebook pages."""
    cards = ""
    for p in pages:
        name = escape(p["name"])
        page_id = escape(p["page_id"])
        description = escape(p.get("description", ""))
        image = escape(p.get("image", ""))
        url = escape(p["url"])
        stats = p.get("stats", {})

        followers = format_number(stats.get("followers", 0))

        cards += (
            f'      <div class="social-profile-card">\n'
            f'        <div class="social-profile-header">\n'
            f'          <img class="social-avatar" src="{image}" alt="{name}" loading="lazy">\n'
            f'          <div class="social-profile-info">\n'
            f'            <h3>{name}</h3>\n'
            f'            <a href="{url}" target="_blank" rel="noopener" class="social-handle">/{page_id}</a>\n'
            f'          </div>\n'
            f'          <span class="social-platform-tag facebook">Facebook</span>\n'
            f'        </div>\n'
        )
        if description:
            cards += f'        <p class="social-bio">{description}</p>\n'
        cards += (
            f'        <div class="social-stats">\n'
            f'          <span><strong>{followers}</strong> f&ouml;ljare</span>\n'
            f'        </div>\n'
            f'        <a href="{url}" target="_blank" rel="noopener" class="social-visit-btn facebook">Bes&ouml;k p&aring; Facebook &rarr;</a>\n'
            f'      </div>\n'
        )

    return cards


def build_tiktok_cards(profiles):
    """Generate HTML cards for TikTok profiles."""
    cards = ""
    for p in profiles:
        username = escape(p["username"])
        nickname = escape(p["nickname"])
        bio = escape(p.get("bio", ""))
        avatar = escape(p.get("avatar", ""))
        url = escape(p["url"])
        stats = p.get("stats", {})

        followers = format_number(stats.get("followers", 0))
        likes = format_number(stats.get("likes", 0))
        videos = stats.get("videos", 0)

        cards += (
            f'      <div class="social-profile-card">\n'
            f'        <div class="social-profile-header">\n'
            f'          <img class="social-avatar" src="{avatar}" alt="{nickname}" loading="lazy">\n'
            f'          <div class="social-profile-info">\n'
            f'            <h3>{nickname}</h3>\n'
            f'            <a href="{url}" target="_blank" rel="noopener" class="social-handle">@{username}</a>\n'
            f'          </div>\n'
            f'          <span class="social-platform-tag tiktok">TikTok</span>\n'
            f'        </div>\n'
        )
        if bio:
            cards += f'        <p class="social-bio">{bio}</p>\n'
        cards += (
            f'        <div class="social-stats">\n'
            f'          <span><strong>{followers}</strong> f&ouml;ljare</span>\n'
            f'          <span><strong>{likes}</strong> likes</span>\n'
            f'          <span><strong>{videos}</strong> videos</span>\n'
            f'        </div>\n'
            f'        <a href="{url}" target="_blank" rel="noopener" class="social-visit-btn tiktok">Se videos p&aring; TikTok &rarr;</a>\n'
            f'      </div>\n'
        )

    return cards


def build():
    """Build social feed HTML and inject into social.html."""
    if not os.path.exists(SOCIAL_FILE):
        print("[build_social] social.html not found")
        return False

    # Load Facebook data
    fb_pages = []
    if os.path.exists(FACEBOOK_FILE):
        with open(FACEBOOK_FILE) as f:
            data = json.load(f)
        fb_pages = data.get("pages", [])
        print(f"[build_social] Loaded {len(fb_pages)} Facebook page(s)")

    # Load TikTok data
    tiktok_profiles = []
    if os.path.exists(TIKTOK_FILE):
        with open(TIKTOK_FILE) as f:
            data = json.load(f)
        tiktok_profiles = data.get("profiles", [])
        print(f"[build_social] Loaded {len(tiktok_profiles)} TikTok profile(s)")

    if not fb_pages and not tiktok_profiles:
        print("[build_social] No social data to display")
        return False

    # Build feed HTML — Facebook first, then TikTok
    feed_html = '    <!-- SOCIAL FEED START -->\n'
    feed_html += '    <div class="social-feed-list">\n'
    feed_html += build_facebook_cards(fb_pages)
    feed_html += build_tiktok_cards(tiktok_profiles)
    feed_html += '    </div>\n'
    feed_html += '    <!-- SOCIAL FEED END -->'

    # Read social.html
    with open(SOCIAL_FILE) as f:
        html = f.read()

    # Replace feed section
    pattern = r"    <!-- SOCIAL FEED START -->.*?<!-- SOCIAL FEED END -->"
    if re.search(pattern, html, re.DOTALL):
        html = re.sub(pattern, feed_html, html, count=1, flags=re.DOTALL)
        print("[build_social] Replaced social feed in social.html")
    else:
        print("[build_social] WARNING: Could not find SOCIAL FEED markers")
        return False

    with open(SOCIAL_FILE, "w") as f:
        f.write(html)

    print("[build_social] Done!")
    return True


if __name__ == "__main__":
    build()
