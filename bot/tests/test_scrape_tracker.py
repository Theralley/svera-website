"""Tests for bot/scrape_tracker.py"""
import json
import os
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest

import scrape_tracker


@pytest.fixture
def tracker_env(tmp_path):
    """Patch LOG_FILE to use a temp file."""
    log_file = str(tmp_path / "scrape_log.json")
    with patch.object(scrape_tracker, "LOG_FILE", log_file):
        yield log_file


def test_mark_and_check(tracker_env):
    """mark_scraped then should_scrape returns False."""
    scrape_tracker.mark_scraped("news_articles", count=10)
    assert scrape_tracker.should_scrape("news_articles") is False


def test_force_always_true(tracker_env):
    """should_scrape(force=True) always returns True."""
    scrape_tracker.mark_scraped("news_articles", count=10)
    assert scrape_tracker.should_scrape("news_articles", force=True) is True


def test_unknown_source_needs_scrape(tracker_env):
    """New/unknown source returns True."""
    assert scrape_tracker.should_scrape("brand_new_source") is True


def test_get_last_scraped_none(tracker_env):
    """Unknown source returns None."""
    assert scrape_tracker.get_last_scraped("nonexistent") is None


def test_get_last_scraped_returns_datetime(tracker_env):
    """Marked source returns a datetime."""
    scrape_tracker.mark_scraped("webtracking_races", count=200)
    result = scrape_tracker.get_last_scraped("webtracking_races")
    assert isinstance(result, datetime)


def test_intervals_honored(tracker_env):
    """Stale source (past interval) should return True."""
    # Write a log entry 25 hours ago (webtracking_races interval = 24h)
    log_file = tracker_env
    old_time = (datetime.now() - timedelta(hours=25)).isoformat(timespec="seconds")
    log_data = {"webtracking_races": {"last_scraped": old_time, "count": 100, "status": "ok"}}
    with open(log_file, "w") as f:
        json.dump(log_data, f)
    assert scrape_tracker.should_scrape("webtracking_races") is True


def test_corrupted_log_file(tracker_env):
    """Invalid JSON in log file -> graceful fallback."""
    log_file = tracker_env
    with open(log_file, "w") as f:
        f.write("{invalid json!!")
    # Should not crash, should return True (needs scrape)
    assert scrape_tracker.should_scrape("news_articles") is True


def test_missing_log_file(tracker_env):
    """No log file -> all sources need scraping."""
    # tracker_env creates a path but doesn't write the file
    assert scrape_tracker.should_scrape("news_articles") is True
    assert scrape_tracker.should_scrape("webtracking_races") is True
