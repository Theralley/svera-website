"""Tests for bot/builders/build_champions.py"""
import pytest

from builders.build_champions import (
    normalize_class_name,
    is_sm_competition,
    should_skip_class,
    is_heat,
    is_total,
    get_class_base,
    select_classes,
    parse_position,
    calc_points,
    calc_dnf_points,
    SM_BONUS,
    BASE_POINTS,
)


# ---- normalize_class_name ----

def test_normalize_class_offshore_3a():
    """'Offshore 3A Total' -> 'A'."""
    assert normalize_class_name("Offshore 3A Total") == "A"


def test_normalize_class_3b():
    """'3B' -> 'B'."""
    assert normalize_class_name("3B") == "B"


def test_normalize_class_v90():
    """'V90 (Offshore, >16)' -> 'V90'."""
    assert normalize_class_name("V90 (Offshore, >16)") == "V90"


def test_normalize_class_single_letter():
    """'V' -> 'V24', 'W' -> 'W150'."""
    assert normalize_class_name("V") == "V24"
    assert normalize_class_name("W") == "W150"


# ---- is_sm_competition ----

def test_is_sm_competition():
    """'SM Deltavling 3' -> True, 'Saltsjoloppet' -> False."""
    assert is_sm_competition({"name": "SM/RM Offshore 2025 Deltävling 3"}) is True
    assert is_sm_competition({"name": "RM Offshore 2025"}) is True
    assert is_sm_competition({"name": "Saltsjöloppet 2025"}) is False


# ---- should_skip_class ----

def test_should_skip_class():
    """SM TABELL -> True, Classic Cup -> True, 3A -> False."""
    assert should_skip_class("SM TABELL 3B") is True
    assert should_skip_class("Classic Cup") is True
    assert should_skip_class("Knop Cupen") is True
    assert should_skip_class("Aquabike Offshore Runabout GP1") is True
    assert should_skip_class("foreign drivers") is True
    assert should_skip_class("3A") is False
    assert should_skip_class("Offshore 3B Total") is False


# ---- is_heat / is_total ----

def test_is_heat_is_total():
    """Heat/Total detection."""
    assert is_heat("Offshore 3A Heat 1") is True
    assert is_heat("3A Total") is False
    assert is_total("3A Total") is True
    assert is_total("Offshore 3A Heat 1") is False


# ---- get_class_base ----

def test_get_class_base():
    """Strip Heat/Total/Offshore prefixes."""
    assert get_class_base("Offshore 3A Total") == "3A"
    assert get_class_base("Offshore 3A Heat 1") == "3A"
    assert get_class_base("3B") == "3B"


# ---- parse_position ----

def test_parse_position():
    """Parse position strings."""
    assert parse_position("1") == (1, "ok")
    assert parse_position("15") == (15, "ok")
    assert parse_position("DSQ") == (None, "dsq")
    assert parse_position("DNF") == (None, "dnf")
    assert parse_position("DNS") == (None, "dns")
    assert parse_position("") == (None, "skip")


# ---- calc_points ----

def test_calc_points_sm():
    """pos=1, sm=True -> 22 (20+2 bonus)."""
    assert calc_points(1, 3, is_sm=True) == BASE_POINTS[1] + SM_BONUS  # 20 + 2 = 22


def test_calc_points_rm():
    """pos=1, sm=False -> 20 (no bonus)."""
    assert calc_points(1, 2, is_sm=False) == BASE_POINTS[1]  # 20


def test_calc_dnf_points():
    """SM -> 2, RM -> 0."""
    assert calc_dnf_points(is_sm=True) == 2
    assert calc_dnf_points(is_sm=False) == 0


# ---- select_classes ----

def test_select_classes_prefers_total(sample_svemo):
    """When Heat+Total exist, only Total selected."""
    comp = sample_svemo["competitions"][0]  # Has both Heat 1 and Total for 3A
    selected = select_classes(comp)

    # "Offshore 3A Total" should be selected, "Offshore 3A Heat 1" should not
    selected_names = list(selected.keys())
    assert any("Total" in n for n in selected_names)
    assert not any("Heat" in n for n in selected_names)

    # SM TABELL and Classic Cup should be skipped
    for name in selected_names:
        assert "SM TABELL" not in name
        assert "Classic" not in name
