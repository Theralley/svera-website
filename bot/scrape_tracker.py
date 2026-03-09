#!/usr/bin/env python3
"""Track scrape timestamps to avoid re-scraping unchanged data.

Usage:
    from scrape_tracker import should_scrape, mark_scraped

    if should_scrape("webtracking_races"):
        # do scrape
        mark_scraped("webtracking_races")

Log is stored in bot/scrape_log.json with structure:
    { "source_name": { "last_scraped": "2026-02-25T06:00:00", "count": 277, "status": "ok" } }
"""
import json
import os
from datetime import datetime, timedelta

LOG_FILE = os.path.join(os.path.dirname(__file__), "scrape_log.json")

# Default intervals (hours) before re-scraping each source
INTERVALS = {
    "webtracking_races": 48,        # Every 2 days
    "webtracking_results": 48,      # Every 2 days
    "webtracking_results_recent": 48, # Every 2 days
    "svemo_calendar": 48,           # Every 2 days
    "uim_calendar": 48,             # Every 2 days
    "svemo_results": 48,            # Every 2 days
    "svemo_calendar_public": 48,     # Every 2 days — public verification
    "svemo_rules": 168,             # Weekly — rules change very rarely
    "news_articles": 168,           # Weekly — news aggregation
    "news_weekly_summary": 168,     # Weekly — AI summary
}


def _load_log():
    if os.path.exists(LOG_FILE):
        try:
            with open(LOG_FILE) as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return {}
    return {}


def _save_log(log):
    with open(LOG_FILE, "w") as f:
        json.dump(log, f, indent=2, ensure_ascii=False)


def should_scrape(source, force=False):
    """Check if a source needs re-scraping based on time interval."""
    if force:
        return True

    log = _load_log()
    entry = log.get(source)
    if not entry or "last_scraped" not in entry:
        return True

    interval_hours = INTERVALS.get(source, 24)
    last = datetime.fromisoformat(entry["last_scraped"])
    return datetime.now() - last > timedelta(hours=interval_hours)


def mark_scraped(source, count=0, status="ok", extra=None):
    """Record that a source was successfully scraped."""
    log = _load_log()
    entry = {
        "last_scraped": datetime.now().isoformat(timespec="seconds"),
        "count": count,
        "status": status,
    }
    if extra:
        entry.update(extra)
    log[source] = entry
    _save_log(log)


def get_last_scraped(source):
    """Get the last scrape timestamp for a source, or None."""
    log = _load_log()
    entry = log.get(source)
    if entry and "last_scraped" in entry:
        return datetime.fromisoformat(entry["last_scraped"])
    return None


def print_status():
    """Print current scrape status for all tracked sources."""
    log = _load_log()
    if not log:
        print("No scrape history yet.")
        return

    print(f"{'Source':<30} {'Last scraped':<22} {'Count':>6} {'Status':<8} {'Stale?'}")
    print("-" * 85)
    for source, entry in sorted(log.items()):
        last = entry.get("last_scraped", "never")
        count = entry.get("count", "?")
        status = entry.get("status", "?")
        stale = "YES" if should_scrape(source) else "no"
        print(f"{source:<30} {last:<22} {count:>6} {status:<8} {stale}")


if __name__ == "__main__":
    print_status()
