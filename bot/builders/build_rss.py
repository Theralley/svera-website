#!/usr/bin/env python3
"""Build RSS feed from SVERA's own news (index.html) + international news (news_feed.json).

Produces two feeds:
  rss.xml          — SVERA's own Swedish news (from index.html "Nyheter från SVERA")
  rss-intl.xml     — International news (from news_feed.json)
"""
import json
import os
import re
from datetime import datetime, timezone
from html import escape, unescape

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BOT_DIR = os.path.dirname(SCRIPT_DIR)
PROJECT_DIR = os.path.dirname(BOT_DIR)
DATA_DIR = os.path.join(BOT_DIR, "data")
FEED_FILE = os.path.join(DATA_DIR, "news_feed.json")
INDEX_FILE = os.path.join(PROJECT_DIR, "index.html")
RSS_FILE = os.path.join(PROJECT_DIR, "rss.xml")
RSS_INTL_FILE = os.path.join(PROJECT_DIR, "rss-intl.xml")

SITE_URL = "https://svera.nu"


def strip_html(text):
    """Remove HTML tags and decode entities."""
    text = re.sub(r"<[^>]+>", "", text)
    return unescape(text).strip()


def parse_svera_news():
    """Extract news cards from index.html."""
    if not os.path.exists(INDEX_FILE):
        print("ERROR: index.html not found")
        return []

    with open(INDEX_FILE, "r", encoding="utf-8") as f:
        html = f.read()

    # Extract the news section
    match = re.search(r'<main id="nyheter">(.*?)</main>', html, re.DOTALL)
    if not match:
        print("ERROR: Could not find nyheter section in index.html")
        return []

    section = match.group(1)

    # Parse each news-card
    articles = []
    cards = re.findall(r'<article class="news-card"[^>]*>(.*?)</article>', section, re.DOTALL)

    for card in cards:
        # Category
        cat_match = re.search(r'<span class="category"[^>]*>(.*?)</span>', card)
        category = strip_html(cat_match.group(1)) if cat_match else ""

        # Date
        date_match = re.search(r'<span class="news-date">([\d-]+)</span>', card)
        date = date_match.group(1) if date_match else ""

        # Title
        title_match = re.search(r'<h3>(.*?)</h3>', card, re.DOTALL)
        title = strip_html(title_match.group(1)) if title_match else ""

        # Body paragraphs (skip source lines)
        paragraphs = re.findall(r'<p(?:\s[^>]*)?>(.*?)</p>', card, re.DOTALL)
        body_parts = []
        for p in paragraphs:
            text = strip_html(p)
            if text.startswith("Källa:") or text.startswith("K\u00e4lla:"):
                continue
            body_parts.append(text)
        body = " ".join(body_parts)[:400]

        # Link (if any)
        link_match = re.search(r'<a href="([^"]+)"[^>]*class="read-more"', card)
        link = link_match.group(1) if link_match else ""
        if link and not link.startswith("http"):
            link = f"{SITE_URL}/{link}"

        if title:
            articles.append({
                "title": title,
                "date": date,
                "category": category,
                "body": body,
                "link": link,
            })

    return articles


def build_rss_xml(items, filename, title, description):
    """Generate an RSS XML file."""
    build_date = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000")
    basename = os.path.basename(filename)

    xml_items = []
    for art in items:
        title = art["title"]
        body = art.get("body") or art.get("excerpt", "")
        link = art.get("link") or art.get("url", f"{SITE_URL}/#nyheter")
        date = art.get("date", "")
        category = art.get("category", "")

        # If no external link, point to the homepage news section
        if not link or link == f"{SITE_URL}/":
            link = f"{SITE_URL}/#nyheter"

        try:
            dt = datetime.strptime(date, "%Y-%m-%d")
            pub_date = dt.strftime("%a, %d %b %Y 00:00:00 +0000")
        except (ValueError, TypeError):
            pub_date = build_date

        # Build Facebook-ready description
        # Format: emoji + title + body + link + hashtags
        cat_emoji = {
            "Internationellt": "\U0001f30d",
            "Ny funktion": "\u2728",
            "Evenemang": "\U0001f3aa",
            "Tävling": "\U0001f3c1",
            "Nyhet": "\U0001f4e3",
            "Arkivet": "\U0001f4dc",
            "Klasser": "\U0001f6a4",
        }
        emoji = cat_emoji.get(category, "\U0001f3c1")
        cat_label = f" | {category}" if category else ""

        # Truncate body to ~250 chars at word boundary
        short_body = body[:250].rsplit(" ", 1)[0] if len(body) > 250 else body
        if len(body) > 250:
            short_body += "..."

        fb_desc = f"{emoji} {title}{cat_label}\n\n{short_body}\n\n\U0001f449 {link}\n\n#racerbåt #powerboat #svera #båtracing"

        cat_tag = f"\n      <category>{escape(category)}</category>" if category else ""

        xml_items.append(f"""    <item>
      <title>{escape(title)}</title>
      <link>{escape(link)}</link>
      <description>{escape(fb_desc)}</description>
      <pubDate>{pub_date}</pubDate>
      <guid isPermaLink="false">svera-{date}-{escape(title[:30])}</guid>{cat_tag}
    </item>""")

    rss = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">
  <channel>
    <title>{escape(title)}</title>
    <link>{SITE_URL}</link>
    <description>{escape(description)}</description>
    <language>sv</language>
    <lastBuildDate>{build_date}</lastBuildDate>
    <atom:link href="{SITE_URL}/{basename}" rel="self" type="application/rss+xml"/>
{chr(10).join(xml_items)}
  </channel>
</rss>"""

    with open(filename, "w", encoding="utf-8") as f:
        f.write(rss)

    print(f"RSS built: {len(xml_items)} items -> {basename}")


def build_rss():
    # 1. SVERA's own news (from index.html)
    svera_articles = parse_svera_news()
    if svera_articles:
        build_rss_xml(
            svera_articles,
            RSS_FILE,
            "SVERA — Nyheter från SVERA",
            "Nyheter och uppdateringar från Svenska Evenemang & Racerbåtsarkivet.",
        )

    # 2. International news (from news_feed.json)
    if os.path.exists(FEED_FILE):
        with open(FEED_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        intl_articles = data.get("articles", [])[:20]
        # Add excerpt as body for consistency
        for a in intl_articles:
            a["body"] = a.get("excerpt", "")[:300]
            source = a.get("source", "")
            if source:
                a["body"] += f" (Källa: {source})"
        build_rss_xml(
            intl_articles,
            RSS_INTL_FILE,
            "SVERA — Internationella Racerbåtsnyheter",
            "Senaste nyheterna inom internationell racerbåtssport, samlat av SVERA.",
        )


if __name__ == "__main__":
    build_rss()
