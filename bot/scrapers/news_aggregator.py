#!/usr/bin/env python3
"""Scrape latest powerboat racing news from 3 sources.

Sources:
  1. powerboatracingworld.com — WP REST API
  2. f1h2o.com — HTML scraping /news/YYYY
  3. powerboat.news — WP REST API

Saves to: bot/data/news_feed.json
"""
import json
import os
import re
import urllib.request
import urllib.error
from datetime import datetime
from html.parser import HTMLParser

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(os.path.dirname(SCRIPT_DIR), "data")
OUTPUT_FILE = os.path.join(DATA_DIR, "news_feed.json")

HEADERS = {
    "User-Agent": "SVERA-NewsBot/1.0 (svera.nu; powerboat racing archive)",
    "Accept": "application/json, text/html",
}
MAX_ARTICLES = 10  # per source


def fetch_url(url, accept="application/json"):
    """Fetch URL with proper headers. Returns string or None."""
    req = urllib.request.Request(url, headers={**HEADERS, "Accept": accept})
    try:
        resp = urllib.request.urlopen(req, timeout=30)
        return resp.read().decode("utf-8", errors="replace")
    except Exception as e:
        print(f"  [WARN] Failed to fetch {url}: {e}")
        return None


def strip_html(text):
    """Remove HTML tags from a string."""
    if not text:
        return ""
    clean = re.sub(r"<[^>]+>", "", text)
    clean = clean.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    clean = clean.replace("&#8217;", "'").replace("&#8216;", "'")
    clean = clean.replace("&#8220;", '"').replace("&#8221;", '"')
    clean = clean.replace("&nbsp;", " ").replace("&#8230;", "...")
    clean = re.sub(r"&[#\w]+;", "", clean)
    return clean.strip()


# ==============================================================
# Source 1: powerboatracingworld.com (WP REST API)
# ==============================================================
def scrape_prw():
    """Fetch latest articles from Powerboat Racing World via WP API."""
    print("[PRW] Fetching from powerboatracingworld.com...")
    url = f"https://powerboatracingworld.com/wp-json/wp/v2/posts?per_page={MAX_ARTICLES}&orderby=date&order=desc"
    raw = fetch_url(url)
    if not raw:
        return []

    try:
        posts = json.loads(raw)
    except json.JSONDecodeError:
        print("  [WARN] Invalid JSON from PRW")
        return []

    articles = []
    for p in posts:
        articles.append({
            "title": strip_html(p.get("title", {}).get("rendered", "")),
            "date": p.get("date", "")[:10],
            "url": p.get("link", ""),
            "excerpt": strip_html(p.get("excerpt", {}).get("rendered", ""))[:300],
            "source": "Powerboat Racing World",
            "source_short": "PRW",
        })
    print(f"  [PRW] Got {len(articles)} articles")
    return articles


# ==============================================================
# Source 2: f1h2o.com (HTML scraping)
# ==============================================================
def scrape_f1h2o():
    """Fetch latest articles from f1h2o.com using regex on structured HTML."""
    print("[F1H2O] Fetching from f1h2o.com...")
    year = datetime.now().year
    url = f"https://www.f1h2o.com/news/{year}"
    raw = fetch_url(url, accept="text/html")
    if not raw:
        url = f"https://www.f1h2o.com/news/{year - 1}"
        raw = fetch_url(url, accept="text/html")
    if not raw:
        return []

    articles = []
    # Parse structured divs: news-date, news-title, news-excerpt, news-readmore
    items = re.findall(
        r'<div class="news-item[^"]*">(.*?)</div>\s*</div>\s*</div>',
        raw, re.DOTALL
    )
    for item in items:
        date_m = re.search(r'news-date">(.*?)</div>', item)
        title_m = re.search(r'news-title">\s*(.*?)\s*</div>', item)
        excerpt_m = re.search(r'news-excerpt">\s*(.*?)\s*</div>', item, re.DOTALL)
        link_m = re.search(r'href="(/post/[^"]+)"', item)

        if not title_m or not link_m:
            continue

        # Parse date
        date_str = ""
        if date_m:
            try:
                ds = date_m.group(1).strip().replace(",", "")
                dt = datetime.strptime(ds, "%B %d %Y")
                date_str = dt.strftime("%Y-%m-%d")
            except ValueError:
                pass

        # Clean title
        title = strip_html(title_m.group(1)).strip()

        # Clean excerpt
        excerpt = ""
        if excerpt_m:
            excerpt = strip_html(excerpt_m.group(1)).strip()[:300]

        href = link_m.group(1)
        article_url = "https://www.f1h2o.com" + href

        articles.append({
            "title": title,
            "date": date_str,
            "url": article_url,
            "excerpt": excerpt,
            "source": "F1H2O",
            "source_short": "F1H2O",
        })

        if len(articles) >= MAX_ARTICLES:
            break

    print(f"  [F1H2O] Got {len(articles)} articles")
    return articles


# ==============================================================
# Source 3: powerboat.news (WP REST API)
# ==============================================================
def scrape_pbn():
    """Fetch latest articles from powerboat.news via WP API."""
    print("[PBN] Fetching from powerboat.news...")
    url = f"https://powerboat.news/wp-json/wp/v2/posts?per_page={MAX_ARTICLES}&orderby=date&order=desc"
    raw = fetch_url(url)
    if not raw:
        return []

    try:
        posts = json.loads(raw)
    except json.JSONDecodeError:
        print("  [WARN] Invalid JSON from PBN")
        return []

    articles = []
    for p in posts:
        articles.append({
            "title": strip_html(p.get("title", {}).get("rendered", "")),
            "date": p.get("date", "")[:10],
            "url": p.get("link", ""),
            "excerpt": strip_html(p.get("excerpt", {}).get("rendered", ""))[:300],
            "source": "Powerboat News",
            "source_short": "PBN",
        })
    print(f"  [PBN] Got {len(articles)} articles")
    return articles


# ==============================================================
# Main
# ==============================================================
def scrape_all():
    """Scrape all sources and save combined feed."""
    os.makedirs(DATA_DIR, exist_ok=True)

    all_articles = []
    all_articles.extend(scrape_prw())
    all_articles.extend(scrape_f1h2o())
    all_articles.extend(scrape_pbn())

    # Sort by date descending
    all_articles.sort(key=lambda a: a.get("date", ""), reverse=True)

    feed = {
        "scraped_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "total": len(all_articles),
        "articles": all_articles,
    }

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(feed, f, indent=2, ensure_ascii=False)

    print(f"\n[NEWS] Saved {len(all_articles)} articles to {OUTPUT_FILE}")
    return feed


if __name__ == "__main__":
    scrape_all()
