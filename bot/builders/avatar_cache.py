#!/usr/bin/env python3
"""Download and cache social media avatars locally.

Social platforms (Facebook, Instagram, TikTok) sign their CDN avatar URLs
with expiration tokens (typically ~1 week). To avoid broken images, we
download each avatar and rewrite the profile data to reference a local
path under assets/social-avatars/{platform}/{username}.{ext}.

Call cache_avatars_for_platform(profiles, platform, handle_key, avatar_key)
before building HTML. It mutates each profile in-place, setting avatar_key
to the local path (e.g. "assets/social-avatars/tiktok/rasmushamren.jpg").
If download fails and a cached copy exists, it keeps the cached path.
If download fails with no cache, it falls back to a placeholder SVG.
"""
import hashlib
import os
import re
import urllib.request
import urllib.error

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BOT_DIR = os.path.dirname(SCRIPT_DIR)
PROJECT_DIR = os.path.dirname(BOT_DIR)
AVATAR_ROOT = os.path.join(PROJECT_DIR, "assets", "social-avatars")
PLACEHOLDER_REL = "assets/images/avatar-placeholder.svg"

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

SAFE_NAME_RE = re.compile(r"[^a-zA-Z0-9._-]+")


def _safe_filename(handle: str, url: str) -> str:
    """Derive a safe filename from handle + URL extension."""
    base = SAFE_NAME_RE.sub("_", handle.strip().lstrip("@/")) or "profile"
    # Guess extension from URL path (strip query string first)
    path = url.split("?", 1)[0]
    ext = os.path.splitext(path)[1].lower()
    if ext not in (".jpg", ".jpeg", ".png", ".webp", ".gif"):
        ext = ".jpg"
    return f"{base}{ext}"


def _download(url: str, dest: str) -> bool:
    """Download url to dest. Returns True on success."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = resp.read()
        if not data or len(data) < 200:
            return False
        tmp = dest + ".tmp"
        with open(tmp, "wb") as f:
            f.write(data)
        os.replace(tmp, dest)
        return True
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError) as e:
        print(f"  [avatar_cache] download failed: {e} for {url[:80]}")
        return False


def cache_avatar(url: str, platform: str, handle: str) -> str:
    """Download one avatar and return its project-relative local path.

    Falls back to existing cached file if download fails, or to placeholder.
    """
    if not url or not url.startswith(("http://", "https://")):
        # Already local or empty
        return url or PLACEHOLDER_REL

    platform_dir = os.path.join(AVATAR_ROOT, platform)
    os.makedirs(platform_dir, exist_ok=True)

    filename = _safe_filename(handle, url)
    abs_path = os.path.join(platform_dir, filename)
    rel_path = f"assets/social-avatars/{platform}/{filename}"

    # Check if we have a fresh copy (< 6 days old) — skip re-download
    import time
    if os.path.exists(abs_path):
        age = time.time() - os.path.getmtime(abs_path)
        if age < 6 * 86400:
            return rel_path

    ok = _download(url, abs_path)
    if ok:
        return rel_path
    if os.path.exists(abs_path):
        # Keep stale cache rather than breaking the page
        return rel_path
    return PLACEHOLDER_REL


def cache_avatars_for_platform(profiles, platform: str, handle_key: str,
                                avatar_key: str):
    """Mutate each profile: replace avatar_key URL with local path."""
    for p in profiles:
        handle = p.get(handle_key) or p.get("username") or p.get("name", "unknown")
        url = p.get(avatar_key, "")
        local = cache_avatar(url, platform, str(handle))
        p[avatar_key] = local


if __name__ == "__main__":
    # Self-test
    import json
    import sys
    data_dir = os.path.join(BOT_DIR, "data")
    for platform, fname, handle_key, avatar_key in [
        ("tiktok", "social_tiktok.json", "username", "avatar"),
        ("instagram", "social_instagram.json", "username", "image"),
        ("facebook", "social_facebook.json", "page_id", "image"),
    ]:
        path = os.path.join(data_dir, fname)
        if not os.path.exists(path):
            continue
        d = json.load(open(path))
        profiles = d.get("profiles") or d.get("pages") or []
        print(f"[{platform}] caching {len(profiles)} avatars...")
        cache_avatars_for_platform(profiles, platform, handle_key, avatar_key)
        for p in profiles:
            print(f"  {p.get(handle_key)}: {p.get(avatar_key)}")
