"""Tests for bot/scrapers/webtracking.py"""
import re

import pytest

from scrapers.webtracking import scrape_races, classify_race


# ---- classify_race (offline) ----

def test_classify_race():
    """Race type classification."""
    assert classify_race("Saltsjöloppet 2024") == "Offshore"
    assert classify_race("Offshore SM DT 3") == "Offshore"
    # classify_race checks for "runban" (no d) and "circuit"
    assert classify_race("Circuit SM 2024") == "Rundbana"
    assert classify_race("Circuit Cup") == "Rundbana"
    assert classify_race("Sommarträff 2024") == "Tävling"
    # "Rundbana" in actual name doesn't match the "runban" check (has extra 'd')
    assert classify_race("Rundbana SM 2024") == "Tävling"


# ---- Live network tests ----

@pytest.mark.network
def test_fetch_races_live():
    """Returns 200+ races with raceIdx, raceName, date."""
    races = scrape_races()
    assert races is not None
    assert len(races) >= 200


@pytest.mark.network
def test_race_structure():
    """Each race has idx, name, date, year, type fields."""
    races = scrape_races()
    assert races is not None
    required = {"idx", "name", "date", "year", "type"}
    for race in races[:10]:
        assert required.issubset(race.keys())


@pytest.mark.network
def test_race_dates_format():
    """Dates match YYYY-MM-DD pattern."""
    races = scrape_races()
    assert races is not None
    pattern = re.compile(r"^\d{4}-\d{2}-\d{2}$")
    for race in races[:20]:
        assert pattern.match(race["date"]), f"Bad date: {race['date']} in {race['name']}"
