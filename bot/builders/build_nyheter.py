#!/usr/bin/env python3
"""DEPRECATED — use build_news.py instead.

This builder reads news_articles.json (from news_scraper.py) and generates
nyheter.html from scratch. The canonical pipeline is now:
  news_aggregator.py -> news_feed.json -> build_news.py -> nyheter.html

Kept for reference only. Do not call from daemon or cron.
"""
import json
import os
import re
import urllib.request
from datetime import datetime, timedelta
from html import escape

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
CONFIG_FILE = os.path.join(PROJECT_DIR, "config.json")
SUMMARY_FILE = os.path.join(DATA_DIR, "news_weekly_summary.json")


def load_json(filename):
    path = os.path.join(DATA_DIR, filename)
    if not os.path.exists(path):
        return None
    with open(path) as f:
        return json.load(f)


def load_config():
    if not os.path.exists(CONFIG_FILE):
        return {}
    with open(CONFIG_FILE) as f:
        return json.load(f)


def generate_weekly_summary(articles, config):
    """Use DeepSeek via OpenRouter to generate a weekly summary."""
    api_keys = config.get("api_keys", {})
    api_key = api_keys.get("openrouter")
    model = api_keys.get("openrouter_model", "deepseek/deepseek-chat-v3-0324")
    base_url = api_keys.get("openrouter_base_url", "https://openrouter.ai/api/v1")

    if not api_key:
        print("[build_nyheter] No OpenRouter API key, skipping summary")
        return None

    # Filter to articles from the last 7 days
    cutoff = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
    recent = [a for a in articles if (a.get("date") or "9999") >= cutoff]
    if not recent:
        # Use all articles if none have dates in range
        recent = articles[:15]

    # Build prompt content
    news_text = ""
    for i, a in enumerate(recent[:20], 1):
        news_text += f"\n{i}. [{a['source']}] {a['title']}"
        if a.get("date"):
            news_text += f" ({a['date']})"
        if a.get("summary"):
            news_text += f"\n   {a['summary']}"
        news_text += "\n"

    prompt = f"""You are a powerboat racing journalist. Write a concise weekly summary
called "This Week in Powerboating" based on the following recent news articles.
Write in English. Keep it to 3-5 paragraphs covering the most important stories.
Use an engaging but professional tone. Do NOT use markdown formatting - write plain text
with simple paragraph breaks. Do not include a title/heading.

Recent powerboat racing news:
{news_text}"""

    payload = json.dumps({
        "model": model,
        "messages": [
            {"role": "system", "content": "You are a concise sports journalist specializing in powerboat racing."},
            {"role": "user", "content": prompt},
        ],
        "max_tokens": 800,
        "temperature": 0.7,
    }).encode("utf-8")

    try:
        req = urllib.request.Request(
            f"{base_url}/chat/completions",
            data=payload,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://svera.nu",
                "X-Title": "SVERA News Bot",
            },
        )
        resp = urllib.request.urlopen(req, timeout=30)
        result = json.loads(resp.read().decode())
        summary_text = result["choices"][0]["message"]["content"].strip()

        # Save summary
        summary_data = {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "model": model,
            "article_count": len(recent),
            "summary": summary_text,
        }
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(SUMMARY_FILE, "w") as f:
            json.dump(summary_data, f, ensure_ascii=False, indent=2)

        print(f"[build_nyheter] Generated weekly summary ({len(summary_text)} chars)")
        return summary_data

    except Exception as e:
        print(f"[build_nyheter] DeepSeek summary failed: {e}")
        return None


def load_existing_summary():
    """Load previously generated summary if it exists and is recent enough."""
    if not os.path.exists(SUMMARY_FILE):
        return None
    try:
        with open(SUMMARY_FILE) as f:
            data = json.load(f)
        generated = datetime.fromisoformat(data["generated_at"])
        if datetime.now() - generated < timedelta(days=7):
            return data
    except (json.JSONDecodeError, KeyError, ValueError):
        pass
    return None


def build():
    """Build nyheter.html from news data."""
    news_data = load_json("news_articles.json")
    if not news_data:
        print("[build_nyheter] No news data found, run news_scraper.py first")
        return False

    articles = news_data.get("articles", [])
    if not articles:
        print("[build_nyheter] No articles in news data")
        return False

    config = load_config()

    # Weekly summary — generate or load cached
    summary = load_existing_summary()
    if not summary:
        summary = generate_weekly_summary(articles, config)

    # Build HTML
    scraped_at = news_data.get("scraped_at", "")
    html = _render_page(articles, summary, scraped_at)

    out_path = os.path.join(PROJECT_DIR, "nyheter.html")
    with open(out_path, "w") as f:
        f.write(html)

    print(f"[build_nyheter] Built nyheter.html with {len(articles)} articles")
    return True


def _render_page(articles, summary, scraped_at):
    """Render the full nyheter.html page."""
    today = datetime.now().strftime("%Y-%m-%d")

    # Group articles by source
    by_source = {}
    for a in articles:
        src = a.get("source", "Unknown")
        by_source.setdefault(src, []).append(a)

    # Build weekly summary section
    summary_html = ""
    if summary:
        paragraphs = summary["summary"].split("\n\n")
        summary_paragraphs = "\n".join(
            f"        <p>{escape(p.strip())}</p>" for p in paragraphs if p.strip()
        )
        gen_date = summary.get("generated_at", "")[:10]
        summary_html = f"""
    <section class="content-block weekly-summary">
      <h2>This Week in Powerboating</h2>
      <div class="weekly-summary-content">
{summary_paragraphs}
      </div>
      <p class="summary-meta">Sammanfattning genererad {gen_date} via DeepSeek AI</p>
    </section>
"""

    # Build article cards
    article_cards = ""
    for a in articles:
        date_html = f'<span class="news-date">{escape(a["date"])}</span>' if a.get("date") else ""
        summary_text = f"<p>{escape(a['summary'][:200])}</p>" if a.get("summary") else ""
        source_class = a.get("source_id", "")

        article_cards += f"""
        <article class="news-card">
          <div class="news-body">
            <div class="news-card-header">
              <span class="news-source source-{escape(source_class)}">{escape(a["source"])}</span>
              {date_html}
            </div>
            <h3><a href="{escape(a["url"])}" target="_blank" rel="noopener">{escape(a["title"])}</a></h3>
            {summary_text}
            <a href="{escape(a["url"])}" class="read-more" target="_blank" rel="noopener">Read more &rarr;</a>
          </div>
        </article>
"""

    # Source badges for filter
    source_badges = ""
    for src_name, src_articles in by_source.items():
        source_badges += f'      <button class="source-filter" data-source="{escape(src_name)}">{escape(src_name)} ({len(src_articles)})</button>\n'

    return f"""<!DOCTYPE html>
<html lang="sv">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Nyheter &mdash; SVERA</title>
  <meta name="description" content="Internationella nyheter om powerboat racing. Samlat fr&aring;n Powerboat Racing World, F1H2O och Powerboat News.">
  <link rel="stylesheet" href="assets/css/style.css">
  <style>
    .weekly-summary {{
      border-left: 4px solid var(--accent);
      background: linear-gradient(135deg, #fdfef6 0%, #fff 100%);
    }}
    .weekly-summary h2 {{
      color: var(--primary);
      border-bottom-color: var(--accent);
    }}
    .weekly-summary-content p {{
      margin-bottom: 14px;
      line-height: 1.8;
      color: var(--text);
    }}
    .summary-meta {{
      font-size: 0.75rem;
      color: var(--text-light);
      font-style: italic;
      margin-top: 16px;
      padding-top: 12px;
      border-top: 1px solid var(--border);
    }}
    .source-filters {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin-bottom: 24px;
    }}
    .source-filter {{
      padding: 6px 16px;
      border: 1px solid var(--border);
      border-radius: 20px;
      background: var(--white);
      color: var(--text);
      font-size: 0.78rem;
      font-weight: 600;
      cursor: pointer;
      transition: all var(--transition);
      font-family: var(--font);
    }}
    .source-filter:hover,
    .source-filter.active {{
      background: var(--primary);
      color: #fff;
      border-color: var(--primary);
    }}
    .news-card-header {{
      display: flex;
      align-items: center;
      gap: 12px;
      margin-bottom: 8px;
    }}
    .news-source {{
      display: inline-block;
      padding: 3px 10px;
      border-radius: 12px;
      font-size: 0.68rem;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.4px;
    }}
    .source-prw {{
      background: #1a3a5c;
      color: #fff;
    }}
    .source-f1h2o {{
      background: #cc0000;
      color: #fff;
    }}
    .source-pbnews {{
      background: #2d6a4f;
      color: #fff;
    }}
    .news-list .news-card .news-body h3 a {{
      color: var(--primary);
      text-decoration: none;
      transition: color var(--transition);
    }}
    .news-list .news-card .news-body h3 a:hover {{
      color: var(--primary-dark);
    }}
    .page-hero {{
      background: linear-gradient(135deg, #1e2d6d 0%, var(--primary) 35%, #2840a0 70%, #1a2766 100%);
      color: #fff;
      padding: 36px 0 28px;
      border-bottom: 3px solid var(--accent);
    }}
    .page-hero h2 {{
      font-size: 1.6rem;
      font-weight: 300;
      margin-bottom: 8px;
    }}
    .page-hero p {{
      color: rgba(255,255,255,0.75);
      font-size: 0.92rem;
    }}
    .update-info {{
      text-align: center;
      font-size: 0.78rem;
      color: var(--text-light);
      padding: 16px 0;
    }}
  </style>
</head>
<body>

<a href="#main" class="skip-link">Hoppa till inneh&aring;ll</a>

<!-- Top bar -->
<div class="top-bar">
  <div class="container">
    <span>Oberoende informationsresurs sedan 2026</span>
  </div>
</div>

<!-- Header -->
<header class="site-header">
  <div class="container">
    <div class="header-inner">
      <a href="/" class="logo">
        <img class="logo-img" src="assets/images/svera-logo.png" alt="SVERA">
        <div class="logo-text">
          <h1>SVERA</h1>
          <span class="tagline">Svenska Evenemang &amp; Racerb&aring;tsarkivet</span>
        </div>
      </a>
      <button class="hamburger" aria-label="Meny">
        <span></span>
        <span></span>
        <span></span>
      </button>
    </div>
  </div>

  <!-- Navigation -->
  <nav class="main-nav">
    <div class="container">
      <ul class="nav-list">
        <li><a href="/">Hem</a></li>
        <li>
          <a href="om.html">Om SVERA</a>
          <ul class="dropdown">
            <li><a href="om.html#historia">Historia</a></li>
            <li><a href="om.html#bakgrund">V&aring;r bakgrund</a></li>
            <li><a href="om.html#mission">Vad vi g&ouml;r</a></li>
          </ul>
        </li>
        <li>
          <a href="arkivet.html">Arkivet</a>
          <ul class="dropdown">
            <li><a href="arkivet.html#historia">Historiska milstolpar</a></li>
            <li><a href="arkivet.html#nyheter">Nyhetsarkiv</a></li>
            <li><a href="arkivet.html#forare">F&ouml;rarregister</a></li>
            <li><a href="arkivet.html#classic">Classic-klasser</a></li>
          </ul>
        </li>
        <li>
          <a href="klasser.html">Klasser &amp; Regler</a>
          <ul class="dropdown">
            <li><a href="klasser.html#rundbana">Rundbana</a></li>
            <li><a href="klasser.html#offshore">Offshore</a></li>
            <li><a href="klasser.html#aquabike">Aquabike</a></li>
            <li><a href="klasser.html#regler">Reglementen</a></li>
          </ul>
        </li>
        <li><a href="kalender.html">Kalender</a></li>
        <li><a href="resultat.html">Resultat</a></li>
        <li><a href="nyheter.html" class="active">Nyheter</a></li>
        <li><a href="klubbar.html">Klubbar</a></li>
        <li><a href="kontakt.html">Kontakt</a></li>
      </ul>
    </div>
  </nav>
</header>

<!-- Page Hero -->
<section class="page-hero">
  <div class="container">
    <span class="hero-badge">International News</span>
    <h2>Nyheter fr&aring;n v&auml;rldens powerboat-racing</h2>
    <p>Automatiskt samlat fr&aring;n Powerboat Racing World, F1H2O och Powerboat News.</p>
  </div>
</section>

<!-- Main content -->
<div class="container">
  <div class="page-content" id="main">
{summary_html}
    <!-- Source filters -->
    <div class="source-filters">
      <button class="source-filter active" data-source="all">Alla ({len(articles)})</button>
{source_badges}
    </div>

    <!-- News list -->
    <div class="news-list">
{article_cards}
    </div>

    <div class="update-info">
      Senast uppdaterad: {scraped_at[:16] if scraped_at else today}
    </div>
  </div>
</div>

<!-- Footer -->
<footer class="site-footer">
  <div class="container">
    <div class="footer-grid">
      <div class="footer-col">
        <h3>SVERA</h3>
        <p>Svenska Evenemang &amp; Racerb&aring;tsarkivet</p>
        <p>Oberoende informationsresurs f&ouml;r svensk racerb&aring;tsport.</p>
      </div>
      <div class="footer-col">
        <h3>Utforska</h3>
        <ul>
          <li><a href="om.html">Om SVERA</a></li>
          <li><a href="arkivet.html">Arkivet</a></li>
          <li><a href="klasser.html">Klasser &amp; Regler</a></li>
          <li><a href="kalender.html">Kalender</a></li>
          <li><a href="resultat.html">Resultat</a></li>
          <li><a href="nyheter.html">Nyheter</a></li>
          <li><a href="klubbar.html">Klubbar</a></li>
        </ul>
      </div>
      <div class="footer-col">
        <h3>Kontakt</h3>
        <p>Har du material, bilder eller kunskap att bidra med?</p>
        <p><a href="kontakt.html">Kontakta oss &rarr;</a></p>
      </div>
    </div>
    <div class="footer-bottom">
      &copy; 2026 SVERA &mdash; Svenska Evenemang &amp; Racerb&aring;tsarkivet. Senast uppdaterad {today}.
    </div>
  </div>
</footer>

<script src="assets/js/main.js"></script>
<script>
// Source filter functionality
document.querySelectorAll('.source-filter').forEach(function(btn) {{
  btn.addEventListener('click', function() {{
    var source = this.dataset.source;
    document.querySelectorAll('.source-filter').forEach(function(b) {{ b.classList.remove('active'); }});
    this.classList.add('active');
    document.querySelectorAll('.news-list .news-card').forEach(function(card) {{
      var cardSource = card.querySelector('.news-source');
      if (source === 'all' || (cardSource && cardSource.textContent.trim() === source)) {{
        card.style.display = '';
      }} else {{
        card.style.display = 'none';
      }}
    }});
  }});
}});
</script>
</body>
</html>"""


if __name__ == "__main__":
    import sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

    force_summary = "--force-summary" in sys.argv
    if force_summary:
        # Remove cached summary to force regeneration
        if os.path.exists(SUMMARY_FILE):
            os.remove(SUMMARY_FILE)

    build()
