# SVERA Data Sources

All external websites and APIs scraped by the SVERA bot system.
Last updated: 2026-02-26

## Primary Data Sources

### 1. WebTracking.se — GPS Tracking & Race Results
- **Base URL:** `https://webtracking.se/pbl`
- **Auth:** None (public API)
- **Scraper:** `bot/scrapers/webtracking.py`, `bot/scrapers/webtracking_results.py`
- **Interval:** 24h
- **Endpoints:**
  - `?reqType=rc` — Race list (277 races, 2011–present)
  - `?reqType=rs&raceIdx={id}` — Race results (checkpoint crossings, laps, times)
  - `?reqType=en&raceIdx={id}` — Entrant details (pilot, co-pilot, boat)
- **Output:** `bot/data/webtracking_races.json`, `bot/data/webtracking_results.json`
- **Used by:** `resultat.html` (WebTracking tab)

### 2. SVEMO TAM — Swedish Motorsport Federation
- **Login URL:** `https://tam.svemo.se/Auth/Login`
- **Calendar URL:** `https://tam.svemo.se/Competition`
- **Results URL:** `https://tam.svemo.se/Result/Competition`
- **Public Results:** `https://ta.svemo.se/Resultat/Tavling/{CompetitionId}`
- **Event Results:** `https://ta.svemo.se/Public/Pages/Competition/Default/EventResult.aspx?CompetitionId={id}&EventId={id}`
- **Auth:** POST with username + password + `__RequestVerificationToken` (CSRF)
- **Scraper:** `bot/scrapers/svemo_calendar.py`, `bot/scrapers/svemo_results.py`
- **Interval:** 48h
- **Branch IDs:** 22=Rundbana, 26=Aquabike, 27=Offshore
- **Output:** `bot/data/svemo_calendar.json`, `bot/data/svemo_results.json`
- **Used by:** `kalender.html` (SVEMO table), `resultat.html` (SVEMO Resultat tab)

### 3. SVEMO Rules
- **Rule Books:** `https://regler.svemo.se/regelbocker/vattensport`
- **Statutes:** `https://regler.svemo.se/stadgar-och-spar`
- **Auth:** None (public)
- **Scraper:** `bot/scrapers/svemo_rules.py`
- **Interval:** 168h (weekly)
- **Output:** `bot/data/rules.json`
- **Used by:** `klasser.html`

### 4. UIM Sport — International Powerboat Federation
- **Calendar:** `https://www.uim.sport/CalendarList.aspx`
- **Rule Books:** `https://www.uim.sport/RuleBookReleaseList.aspx`
- **Auth:** None (public, ASP.NET WebForms/Telerik RadGrid)
- **Scraper:** `bot/scrapers/uim_calendar.py`, `bot/scrapers/svemo_rules.py`
- **Interval:** 48h (calendar), 168h (rules)
- **Output:** `bot/data/uim_calendar.json`, `bot/data/rules.json`
- **Used by:** `kalender.html` (UIM table), `klasser.html`

### 5. Powerboat Racing World (PRW)
- **API:** `https://powerboatracingworld.com/wp-json/wp/v2/posts?per_page=10`
- **Auth:** None (WordPress REST API, public)
- **Scraper:** `bot/scrapers/news_aggregator.py`
- **Interval:** 12h
- **Output:** `bot/data/news_feed.json`
- **Used by:** `nyheter.html`

### 6. F1H2O
- **URL:** `https://www.f1h2o.com/news/{YYYY}`
- **Auth:** None (HTML scraping)
- **Scraper:** `bot/scrapers/news_aggregator.py`
- **Interval:** 12h
- **Output:** `bot/data/news_feed.json`
- **Used by:** `nyheter.html`

### 7. Powerboat News (PBN)
- **API:** `https://powerboat.news/wp-json/wp/v2/posts?per_page=10`
- **Auth:** None (WordPress REST API, public)
- **Scraper:** `bot/scrapers/news_aggregator.py`
- **Interval:** 12h
- **Output:** `bot/data/news_feed.json`
- **Used by:** `nyheter.html`

## Secondary Sources

### 8. SVERA.org Archive
- **URL:** `https://web.archive.org/web/20210310000057/https://www.svera.org/`
- **Alt:** `https://archive.ph/FGsei`
- **Type:** Static reference (historical data, not actively scraped)
- **Used by:** `arkivet.html`

### 9. OpenRouter API (AI Summarization)
- **URL:** `https://openrouter.ai/api/v1/chat/completions`
- **Model:** `deepseek/deepseek-v4-pro` (primary), `qwen/qwen-2.5-72b-instruct` (fallback)
- **Auth:** Bearer token (API key in config.json)
- **Used by:** `bot/builders/build_news.py` (weekly digest summarization), `bot/email_worker.py` (task processing)

## Scrape Interval Summary

| Source | Scraper | Interval | Records |
|--------|---------|----------|---------|
| WebTracking races | `webtracking.py` | 24h | 277 races |
| WebTracking results | `webtracking_results.py` | 24h | 242 races with results |
| SVEMO calendar | `svemo_calendar.py` | 48h | Upcoming events |
| SVEMO results | `svemo_results.py` | 48h | 14 competitions, 417 entries |
| UIM calendar | `uim_calendar.py` | 48h | ~30 events |
| SVEMO + UIM rules | `svemo_rules.py` | 168h | PDF links |
| News (PRW, F1H2O, PBN) | `news_aggregator.py` | 12h | ~24 articles |
| Weekly AI digest | `build_news.py` | 168h | 1 summary |

## External Links on Site (not scraped)

These URLs appear as outbound links on the website but are not actively scraped:

- `https://www.svemo.se` — SVEMO main site
- `https://www.roslagenboatracing.com` — RBR club
- `https://www.roslagsloppet.com` — Roslagsloppet event
- `https://www.kmk.se` — Kungliga Motorbåt Klubben
- `https://www.facebook.com/p/Sweden-Boat-Racing-Club-100063749852329/` — SBRC Facebook
- `https://buymeacoffee.com/theralley` — Support/donate link
