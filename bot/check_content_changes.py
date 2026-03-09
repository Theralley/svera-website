#!/usr/bin/env python3
"""Detect content changes in kalender.html and resultat.html.

Compares file content (ignoring date stamps) against stored hashes.
If content changed, updates the 'Uppdaterad' date in the source notes.
Always updates 'Senast kontrollerad' to today.

Run: python3 bot/check_content_changes.py
Called by deploy.sh before uploading.
"""
import hashlib
import json
import os
import re
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)
HASH_FILE = os.path.join(SCRIPT_DIR, "data", "content_hashes.json")

# Patterns to strip before hashing (so date changes don't trigger false positives)
DATE_PATTERNS = [
    re.compile(r'Uppdaterad \d{4}-\d{2}-\d{2}'),
    re.compile(r'Senast kontrollerad \d{4}-\d{2}-\d{2}'),
    re.compile(r'Senast uppdaterad \d{4}-\d{2}-\d{2}'),
]

TRACKED_FILES = {
    "kalender.html": {
        "update_pattern": r'Uppdaterad \d{4}-\d{2}-\d{2}',
        "checked_pattern": r'Senast kontrollerad \d{4}-\d{2}-\d{2}',
    },
    "resultat.html": {
        # resultat.html only has footer date (handled by update_footer.py)
    },
}


def strip_dates(content):
    """Remove date stamps from content for comparison."""
    for pat in DATE_PATTERNS:
        content = pat.sub("DATE_PLACEHOLDER", content)
    return content


def compute_hash(content):
    """Compute MD5 hash of content with dates stripped."""
    cleaned = strip_dates(content)
    return hashlib.md5(cleaned.encode("utf-8")).hexdigest()


def load_hashes():
    if os.path.exists(HASH_FILE):
        try:
            with open(HASH_FILE) as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    return {}


def save_hashes(hashes):
    os.makedirs(os.path.dirname(HASH_FILE), exist_ok=True)
    with open(HASH_FILE, "w") as f:
        json.dump(hashes, f, indent=2)


def main():
    today = datetime.now().strftime("%Y-%m-%d")
    hashes = load_hashes()
    changes = []

    for filename, config in TRACKED_FILES.items():
        filepath = os.path.join(PROJECT_DIR, filename)
        if not os.path.exists(filepath):
            print(f"  Skipped: {filename} (not found)")
            continue

        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()

        current_hash = compute_hash(content)
        stored_hash = hashes.get(filename)
        content_changed = current_hash != stored_hash

        updated = False

        # Update "Uppdaterad" date if content actually changed
        if content_changed and config.get("update_pattern"):
            content = re.sub(
                config["update_pattern"],
                f"Uppdaterad {today}",
                content,
            )
            updated = True
            changes.append(filename)
            print(f"  {filename}: content changed — Uppdaterad → {today}")

        # Always update "Senast kontrollerad"
        if config.get("checked_pattern"):
            content = re.sub(
                config["checked_pattern"],
                f"Senast kontrollerad {today}",
                content,
            )
            updated = True

        if updated:
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(content)

        # Store new hash (computed from updated content)
        hashes[filename] = compute_hash(content)

        if not content_changed:
            print(f"  {filename}: no content change — Senast kontrollerad → {today}")

    save_hashes(hashes)

    if changes:
        print(f"\nContent changed in: {', '.join(changes)}")
    else:
        print(f"\nNo content changes detected. Dates checked: {today}")

    return len(changes)


if __name__ == "__main__":
    main()
