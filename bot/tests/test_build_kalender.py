"""Tests for bot/builders/build_kalender.py"""
import pytest

from builders.build_kalender import build_svemo_table, build_uim_table, MONTHS_SV


# ---- build_svemo_table ----

def test_build_svemo_table_empty():
    """No events -> 'Inga kommande' message."""
    result = build_svemo_table([])
    assert "Inga kommande" in result


def test_build_svemo_table_badges(sample_calendar):
    """Offshore -> badge-offshore, Rundbana -> badge-rundbana."""
    result = build_svemo_table(sample_calendar)
    assert "badge-offshore" in result
    assert "badge-rundbana" in result


def test_build_svemo_table_future_only(sample_calendar):
    """Past events filtered out."""
    result = build_svemo_table(sample_calendar)
    # "Old Event 2025" has date 2025-09-27 which is in the past
    assert "Old Event 2025" not in result
    # Future events should be present
    assert "Saltsjoloppet 2026" in result


# ---- build_uim_table ----

def test_build_uim_table_empty():
    """Empty -> colspan message."""
    result = build_uim_table([])
    assert "colspan" in result
    assert "Inga internationella" in result


def test_build_uim_table_rows(sample_uim):
    """Generates <tr> with venue/country/discipline."""
    result = build_uim_table(sample_uim)
    assert "<tr" in result
    assert "Sharjah" in result
    assert "UAE" in result
    assert "Offshore" in result


# ---- MONTHS_SV ----

def test_months_sv_complete():
    """All 12 months in MONTHS_SV dict."""
    assert len(MONTHS_SV) == 12
    for i in range(1, 13):
        assert i in MONTHS_SV
    assert MONTHS_SV[1] == "januari"
    assert MONTHS_SV[12] == "december"
