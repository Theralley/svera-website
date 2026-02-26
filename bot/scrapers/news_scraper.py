#!/usr/bin/env python3
"""DEPRECATED — use news_aggregator.py instead.

This scraper uses HTML parsing. The canonical pipeline is now:
  news_aggregator.py (WP REST APIs + HTML) -> news_feed.json -> build_news.py

Kept for reference only. Do not call from daemon or cron.
"""
import urllib.request
import json
import os
import re
import time
from html.parser import HTMLParser
from datetime import datetime, timedelta

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
USER_AGENT = "SVERA-Bot/1.0 (svera.nu; powerboat news aggregator)"
MAX_ARTICLES_PER_SOURCE = 15


def fetch_html(url, retries=3):
    """Fetch HTML content from a URL."""
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": USER_AGENT,
                "Accept": "text/html,application/xhtml+xml",
                "Accept-Language": "en-US,en;q=0.9,sv;q=0.8",
            })
            resp = urllib.request.urlopen(req, timeout=20)
            return resp.read().decode("utf-8", errors="replace")
        except Exception as e:
            if attempt == retries - 1:
                print(f"  ERROR fetching {url}: {e}")
                return None
            time.sleep(2)


# ── powerboatracingworld.com ──────────────────────────────────────────

class PRWParser(HTMLParser):
    """Parse powerboatracingworld.com article listings."""

    def __init__(self):
        super().__init__()
        self.articles = []
        self._in_title_section = False
        self._in_h = False
        self._in_a = False
        self._current = {}
        self._depth = 0

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        cls = attrs_dict.get("class", "")

        if "title-section" in cls:
            self._in_title_section = True
            self._current = {}

        if self._in_title_section and tag == "a":
            href = attrs_dict.get("href", "")
            if href and href.startswith("/"):
                self._current["url"] = "https://powerboatracingworld.com" + href
            elif href and href.startswith("http"):
                self._current["url"] = href
            self._in_a = True

        if self._in_title_section and self._in_a and tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            self._in_h = True
            self._current["title"] = ""

    def handle_data(self, data):
        if self._in_h:
            self._current["title"] = self._current.get("title", "") + data.strip()

    def handle_endtag(self, tag):
        if tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            self._in_h = False
        if tag == "a":
            self._in_a = False
        if tag == "div" and self._in_title_section:
            if self._current.get("title") and self._current.get("url"):
                self.articles.append(self._current)
            self._in_title_section = False
            self._current = {}


def scrape_prw():
    """Scrape powerboatracingworld.com."""
    print("[news] Scraping powerboatracingworld.com...")
    html = fetch_html("https://powerboatracingworld.com")
    if not html:
        return []

    parser = PRWParser()
    parser.feed(html)

    articles = []
    seen = set()
    for a in parser.articles:
        if a["url"] in seen:
            continue
        seen.add(a["url"])
        articles.append({
            "title": a["title"],
            "url": a["url"],
            "source": "Powerboat Racing World",
            "source_id": "prw",
            "date": None,
            "summary": "",
        })
        if len(articles) >= MAX_ARTICLES_PER_SOURCE:
            break

    # Try to fetch individual article pages for dates/summaries
    for art in articles[:8]:
        _enrich_article_prw(art)
        time.sleep(0.5)

    print(f"[news] PRW: {len(articles)} articles")
    return articles


def _enrich_article_prw(article):
    """Fetch individual article page to get date and summary."""
    html = fetch_html(article["url"])
    if not html:
        return

    # Look for date patterns
    date_match = re.search(
        r'(\w+ \d{1,2},?\s*\d{4})',
        html[:5000]
    )
    if date_match:
        article["date"] = _parse_date_en(date_match.group(1))

    # Look for meta description
    meta_match = re.search(
        r'<meta\s+(?:name|property)=["\'](?:og:description|description)["\']\s+content=["\']([^"\']+)',
        html, re.IGNORECASE
    )
    if meta_match:
        article["summary"] = meta_match.group(1).strip()[:300]


# ── f1h2o.com ─────────────────────────────────────────────────────────

def scrape_f1h2o():
    """Scrape f1h2o.com news."""
    print("[news] Scraping f1h2o.com...")
    html = fetch_html("https://www.f1h2o.com")
    if not html:
        return []

    articles = []
    seen = set()

    # Find /post/ links with nearby text
    pattern = re.compile(
        r'<a[^>]*href=["\'](/post/[^"\']+)["\'][^>]*>(.*?)</a>',
        re.DOTALL | re.IGNORECASE
    )
    for match in pattern.finditer(html):
        href = match.group(1)
        text = re.sub(r'<[^>]+>', '', match.group(2)).strip()
        if not text or len(text) < 10 or href in seen:
            continue
        seen.add(href)
        articles.append({
            "title": text,
            "url": "https://www.f1h2o.com" + href,
            "source": "F1H2O",
            "source_id": "f1h2o",
            "date": None,
            "summary": "",
        })
        if len(articles) >= MAX_ARTICLES_PER_SOURCE:
            break

    # Enrich top articles
    for art in articles[:8]:
        _enrich_article_f1h2o(art)
        time.sleep(0.5)

    print(f"[news] F1H2O: {len(articles)} articles")
    return articles


def _enrich_article_f1h2o(article):
    """Fetch individual F1H2O article for date and summary."""
    html = fetch_html(article["url"])
    if not html:
        return

    # Look for date
    date_match = re.search(
        r'(\w+ \d{1,2},?\s*\d{4})',
        html[:5000]
    )
    if date_match:
        article["date"] = _parse_date_en(date_match.group(1))

    # Meta description
    meta_match = re.search(
        r'<meta\s+(?:name|property)=["\'](?:og:description|description)["\']\s+content=["\']([^"\']+)',
        html, re.IGNORECASE
    )
    if meta_match:
        article["summary"] = meta_match.group(1).strip()[:300]


# ── powerboat.news ────────────────────────────────────────────────────

class PBNewsParser(HTMLParser):
    """Parse powerboat.news WordPress article listings."""

    def __init__(self):
        super().__init__()
        self.articles = []
        self._in_article = False
        self._in_entry_title = False
        self._in_entry_summary = False
        self._in_time = False
        self._in_a = False
        self._current = {}
        self._current_href = ""

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        cls = attrs_dict.get("class", "")

        if tag == "article":
            self._in_article = True
            self._current = {"title": "", "url": "", "date": None, "summary": ""}

        if self._in_article:
            if "entry-title" in cls:
                self._in_entry_title = True
            if "entry-summary" in cls or "entry-content" in cls:
                self._in_entry_summary = True

            if tag == "a" and self._in_entry_title:
                self._current["url"] = attrs_dict.get("href", "")
                self._in_a = True

            if tag == "time":
                dt = attrs_dict.get("datetime", "")
                if dt:
                    self._current["date"] = dt[:10]
                self._in_time = True

    def handle_data(self, data):
        if self._in_entry_title and self._in_a:
            self._current["title"] += data.strip()
        if self._in_entry_summary:
            self._current["summary"] += data.strip() + " "

    def handle_endtag(self, tag):
        if tag == "a":
            self._in_a = False
        if self._in_entry_title and tag in ("h1", "h2", "h3", "h4", "h5"):
            self._in_entry_title = False
        if tag == "div" and self._in_entry_summary:
            self._in_entry_summary = False
        if tag == "time":
            self._in_time = False
        if tag == "article" and self._in_article:
            self._in_article = False
            if self._current.get("title"):
                self._current["summary"] = self._current["summary"].strip()[:300]
                self.articles.append(self._current)


def scrape_powerboat_news():
    """Scrape powerboat.news."""
    print("[news] Scraping powerboat.news...")
    html = fetch_html("https://powerboat.news")
    if not html:
        return []

    parser = PBNewsParser()
    parser.feed(html)

    articles = []
    for a in parser.articles[:MAX_ARTICLES_PER_SOURCE]:
        articles.append({
            "title": a["title"],
            "url": a["url"],
            "source": "Powerboat News",
            "source_id": "pbnews",
            "date": a["date"],
            "summary": a["summary"],
        })

    print(f"[news] Powerboat News: {len(articles)} articles")
    return articles


# ── Helpers ────────────────────────────────────────────────────────────

MONTHS_EN = {
    "january": "01", "february": "02", "march": "03", "april": "04",
    "may": "05", "june": "06", "july": "07", "august": "08",
    "september": "09", "october": "10", "november": "11", "december": "12",
}


def _parse_date_en(date_str):
    """Parse English date string like 'February 2, 2026' to ISO date."""
    if not date_str:
        return None
    date_str = date_str.strip().replace(",", "")
    parts = date_str.split()
    if len(parts) >= 3:
        month = MONTHS_EN.get(parts[0].lower())
        if month:
            day = parts[1].zfill(2)
            year = parts[2]
            return f"{year}-{month}-{day}"
    return None


def save(articles):
    """Save scraped articles to JSON."""
    os.makedirs(DATA_DIR, exist_ok=True)
    out = os.path.join(DATA_DIR, "news_articles.json")
    with open(out, "w") as f:
        json.dump({
            "scraped_at": datetime.now().isoformat(timespec="seconds"),
            "count": len(articles),
            "articles": articles,
        }, f, ensure_ascii=False, indent=2)
    print(f"[news] Saved {len(articles)} articles to {out}")
    return out


def scrape_all():
    """Scrape all news sources and return combined list."""
    all_articles = []
    all_articles.extend(scrape_prw())
    all_articles.extend(scrape_f1h2o())
    all_articles.extend(scrape_powerboat_news())

    # Sort by date (newest first), articles without dates go last
    all_articles.sort(
        key=lambda a: a.get("date") or "0000-00-00",
        reverse=True,
    )

    return all_articles


if __name__ == "__main__":
    import sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
    from scrape_tracker import should_scrape, mark_scraped

    force = "--force" in sys.argv

    if not should_scrape("news_articles", force=force) and not force:
        print("[news] Skipping — scraped recently")
    else:
        articles = scrape_all()
        if articles:
            save(articles)
            mark_scraped("news_articles", count=len(articles))
        else:
            print("[news] No articles scraped")
