#!/usr/bin/env python3
"""SVERA site test suite — run before deployment.

Tests:
  1. All HTML pages parse without errors
  2. Nav consistency — every page has the same nav items
  3. No broken internal links (href to *.html files that exist)
  4. News feed / weekly digest markers present in nyheter.html
  5. Scrapers return data from all 3 sources
  6. build_news.py can parse and replace markers
  7. No leftover old links (index.html#nyheter)

Usage:
  python3 bot/test_site.py          # run all tests
  python3 bot/test_site.py --quick  # skip scraper tests (no network)
"""
import os
import re
import sys
from html.parser import HTMLParser

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)

EXPECTED_PAGES = [
    "index.html", "om.html", "arkivet.html", "klasser.html",
    "kalender.html", "resultat.html", "nyheter.html", "klubbar.html", "kontakt.html",
]

EXPECTED_NAV_ITEMS = [
    "/", "om.html", "arkivet.html", "klasser.html",
    "kalender.html", "resultat.html", "nyheter.html", "klubbar.html", "kontakt.html",
]

passed = 0
failed = 0


def test(name, condition, detail=""):
    global passed, failed
    if condition:
        passed += 1
        print(f"  PASS  {name}")
    else:
        failed += 1
        print(f"  FAIL  {name}")
        if detail:
            print(f"        {detail}")


def read_file(name):
    path = os.path.join(PROJECT_DIR, name)
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


# ==============================================================
# Test 1: All pages exist and parse
# ==============================================================
print("\n[1] HTML pages exist and parse")
for page in EXPECTED_PAGES:
    path = os.path.join(PROJECT_DIR, page)
    exists = os.path.exists(path)
    test(f"{page} exists", exists)
    if exists:
        html = read_file(page)
        test(f"{page} has <html>", "<html" in html)
        test(f"{page} has </html>", "</html>" in html)


# ==============================================================
# Test 2: Nav consistency — Nyheter link in every page
# ==============================================================
print("\n[2] Navigation consistency")
for page in EXPECTED_PAGES:
    path = os.path.join(PROJECT_DIR, page)
    if not os.path.exists(path):
        continue
    html = read_file(page)
    # Extract nav section
    nav_match = re.search(r'<nav class="main-nav">(.*?)</nav>', html, re.DOTALL)
    if not nav_match:
        test(f"{page} has <nav>", False)
        continue
    nav_html = nav_match.group(1)
    # Check all expected nav items are present (as href targets)
    for item in EXPECTED_NAV_ITEMS:
        has_item = f'href="{item}"' in nav_html or f"href='{item}'" in nav_html
        test(f"{page} nav has {item}", has_item)


# ==============================================================
# Test 3: No broken internal links
# ==============================================================
print("\n[3] Internal links")
for page in EXPECTED_PAGES:
    path = os.path.join(PROJECT_DIR, page)
    if not os.path.exists(path):
        continue
    html = read_file(page)
    # Find all href="*.html" links (not http/https)
    links = re.findall(r'href="([^"#]+\.html)', html)
    for link in set(links):
        if link.startswith("http"):
            continue
        target = os.path.join(PROJECT_DIR, link)
        test(f"{page} -> {link}", os.path.exists(target))


# ==============================================================
# Test 4: No old index.html#nyheter links
# ==============================================================
print("\n[4] No legacy links")
for page in EXPECTED_PAGES:
    path = os.path.join(PROJECT_DIR, page)
    if not os.path.exists(path):
        continue
    html = read_file(page)
    test(f"{page} no index.html#nyheter", "index.html#nyheter" not in html)


# ==============================================================
# Test 5: Nyheter page markers
# ==============================================================
print("\n[5] Nyheter page structure")
if os.path.exists(os.path.join(PROJECT_DIR, "nyheter.html")):
    html = read_file("nyheter.html")
    test("Has WEEKLY DIGEST START", "<!-- WEEKLY DIGEST START -->" in html)
    test("Has WEEKLY DIGEST END", "<!-- WEEKLY DIGEST END -->" in html)
    test("Has NEWS FEED START", "<!-- NEWS FEED START -->" in html)
    test("Has NEWS FEED END", "<!-- NEWS FEED END -->" in html)
    test("Has source buttons", "source-btn" in html)
    test("Has PRW link", "powerboatracingworld.com" in html)
    test("Has F1H2O link", "f1h2o.com" in html)
    test("Has PBN link", "powerboat.news" in html)


# ==============================================================
# Test 6: News card format (no blue gradient images)
# ==============================================================
print("\n[6] News card format")
if os.path.exists(os.path.join(PROJECT_DIR, "index.html")):
    html = read_file("index.html")
    test("No news-image divs", 'class="news-image"' not in html)
    test("No linear-gradient in cards", "linear-gradient" not in html.split("</header>")[-1].split("<!-- Data Sources -->")[0] if "<!-- Data Sources -->" in html else True)
    test("Has news-meta divs", 'class="news-meta"' in html)
    test("Has category badges", 'class="category"' in html)


# ==============================================================
# Test 7: Scrapers (skip with --quick)
# ==============================================================
if "--quick" not in sys.argv:
    print("\n[7] Scrapers (live network)")
    sys.path.insert(0, os.path.join(SCRIPT_DIR, "scrapers"))
    try:
        from news_aggregator import scrape_prw, scrape_f1h2o, scrape_pbn

        prw = scrape_prw()
        test("PRW returns articles", len(prw) > 0, f"got {len(prw)}")

        f1h2o = scrape_f1h2o()
        test("F1H2O returns articles", len(f1h2o) > 0, f"got {len(f1h2o)}")

        pbn = scrape_pbn()
        test("PBN returns articles", len(pbn) > 0, f"got {len(pbn)}")

        # Check F1H2O titles are clean (no excerpt in title)
        for a in f1h2o[:3]:
            clean = len(a["title"]) < 100
            test(f"F1H2O title clean: {a['title'][:50]}...", clean, f"len={len(a['title'])}")
    except Exception as e:
        test("Scraper import", False, str(e))
else:
    print("\n[7] Scrapers (SKIPPED — use without --quick to test)")


# ==============================================================
# Test 8: build_news.py marker replacement
# ==============================================================
print("\n[8] Build news marker replacement")
data_dir = os.path.join(SCRIPT_DIR, "data")
feed_file = os.path.join(data_dir, "news_feed.json")
digest_file = os.path.join(data_dir, "weekly_digest.json")
test("news_feed.json exists", os.path.exists(feed_file))
test("weekly_digest.json exists", os.path.exists(digest_file))

if os.path.exists(feed_file) and os.path.exists(digest_file):
    import json
    with open(feed_file) as f:
        feed = json.load(f)
    test("Feed has articles", len(feed.get("articles", [])) > 0)

    # Check all 3 sources present
    sources = set(a["source_short"] for a in feed.get("articles", []))
    test("Feed has PBN", "PBN" in sources)
    test("Feed has F1H2O", "F1H2O" in sources)
    test("Feed has PRW", "PRW" in sources)


# ==============================================================
# Test 9: Resultat page structure — type filters, tabs, robustness
# ==============================================================
print("\n[9] Resultat page — type filters & UI robustness")
res_html = read_file("resultat.html")

# --- Tabs ---
test("Has tab container", 'class="result-tabs"' in res_html)
test("Has WebTracking tab button", "switchTab('wt'" in res_html or 'switchTab("wt"' in res_html)
test("Has SVEMO tab button", "switchTab('svemo'" in res_html or 'switchTab("svemo"' in res_html)
test("Has WebTracking panel", 'id="panel-wt"' in res_html)
test("Has SVEMO panel", 'id="panel-svemo"' in res_html)
test("switchTab function defined", "function switchTab(" in res_html)

# --- Type filter buttons row ---
test("Has type filter container", 'id="typeFilters"' in res_html)
test("Has type filter CSS", ".type-filters" in res_html or ".type-btn" in res_html)

# --- Type filter JS ---
test("Has type filter variable (aT)", "var aT=" in res_html)
test("Has filterType function", "function ft(" in res_html or "function filterType(" in res_html)
test("Type filter drives render()", "aT" in res_html and "render()" in res_html)

# --- Type filter renders dynamically from data ---
test("Type filters built from RACES data", "typeFilters" in res_html and "innerHTML" in res_html)

# --- Card-based UI (not old tables) ---
test("Uses race-card class", "race-card" in res_html)
test("Uses race-card-header class", "race-card-header" in res_html)
test("Uses race-card-body class", "race-card-body" in res_html)
test("No old race-table class", "race-table" not in res_html)
test("No old detail-panel class", "detail-panel" not in res_html)
test("No old year-section class", "year-section" not in res_html)

# --- Year filters ---
test("Has year filter container", 'id="yearFilters"' in res_html)
test("Has year filter JS", "function fy(" in res_html)

# --- Search ---
test("Has search input", 'id="searchInput"' in res_html)
test("Has SVEMO search input", 'id="svemoSearch"' in res_html)

# --- Data integrity ---
test("Has RACES data", "var RACES=" in res_html)
test("Has RESULTS data", "var RESULTS=" in res_html)
test("Has SVEMO data", "var SVEMO=" in res_html)
test("Has render function", "function render()" in res_html)
test("Has renderRaceBody function", "function renderRaceBody(" in res_html)
test("Has renderSvemo function", "function renderSvemo(" in res_html)

# --- CSS: type filter button styling ---
test("Type button CSS exists", ".type-btn" in res_html)

# --- Badge classes for all known types ---
test("Badge CSS: offshore", ".badge-offshore" in res_html)
test("Badge CSS: rundbana", ".badge-rundbana" in res_html)
test("Badge CSS: tavling", ".badge-tavling" in res_html)

# --- Results count display ---
test("Results count element", 'id="resultsCount"' in res_html)
test("Count updates on filter", "resultsCount" in res_html)

# --- No CSS leakage (all CSS inside <style>) ---
style_start = res_html.find("<style>")
style_end = res_html.find("</style>")
test("CSS block opens", style_start > 0)
test("CSS block closes", style_end > style_start)
between_style_and_head = res_html[style_end:res_html.find("</head>")]
test("No CSS outside style tag", ".race-card" not in between_style_and_head.replace("</style>", ""))

# --- Mobile responsive ---
test("Has 768px breakpoint", "@media(max-width:768px)" in res_html)
test("Has 480px breakpoint", "@media(max-width:480px)" in res_html)

# --- Credits ---
test("WebTracking credit link", "webtracking.se" in res_html)
test("SVEMO credit link", "ta.svemo.se" in res_html)


# ==============================================================
# Summary
# ==============================================================
print(f"\n{'='*50}")
total = passed + failed
print(f"Results: {passed}/{total} passed, {failed} failed")
if failed:
    print("FIX THE FAILURES BEFORE DEPLOYING")
    sys.exit(1)
else:
    print("All tests passed — safe to deploy")
    sys.exit(0)
