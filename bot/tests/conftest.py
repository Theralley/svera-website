"""Shared fixtures for the SVERA test suite."""
import json
import os
import sys
import tempfile

import pytest

# Ensure bot/ is on sys.path so imports work
BOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BOT_DIR not in sys.path:
    sys.path.insert(0, BOT_DIR)

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")


def _load_fixture(name):
    with open(os.path.join(FIXTURES_DIR, name)) as f:
        return json.load(f)


@pytest.fixture
def tmp_data_dir(tmp_path):
    """Temporary directory for JSON test data."""
    return tmp_path


@pytest.fixture
def sample_races():
    return _load_fixture("webtracking_races.json")


@pytest.fixture
def sample_results():
    return _load_fixture("webtracking_results.json")


@pytest.fixture
def sample_svemo():
    return _load_fixture("svemo_results.json")


@pytest.fixture
def sample_news_feed():
    return _load_fixture("news_feed.json")


@pytest.fixture
def sample_calendar():
    return _load_fixture("svemo_calendar.json")


@pytest.fixture
def sample_uim():
    return _load_fixture("uim_calendar.json")
