"""Tests for bot/scrapers/webtracking_results.py"""
import pytest

from scrapers.webtracking_results import compute_results, fetch_all_results, EXCLUDED_CLASSES


# ---- compute_results (offline) ----

def test_compute_results_classes(sample_results):
    """Computed results have expected classes, exclude PB/R."""
    # sample_results has race 284 with classes A and B
    race_284 = sample_results.get("284", {})
    assert "A" in race_284
    assert "B" in race_284
    for cls in race_284:
        assert cls not in EXCLUDED_CLASSES


def test_result_structure(sample_results):
    """Each result has nr, p (pilot), laps, t (time_str)."""
    for race_id, classes in sample_results.items():
        for cls_name, entries in classes.items():
            for entry in entries:
                assert "nr" in entry
                assert "p" in entry
                assert "laps" in entry
                assert "t" in entry


def test_winner_has_laps(sample_results):
    """Class A winner has laps > 0."""
    race_284 = sample_results.get("284", {})
    class_a = race_284.get("A", [])
    assert len(class_a) > 0
    winner = class_a[0]
    assert winner["laps"] > 0


# ---- Live network tests ----

@pytest.mark.network
def test_fetch_known_race():
    """Race 284 returns 50+ records."""
    records = fetch_all_results(284)
    assert len(records) >= 50
    computed = compute_results(records)
    assert len(computed) > 0
    # PB and R should be excluded
    for cls in computed:
        assert cls not in EXCLUDED_CLASSES
