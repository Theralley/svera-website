#!/usr/bin/env python3
"""Build 'Veckans Nyheter' page using DeepSeek.

Reads: bot/data/news_feed.json (from news_aggregator.py)
Updates: nyheter.html — replaces the weekly digest and article grid sections
Uses: DeepSeek V3 via OpenRouter for summarization
"""
import json
import os
import re
import urllib.request
from datetime import datetime
from html import escape

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BOT_DIR = os.path.dirname(SCRIPT_DIR)
PROJECT_DIR = os.path.dirname(BOT_DIR)
DATA_DIR = os.path.join(BOT_DIR, "data")
FEED_FILE = os.path.join(DATA_DIR, "news_feed.json")
NYHETER_FILE = os.path.join(PROJECT_DIR, "nyheter.html")
CONFIG_FILE = os.path.join(PROJECT_DIR, "config.json")
DIGEST_FILE = os.path.join(DATA_DIR, "weekly_digest.json")


def load_config():
    with open(CONFIG_FILE) as f:
        return json.load(f)


def load_feed():
    if not os.path.exists(FEED_FILE):
        print("[build_news] No news feed found, run news_aggregator.py first")
        return None
    with open(FEED_FILE) as f:
        return json.load(f)


def summarize_with_deepseek(articles, api_key, model):
    """Use DeepSeek to write a Swedish weekly digest."""
    article_text = ""
    for i, a in enumerate(articles[:15], 1):
        article_text += (
            f"{i}. [{a['source_short']}] {a['title']}\n"
            f"   Datum: {a['date']}\n"
        )
        if a.get("excerpt"):
            article_text += f"   {a['excerpt'][:200]}\n"
        article_text += f"   {a['url']}\n\n"

    prompt = (
        "Du ar sportjournalist for SVERA (Sveriges racerbatsarkiv).\n"
        "Skriv en kort sammanfattning pa SVENSKA av veckans nyheter inom powerboat racing.\n\n"
        "REGLER:\n"
        "- Max 3-4 korta stycken\n"
        "- Namna de viktigaste nyheterna (2-4 st)\n"
        "- Inkludera kallorna (PRW, F1H2O, PBN)\n"
        "- Ton: professionell men entusiastisk, som en sportkommentator\n"
        "- Skriv BARA sammanfattningstexten, ingen HTML och inga rubriker\n"
        "- Avsluta inte med 'halsningar' eller liknande\n\n"
        f"NYHETER DENNA VECKA:\n{article_text}\n"
        "Skriv sammanfattningen nu:"
    )

    url = "https://openrouter.ai/api/v1/chat/completions"
    payload = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 1024,
    }).encode("utf-8")

    req = urllib.request.Request(url, data=payload, headers={
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://svera.nu",
        "X-Title": "SVERA News Digest",
    })

    try:
        resp = urllib.request.urlopen(req, timeout=60)
        data = json.loads(resp.read().decode())
        return data["choices"][0]["message"]["content"].strip()
    except Exception as e:
        print(f"[build_news] DeepSeek summarization failed: {e}")
        return None


def build_digest_html(summary_text, articles):
    """Build the weekly digest HTML block for nyheter.html."""
    # Convert summary paragraphs to HTML
    paragraphs = [p.strip() for p in summary_text.split("\n\n") if p.strip()]
    if len(paragraphs) <= 1:
        paragraphs = [p.strip() for p in summary_text.split("\n") if p.strip()]

    summary_html = ""
    for p in paragraphs:
        # Skip headings
        if p.startswith("Veckans") or p.startswith("#"):
            continue
        # Convert markdown bold to <strong>
        p = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", p)
        p = re.sub(r"^#{1,4}\s+", "", p)
        summary_html += f"      <p>{p}</p>\n"

    # Build source links (max 5 unique)
    links_html = ""
    seen = set()
    for a in articles[:8]:
        if a["title"] in seen:
            continue
        seen.add(a["title"])
        title_short = escape(a["title"][:65] + ("..." if len(a["title"]) > 65 else ""))
        links_html += (
            f'        <li><a href="{escape(a["url"])}" target="_blank" rel="noopener">'
            f'{title_short}</a> <span class="source-tag">{escape(a["source_short"])}</span></li>\n'
        )
        if len(seen) >= 5:
            break

    date_str = datetime.now().strftime("%Y-%m-%d")

    html = (
        f'  <!-- WEEKLY DIGEST START -->\n'
        f'  <div class="weekly-digest">\n'
        f'    <div class="digest-header">\n'
        f'      <h2 class="section-title">Veckans Nyheter</h2>\n'
        f'      <span class="digest-date">Uppdaterad {date_str}</span>\n'
        f'    </div>\n'
        f'    <div class="digest-body">\n'
        f'{summary_html}'
        f'    </div>\n'
        f'    <div class="digest-links">\n'
        f'      <h3>Läs mer</h3>\n'
        f'      <ul>\n'
        f'{links_html}'
        f'      </ul>\n'
        f'    </div>\n'
        f'    <div class="digest-footer">\n'
        f'      Källor: Powerboat Racing World, F1H2O, Powerboat News\n'
        f'    </div>\n'
        f'  </div>\n'
        f'  <!-- WEEKLY DIGEST END -->'
    )
    return html


def build_articles_html(articles):
    """Build the article grid HTML from the news feed.

    Ensures all sources are represented by picking top articles per source
    then filling remaining slots chronologically.
    """
    MAX_CARDS = 15

    # Group by source
    by_source = {}
    for a in articles:
        s = a.get("source_short", "?")
        by_source.setdefault(s, []).append(a)

    # Guarantee at least 2 articles per source (if available)
    selected = []
    seen = set()
    for source, src_articles in by_source.items():
        for a in src_articles[:2]:
            if a["title"] not in seen:
                seen.add(a["title"])
                selected.append(a)

    # Fill remaining slots chronologically from all articles
    for a in articles:
        if len(selected) >= MAX_CARDS:
            break
        if a["title"] not in seen:
            seen.add(a["title"])
            selected.append(a)

    # Sort final selection by date descending
    selected.sort(key=lambda a: a.get("date", ""), reverse=True)

    cards_html = ""
    for a in selected:
        title = escape(a.get("title", "")[:80])
        if not title:
            continue

        excerpt = escape(a.get("excerpt", "")[:160])
        url = escape(a.get("url", ""))
        source = escape(a.get("source_short", ""))
        date = escape(a.get("date", ""))

        cards_html += (
            f'    <article class="news-card-grid">\n'
            f'      <div class="news-card-source">{source}</div>\n'
            f'      <h3><a href="{url}" target="_blank" rel="noopener">{title}</a></h3>\n'
        )
        if excerpt:
            cards_html += f'      <p>{excerpt}</p>\n'
        cards_html += (
            f'      <span class="news-card-date">{date}</span>\n'
            f'    </article>\n'
        )

    html = (
        f'  <!-- NEWS FEED START -->\n'
        f'  <h2 class="section-title" style="margin-top:36px;">Senaste artiklarna</h2>\n'
        f'  <div class="news-grid">\n'
        f'{cards_html}'
        f'  </div>\n'
        f'  <!-- NEWS FEED END -->'
    )
    return html


def update_nyheter(digest_html, articles_html):
    """Replace digest and article sections in nyheter.html."""
    if not os.path.exists(NYHETER_FILE):
        print("[build_news] nyheter.html not found")
        return False

    with open(NYHETER_FILE) as f:
        html = f.read()

    # Replace weekly digest
    digest_pattern = r"  <!-- WEEKLY DIGEST START -->.*?<!-- WEEKLY DIGEST END -->"
    if re.search(digest_pattern, html, re.DOTALL):
        html = re.sub(digest_pattern, digest_html, html, count=1, flags=re.DOTALL)
        print("[build_news] Replaced weekly digest in nyheter.html")
    else:
        print("[build_news] WARNING: Could not find digest markers in nyheter.html")

    # Replace article grid
    feed_pattern = r"  <!-- NEWS FEED START -->.*?<!-- NEWS FEED END -->"
    if re.search(feed_pattern, html, re.DOTALL):
        html = re.sub(feed_pattern, articles_html, html, count=1, flags=re.DOTALL)
        print("[build_news] Replaced article grid in nyheter.html")
    else:
        print("[build_news] WARNING: Could not find feed markers in nyheter.html")

    with open(NYHETER_FILE, "w") as f:
        f.write(html)
    return True


def build():
    """Main build pipeline."""
    feed = load_feed()
    if not feed or not feed.get("articles"):
        print("[build_news] No articles to summarize")
        return False

    config = load_config()
    api_key = config.get("api_keys", {}).get("openrouter", "")
    model = config.get("api_keys", {}).get("openrouter_model", "deepseek/deepseek-chat-v3-0324")

    if not api_key:
        print("[build_news] No OpenRouter API key")
        return False

    articles = feed["articles"]
    print(f"[build_news] Summarizing {len(articles)} articles with DeepSeek...")

    summary = summarize_with_deepseek(articles, api_key, model)
    if not summary:
        print("[build_news] Summarization failed")
        return False

    print(f"[build_news] Summary: {summary[:200]}...")

    # Save digest data
    digest = {
        "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "summary": summary,
        "article_count": len(articles),
        "sources": list(set(a["source_short"] for a in articles)),
    }
    with open(DIGEST_FILE, "w", encoding="utf-8") as f:
        json.dump(digest, f, indent=2, ensure_ascii=False)

    # Build HTML sections
    digest_html = build_digest_html(summary, articles)
    articles_html = build_articles_html(articles)

    if not update_nyheter(digest_html, articles_html):
        return False

    print("[build_news] Done!")
    return True


if __name__ == "__main__":
    build()
