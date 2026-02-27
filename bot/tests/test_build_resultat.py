"""Tests for bot/builders/build_resultat.py"""
import pytest

from builders.build_resultat import sanitize_str, sanitize_data, load_json


# ---- sanitize_str ----

def test_sanitize_str():
    """Removes newlines, carriage returns, tabs."""
    # \n -> space, \r -> removed, \t -> space, then strip
    assert sanitize_str("hello\nworld\r\ttab") == "hello world tab"


def test_sanitize_str_non_string():
    """int/None passes through unchanged."""
    assert sanitize_str(42) == 42
    assert sanitize_str(None) is None


# ---- sanitize_data ----

def test_sanitize_data_recursive_dict():
    """Nested dict strings cleaned."""
    data = {"a": "line\none", "b": {"c": "tab\there"}}
    result = sanitize_data(data)
    assert "\n" not in result["a"]
    assert "\t" not in result["b"]["c"]


def test_sanitize_data_recursive_list():
    """Nested list strings cleaned."""
    data = ["hello\nworld", "tab\there"]
    result = sanitize_data(data)
    assert "\n" not in result[0]
    assert "\t" not in result[1]


def test_sanitize_data_mixed():
    """Dict with lists and nested dicts."""
    data = {
        "races": [{"name": "Race\n1"}, {"name": "Race\t2"}],
        "count": 5,
        "nested": {"val": "with\rnewline"},
    }
    result = sanitize_data(data)
    assert "\n" not in result["races"][0]["name"]
    assert "\t" not in result["races"][1]["name"]
    assert "\r" not in result["nested"]["val"]
    assert result["count"] == 5


# ---- load_json ----

def test_load_json_missing():
    """Returns None for non-existent file."""
    result = load_json("totally_nonexistent_file_xyz.json")
    assert result is None
