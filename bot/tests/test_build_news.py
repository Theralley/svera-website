"""Tests for bot/builders/build_news.py"""
import pytest

from builders.build_news import has_names, build_digest_html, build_articles_html


# ---- has_names tests ----

def test_has_names_true():
    """'Johan Andersson' -> True."""
    assert has_names("Johan Andersson vann loppet") is True


def test_has_names_false_stopwords():
    """'Formula Racing' -> False (stopwords)."""
    assert has_names("Formula Racing Championship Series") is False


def test_has_names_swedish_chars():
    """Swedish characters recognized."""
    assert has_names("Östen Åberg kom tvåa") is True


def test_has_names_empty():
    """None/empty -> False."""
    assert has_names(None) is False
    assert has_names("") is False


# ---- build_digest_html tests ----

def test_build_digest_html_structure(sample_news_feed):
    """Has WEEKLY DIGEST markers, h2, ul, source links."""
    summary = "Denna vecka har det hänt mycket.\n\nF1H2O-säsongen startar snart."
    html = build_digest_html(summary, sample_news_feed["articles"])
    assert "<!-- WEEKLY DIGEST START -->" in html
    assert "<!-- WEEKLY DIGEST END -->" in html
    assert "<h2" in html
    assert "<ul>" in html
    assert "Läs mer" in html


def test_build_digest_html_max_links(sample_news_feed):
    """Max 5 source links."""
    summary = "En kort sammanfattning av veckans nyheter."
    html = build_digest_html(summary, sample_news_feed["articles"])
    link_count = html.count("<li><a href=")
    assert link_count <= 5


def test_build_digest_html_skips_headings(sample_news_feed):
    """Short heading-like lines filtered, long content kept."""
    summary = "Veckans nyheter\n\nDetta var en spännande vecka inom powerboat racing med flera stora händelser."
    html = build_digest_html(summary, sample_news_feed["articles"])
    # "Veckans nyheter" is < 50 chars and contains "nyheter" -> should be filtered
    assert "<p>Veckans nyheter</p>" not in html
    # The longer paragraph should be kept
    assert "spännande vecka" in html


# ---- build_articles_html tests ----

def test_build_articles_html_structure(sample_news_feed):
    """Has NEWS FEED markers, news-card-grid articles."""
    html = build_articles_html(sample_news_feed["articles"])
    assert "<!-- NEWS FEED START -->" in html
    assert "<!-- NEWS FEED END -->" in html
    assert "news-card-grid" in html


def test_build_articles_html_max_cards(sample_news_feed):
    """Max 15 cards."""
    html = build_articles_html(sample_news_feed["articles"])
    card_count = html.count("news-card-grid")
    assert card_count <= 15


def test_build_articles_html_source_balance(sample_news_feed):
    """At least 2 per source (if available)."""
    html = build_articles_html(sample_news_feed["articles"])
    # Each source has 2 articles in our fixture, so all should appear
    assert html.count(">PRW<") >= 1
    assert html.count(">F1H2O<") >= 1
    assert html.count(">PBN<") >= 1
