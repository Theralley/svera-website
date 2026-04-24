#!/usr/bin/env python3
"""Build social.html — inject social media profiles grouped by platform.

Reads: bot/data/social_tiktok.json, social_facebook.json, social_instagram.json
Updates: social.html — replaces content between SOCIAL FEED markers

Profiles are grouped into 3 platform sections (Facebook, Instagram, TikTok)
and each profile card shows a tag (News, Team, Driver, Co-pilot).
"""
import json
import os
import re
from html import escape

try:
    from .avatar_cache import cache_avatars_for_platform
except ImportError:
    from avatar_cache import cache_avatars_for_platform

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BOT_DIR = os.path.dirname(SCRIPT_DIR)
PROJECT_DIR = os.path.dirname(BOT_DIR)
DATA_DIR = os.path.join(BOT_DIR, "data")
TIKTOK_FILE = os.path.join(DATA_DIR, "social_tiktok.json")
FACEBOOK_FILE = os.path.join(DATA_DIR, "social_facebook.json")
INSTAGRAM_FILE = os.path.join(DATA_DIR, "social_instagram.json")
SOCIAL_FILE = os.path.join(PROJECT_DIR, "social.html")

TAG_LABELS = {
    "news": "Nyheter",
    "team": "Team",
    "driver": "F\u00f6rare",
    "copilot": "Co-pilot",
}

TAG_COLORS = {
    "news": "#e67e22",
    "team": "#2980b9",
    "driver": "#27ae60",
    "copilot": "#8e44ad",
}


def format_number(n):
    """Format large numbers: 1234 -> '1.2K', 1234567 -> '1.2M'."""
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}K"
    return str(n)


def tag_html(tag):
    """Generate a small tag badge."""
    label = escape(TAG_LABELS.get(tag, tag.title()))
    color = TAG_COLORS.get(tag, "#95a5a6")
    return (
        f'<span class="social-tag" style="background:{color};">'
        f'{label}</span>'
    )


def build_card(name, handle, handle_prefix, avatar, bio, url, stats_html,
               platform_class, button_text, tag=None):
    """Generate a single profile card."""
    card = (
        f'      <div class="social-profile-card">\n'
        f'        <div class="social-profile-header">\n'
        f'          <img class="social-avatar" src="{escape(avatar)}" alt="{escape(name)}" loading="lazy">\n'
        f'          <div class="social-profile-info">\n'
        f'            <h3>{escape(name)}'
    )
    if tag:
        card += f' {tag_html(tag)}'
    card += (
        f'</h3>\n'
        f'            <a href="{escape(url)}" target="_blank" rel="noopener" class="social-handle">{handle_prefix}{escape(handle)}</a>\n'
        f'          </div>\n'
        f'          <span class="social-platform-tag {platform_class}">{platform_class.title()}</span>\n'
        f'        </div>\n'
    )
    if bio:
        card += f'        <p class="social-bio">{escape(bio)}</p>\n'
    card += (
        f'        <div class="social-stats">\n'
        f'{stats_html}'
        f'        </div>\n'
        f'        <a href="{escape(url)}" target="_blank" rel="noopener" class="social-visit-btn {platform_class}">{button_text} &rarr;</a>\n'
        f'      </div>\n'
    )
    return card


def build_facebook_cards(pages):
    """Generate cards for Facebook pages."""
    cards = ""
    for p in pages:
        stats = p.get("stats", {})
        stats_html = f'          <span><strong>{format_number(stats.get("followers", 0))}</strong> f&ouml;ljare</span>\n'
        cards += build_card(
            name=p["name"],
            handle=p["page_id"],
            handle_prefix="/",
            avatar=p.get("image", ""),
            bio=p.get("description", ""),
            url=p["url"],
            stats_html=stats_html,
            platform_class="facebook",
            button_text="Bes&ouml;k p&aring; Facebook",
            tag=p.get("tag"),
        )
    return cards


def build_instagram_cards(profiles):
    """Generate cards for Instagram profiles."""
    cards = ""
    for p in profiles:
        stats = p.get("stats", {})
        stats_html = (
            f'          <span><strong>{format_number(stats.get("followers", 0))}</strong> f&ouml;ljare</span>\n'
            f'          <span><strong>{stats.get("posts", 0)}</strong> inl&auml;gg</span>\n'
        )
        cards += build_card(
            name=p["nickname"],
            handle=p["username"],
            handle_prefix="@",
            avatar=p.get("image", ""),
            bio="",
            url=p["url"],
            stats_html=stats_html,
            platform_class="instagram",
            button_text="Se p&aring; Instagram",
            tag=p.get("tag"),
        )
    return cards


def build_tiktok_cards(profiles):
    """Generate cards for TikTok profiles."""
    cards = ""
    for p in profiles:
        stats = p.get("stats", {})
        stats_html = (
            f'          <span><strong>{format_number(stats.get("followers", 0))}</strong> f&ouml;ljare</span>\n'
            f'          <span><strong>{format_number(stats.get("likes", 0))}</strong> likes</span>\n'
            f'          <span><strong>{stats.get("videos", 0)}</strong> videos</span>\n'
        )
        cards += build_card(
            name=p["nickname"],
            handle=p["username"],
            handle_prefix="@",
            avatar=p.get("avatar", ""),
            bio=p.get("bio", ""),
            url=p["url"],
            stats_html=stats_html,
            platform_class="tiktok",
            button_text="Se videos p&aring; TikTok",
            tag=p.get("tag"),
        )
    return cards


def build_section(title, icon_class, cards_html):
    """Wrap cards in a platform section with heading."""
    return (
        f'      <div class="social-platform-section">\n'
        f'        <h3 class="social-section-title"><span class="social-section-icon {icon_class}"></span>{title}</h3>\n'
        f'        <div class="social-feed-list">\n'
        f'{cards_html}'
        f'        </div>\n'
        f'      </div>\n'
    )


def build():
    """Build social feed HTML and inject into social.html."""
    if not os.path.exists(SOCIAL_FILE):
        print("[build_social] social.html not found")
        return False

    # Load data
    fb_pages = []
    if os.path.exists(FACEBOOK_FILE):
        with open(FACEBOOK_FILE) as f:
            fb_pages = json.load(f).get("pages", [])
        print(f"[build_social] Loaded {len(fb_pages)} Facebook page(s)")

    ig_profiles = []
    if os.path.exists(INSTAGRAM_FILE):
        with open(INSTAGRAM_FILE) as f:
            ig_profiles = json.load(f).get("profiles", [])
        print(f"[build_social] Loaded {len(ig_profiles)} Instagram profile(s)")

    tiktok_profiles = []
    if os.path.exists(TIKTOK_FILE):
        with open(TIKTOK_FILE) as f:
            tiktok_profiles = json.load(f).get("profiles", [])
        print(f"[build_social] Loaded {len(tiktok_profiles)} TikTok profile(s)")

    # Cache avatars locally so signed CDN URLs cannot expire on us
    if fb_pages:
        cache_avatars_for_platform(fb_pages, "facebook", "page_id", "image")
    if ig_profiles:
        cache_avatars_for_platform(ig_profiles, "instagram", "username", "image")
    if tiktok_profiles:
        cache_avatars_for_platform(tiktok_profiles, "tiktok", "username", "avatar")

    if not fb_pages and not ig_profiles and not tiktok_profiles:
        print("[build_social] No social data to display")
        return False

    # Build sections per platform — TikTok first (video), then Facebook, then Instagram
    feed_html = '    <!-- SOCIAL FEED START -->\n'

    if tiktok_profiles:
        feed_html += build_section("TikTok", "tiktok",
                                   build_tiktok_cards(tiktok_profiles))

    if fb_pages:
        feed_html += build_section("Facebook", "facebook",
                                   build_facebook_cards(fb_pages))

    if ig_profiles:
        feed_html += build_section("Instagram", "instagram",
                                   build_instagram_cards(ig_profiles))

    feed_html += '    <!-- SOCIAL FEED END -->'

    # Read and replace
    with open(SOCIAL_FILE) as f:
        html = f.read()

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
