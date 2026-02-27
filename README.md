# SVERA — Svenska Evenemang & Racerbåtsarkivet

> This runs on a Raspberry Pi — *Charlie Webber*

Sveriges samlade informationsplattform for powerboat racing. Live at [svera.nu](https://www.svera.nu).

## What is SVERA?

SVERA collects, automates, and publishes information about Swedish powerboat racing — results, calendars, classes, clubs, and history — all in one place.

The old Svenska Racerbatforbundet (SVERA) was absorbed into Svemo around 2020 and its website disappeared. This project picks up where it left off as an independent, community-driven resource.

## Features

- **Race Results** — 277+ races with GPS tracking from WebTracking.se (2011–present) + official SM/RM competitions from SVEMO
- **Weekly News Digest** — AI-summarized from 3 international news sources (PRW, F1H2O, Powerboat News)
- **Calendar** — Upcoming events from SVEMO TA and UIM Sport
- **Classes & Rules** — All offshore, circuit, and aquabike classes with links to official rule books
- **Clubs** — Swedish boat racing clubs with contact info
- **SM/RM Champions** — Auto-calculated Swedish Championship and Riksmästerskap standings from SVEMO results
- **Archive** — Historical timeline from the first race in Marstrand 1904
- **Email-to-AI Worker** — Send an email and an AI agent updates the site automatically
- **Automated Updates** — Weekly scraping, incremental caching, deploy-on-change

## Tech Stack

- **Frontend:** Pure HTML/CSS/JS — no frameworks, works on one.com free hosting
- **Scrapers:** Python 3 (stdlib only — zero pip dependencies)
- **AI Agent:** DeepSeek V3 (general), Qwen ZDR (personal data), Claude Code CLI (complex tasks) — all via OpenRouter
- **Data Privacy:** ZDR (Zero Data Retention) routing — personal names detected and routed to Qwen ZDR, masked before Claude
- **Deployment:** SFTP to one.com via `sshpass`
- **Automation:** systemd user service — starts at boot, checks email every 60s, full scrape weekly

## Project Structure

```
svera-website/
├── index.html                 Homepage
├── nyheter.html               News + weekly AI digest
├── resultat.html              Race results (auto-generated, gitignored)
├── champions.html             SM/RM standings (auto-generated)
├── kalender.html              Event calendar
├── klasser.html               Classes & rules
├── klubbar.html               Clubs directory
├── arkivet.html               Historical archive
├── om.html                    About SVERA
├── kontakt.html               Contact
├── policy.html                Data & privacy policy (GDPR)
├── .htaccess                  HTTPS + www redirects
├── assets/
│   ├── css/style.css          Stylesheet
│   ├── js/main.js             Client-side JS
│   ├── images/                Logo, favicons
│   └── uploads/               PDFs from email tasks
├── bot/
│   ├── svera_daemon.sh        Main daemon (boot → loop)
│   ├── email_worker.py        Email-to-AI pipeline ("Charlie Webber")
│   ├── deploy.sh              SFTP deployment to one.com
│   ├── update.sh              Manual full scrape + deploy (deprecated)
│   ├── update_footer.py       Stamps "Senast uppdaterad" dates
│   ├── scrape_tracker.py      Prevents redundant scraping
│   ├── scrapers/
│   │   ├── webtracking.py           Race list from webtracking.se
│   │   ├── webtracking_results.py   Race results (positions, laps, times)
│   │   ├── svemo_calendar.py        SVEMO TA calendar (requires auth)
│   │   ├── svemo_results.py         Official SVEMO SM/RM results
│   │   ├── uim_calendar.py          UIM Sport international calendar
│   │   ├── svemo_rules.py           Rule book PDF links
│   │   └── news_aggregator.py       News from PRW, F1H2O, Powerboat News
│   ├── builders/
│   │   ├── build_resultat.py        Generates resultat.html
│   │   ├── build_kalender.py        Updates kalender.html
│   │   ├── build_news.py            Updates nyheter.html + AI digest
│   │   └── build_champions.py       Generates champions.html (SM/RM standings)
│   └── data/                        Cached JSON from scrapers (gitignored)
├── config.json                Credentials (gitignored, never commit)
├── config.json.example        Template — copy and fill in your values
├── setup.sh                   Interactive setup script
├── CLAUDE.md                  Agent instructions for AI tools
├── SOURCES.md                 Full inventory of all scraped URLs
└── TASK.md                    Original project task documentation
```

## Quick Start

### Prerequisites

- Python 3.10+
- `sshpass` — for SFTP deployment (`sudo apt install sshpass`)
- An [OpenRouter](https://openrouter.ai) API key — for AI features (news digest, email worker)
- one.com hosting account (or adapt `deploy.sh` for your host)

### Setup

```bash
# 1. Clone the repo
git clone https://github.com/YOUR_USER/svera-website.git
cd svera-website

# 2. Run the interactive setup (creates config.json)
bash setup.sh

# 3. Test deployment
bash bot/deploy.sh

# 4. Check scraper status
python3 bot/scrape_tracker.py

# 5. Run a manual full scrape + deploy
bash bot/update.sh
```

### Daemon (recommended for production)

The daemon runs continuously: checks email every 60 seconds, runs a full scrape weekly, and deploys automatically when files change.

```bash
# Create the systemd service
mkdir -p ~/.config/systemd/user
cat > ~/.config/systemd/user/svera.service << 'EOF'
[Unit]
Description=SVERA Daemon — email tasks + weekly scrape + auto-deploy
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=/path/to/svera-website
ExecStart=/bin/bash /path/to/svera-website/bot/svera_daemon.sh
Restart=on-failure
RestartSec=60
Environment=PATH=%h/.local/bin:/usr/local/bin:/usr/bin:/bin

[Install]
WantedBy=default.target
EOF

# Update paths in the service file, then:
systemctl --user daemon-reload
systemctl --user enable svera.service
systemctl --user start svera.service

# Check status
systemctl --user status svera.service

# View logs
tail -f bot/daemon.log
tail -f bot/email_worker.log
```

## Data Flow

```
External APIs                  Scrapers              Builders              Deploy
──────────────                 ────────              ────────              ──────
WebTracking.se  ──────────►  webtracking.py      ┐
                             webtracking_results  ├──► build_resultat ──► resultat.html
                                                  │
SVEMO TAM       ──────────►  svemo_calendar.py   ├──► build_kalender ──► kalender.html
                             svemo_results.py    ┤
                                                 └──► build_champions ─► champions.html
                                                                          deploy.sh
UIM Sport       ──────────►  uim_calendar.py     ────► build_kalender     ──► one.com
                                                                              (SFTP)
PRW / F1H2O /   ──────────►  news_aggregator.py  ────► build_news     ──► nyheter.html
Powerboat News

SVEMO / UIM     ──────────►  svemo_rules.py      ────► (embedded in klasser.html)
```

## Scrapers

All scrapers live in `bot/scrapers/` and use **Python stdlib only** (zero pip dependencies). Each one writes cached JSON to `bot/data/` and respects `scrape_tracker.py` intervals to avoid redundant work.

### `webtracking.py` — Race List

| | |
|---|---|
| **Source** | [WebTracking.se](https://webtracking.se) (public REST API) |
| **API** | `https://webtracking.se/pbl?reqType=rc&date=all` |
| **Auth** | None |
| **Interval** | 24h |
| **Output** | `bot/data/webtracking_races.json` (~36 KB) |
| **Used by** | `build_resultat.py` → `resultat.html` |

Fetches the full race list (277+ races, 2011–present). Each race includes index, name, date, year, and auto-classified type (Offshore / Rundbana / Tavling). Filters out non-race entries (patrol boats, rescue).

```bash
python3 bot/scrapers/webtracking.py --force
```

### `webtracking_results.py` — Race Results

| | |
|---|---|
| **Source** | [WebTracking.se](https://webtracking.se) (public REST API) |
| **API** | `https://webtracking.se/pbl?reqType=rs&raceIdx={id}` |
| **Auth** | None |
| **Interval** | 24h |
| **Output** | `bot/data/webtracking_results.json` (~426 KB) |
| **Used by** | `build_resultat.py` → `resultat.html` |

Fetches checkpoint crossing data and computes race results: position, laps completed, and total time per class. Handles both per-entrant starts (offshore) and class starts (circuit racing).

**Incremental by default** — only scrapes races not already cached + current/last year races (which might update). Use `--full` to re-scrape everything.

```bash
python3 bot/scrapers/webtracking_results.py --force          # incremental
python3 bot/scrapers/webtracking_results.py --full --force    # all 277+ races
```

### `svemo_calendar.py` — SVEMO Calendar

| | |
|---|---|
| **Source** | [SVEMO TAM](https://tam.svemo.se) (ASP.NET with CSRF) |
| **Auth** | Personnummer + password (in `config.json`) |
| **Interval** | 48h |
| **Output** | `bot/data/svemo_calendar.json` |
| **Used by** | `build_kalender.py` → `kalender.html` |

Logs in to tam.svemo.se, searches for boat racing branches (Rundbana=22, Aquabike=26, Offshore=27) for the current and next year, and filters for future events only. Each event includes name, date range, location, organizer, branch, and status.

```bash
python3 bot/scrapers/svemo_calendar.py --force
```

### `svemo_results.py` — Official SVEMO Results

| | |
|---|---|
| **Source** | [SVEMO TAM](https://tam.svemo.se) + [SVEMO TA](https://ta.svemo.se) (public results pages) |
| **Auth** | TAM login for competition list; public pages for actual results |
| **Interval** | 48h |
| **Output** | `bot/data/svemo_results.json` (~115 KB) |
| **Used by** | `build_resultat.py` → `resultat.html` (SVEMO tab) |

Two-step scraper: (1) logs in to TAM to get the paginated competition list, then (2) fetches per-class results from public `ta.svemo.se/Resultat/Tavling/{id}` pages. Parses HTML tables for position, driver, club, boat, class, nationality, and points. Incremental — only scrapes competitions not already cached.

```bash
python3 bot/scrapers/svemo_results.py --force
```

### `uim_calendar.py` — UIM International Calendar

| | |
|---|---|
| **Source** | [UIM Sport](https://www.uim.sport) (ASP.NET WebForms / Telerik RadGrid) |
| **Auth** | None |
| **Interval** | 48h |
| **Output** | `bot/data/uim_calendar.json` (~5 KB) |
| **Used by** | `build_kalender.py` → `kalender.html` |

Scrapes the offshore calendar from uim.sport. Parses the RadGrid table for event date, name, venue, country, and discipline. Falls back to a POST with ViewState if the initial HTML is empty (WebForms quirk). Filters to current year only.

```bash
python3 bot/scrapers/uim_calendar.py --force
```

### `svemo_rules.py` — Rule Books

| | |
|---|---|
| **Source** | [SVEMO Regler](https://regler.svemo.se/regelbocker/vattensport) + [UIM Sport](https://www.uim.sport/RuleBookReleaseList.aspx) |
| **Auth** | None |
| **Interval** | 168h (weekly) |
| **Output** | `bot/data/rules.json` (~15 KB) |
| **Used by** | `klasser.html` |

Extracts PDF links to official rule books from both SVEMO and UIM. Categorizes by class (Offshore, Circuit, Aquabike, etc.). Rule books change very rarely so this runs weekly.

```bash
python3 bot/scrapers/svemo_rules.py --force
```

### `news_aggregator.py` — International News

| | |
|---|---|
| **Sources** | [Powerboat Racing World](https://powerboatracingworld.com) (WP REST), [F1H2O](https://www.f1h2o.com) (HTML), [Powerboat News](https://powerboat.news) (WP REST) |
| **Auth** | None |
| **Interval** | 12h |
| **Output** | `bot/data/news_feed.json` (~13 KB) |
| **Used by** | `build_news.py` → `nyheter.html` |

Aggregates the latest 10 articles from each of 3 sources. PRW and Powerboat News use WordPress REST API (`/wp-json/wp/v2/posts`). F1H2O uses HTML scraping with regex on structured divs. Articles include title, date, URL, excerpt, and source tag. Combined feed sorted by date descending.

```bash
python3 bot/scrapers/news_aggregator.py
```

## Builders

Builders read cached JSON from `bot/data/` and generate or update HTML pages.

### `build_resultat.py` — Results Page

Reads `webtracking_races.json`, `webtracking_results.json`, and `svemo_results.json`. Embeds the data as compact JavaScript variables (`var RACES=...`, `var RESULTS=...`, `var SVEMO=...`) directly into `resultat.html` for client-side filtering and display. The generated page is ~530 KB and is gitignored.

### `build_kalender.py` — Calendar Page

Reads `svemo_calendar.json` and `uim_calendar.json`. Replaces the `<tbody>` contents in `kalender.html` with upcoming events, adds class badges (offshore, rundbana, aquabike), and updates the "Uppdaterad" date.

### `build_news.py` — News + AI Digest

Reads `news_feed.json`. Scans articles for personal names — if found, uses **Qwen ZDR** (Zero Data Retention); otherwise uses **DeepSeek V3** (cheaper). Generates a Swedish weekly summary (3–4 paragraphs). Builds article cards (max 15, balanced across sources). Replaces the digest and article grid sections in `nyheter.html`. Requires an OpenRouter API key in `config.json`.

### `build_champions.py` — SM/RM Championship Standings

Reads `svemo_results.json` and calculates championship standings per class per year. Applies the official SVEMO points system (20-17-15-13-11-10-9-8-7-6-5-4-3-2-1 base + 2 bonus for SM). Determines SM vs RM vs no-title status per class based on starter counts (3+ starters at all races = SM; <3 at some but 3+ unique crews across season = RM; otherwise no title). Handles class name normalization across different naming conventions, Heat/Total disambiguation, misaligned scraper data, and DNF/DSQ entries. Generates `champions.html` with year tabs, per-class standings, and expandable per-race breakdowns.

## Scrape Schedule

The daemon (`svera_daemon.sh`) runs a full scrape every **7 days**. Between cycles, individual scrapers respect their own intervals via `scrape_tracker.py`:

| Source | Scraper | Interval | Auth |
|--------|---------|----------|------|
| WebTracking races | `webtracking.py` | 24h | None |
| WebTracking results | `webtracking_results.py` | 24h | None |
| SVEMO calendar | `svemo_calendar.py` | 48h | TAM login |
| SVEMO results | `svemo_results.py` | 48h | TAM login |
| UIM calendar | `uim_calendar.py` | 48h | None |
| News (PRW, F1H2O, PBN) | `news_aggregator.py` | 12h | None |
| Rules (SVEMO + UIM) | `svemo_rules.py` | 168h | None |

### Manual commands

```bash
# Check what needs re-scraping
python3 bot/scrape_tracker.py

# Force scrape everything + rebuild + deploy
bash bot/update.sh

# Or run individual scrapers
python3 bot/scrapers/webtracking.py --force
python3 bot/scrapers/webtracking_results.py --force
python3 bot/scrapers/svemo_calendar.py --force
python3 bot/scrapers/svemo_results.py --force
python3 bot/scrapers/uim_calendar.py --force
python3 bot/scrapers/svemo_rules.py --force
python3 bot/scrapers/news_aggregator.py

# Full results rebuild (re-scrape ALL 277+ races, not just recent)
python3 bot/scrapers/webtracking_results.py --full --force

# Rebuild pages from cached data (no re-scrape)
python3 bot/builders/build_resultat.py
python3 bot/builders/build_kalender.py
python3 bot/builders/build_news.py
python3 bot/builders/build_champions.py

# Deploy
bash bot/deploy.sh
```

## Email-to-AI Worker — "Charlie Webber"

Send an email from the admin address to the configured email and **Charlie Webber** (the AI web developer) automatically handles it.

### How it works

1. Daemon checks inbox every 60 seconds
2. Only processes emails from `admin_sender` (configured in config.json)
3. Accepts plain text body + .pdf attachments
4. DeepSeek classifies the task: **LOW** / **MEDIUM** / **HIGH**
5. Regex scans email for personal names (Swedish name patterns)
6. Routes based on level + name presence:

| Level | Names? | Engine | ZDR? |
|-------|--------|--------|------|
| LOW | No | DeepSeek V3 | No |
| LOW | Yes | Qwen | Yes |
| MEDIUM | Any | Qwen | Yes (always) |
| HIGH | No | DeepSeek crafts → Claude CLI | No |
| HIGH | Yes | Qwen ZDR crafts → mask names → Claude CLI | Yes |

7. Deploys to one.com automatically
8. Always replies with result + which engine was used

### ZDR (Zero Data Retention)

When personal names are detected in email content, the system routes to **Qwen via ZDR-approved API** (`"provider": {"zdr": true}` in the OpenRouter payload). This ensures no personal data is stored by the AI provider.

For HIGH tasks with names, Qwen (ZDR) first extracts all names, then the prompt is masked (`[PERSON_1]`, `[PERSON_2]`) before being sent to Claude Code — Claude never sees real names.

### Example

```
Subject: Nytt inlagg om SM i Oregrund
Body: Lagg till en nyhet om att SM i offshore kors 8-9 augusti i Oregrund.
Attach: inbjudan-sm-2026.pdf

-> Classified LOW, no names -> DeepSeek handles -> reply in ~30s
```

```
Subject: Lagg till Max Samuelsson i nyheter
Body: Max Samuelsson vann SM i offshore 2026.

-> Classified LOW, names detected -> Qwen ZDR handles -> reply in ~45s
```

## Data Sources

| Source | What | Type |
|--------|------|------|
| [WebTracking.se](https://webtracking.se) | Race results, GPS tracking | REST API (public) |
| [SVEMO TAM](https://tam.svemo.se) | Swedish race calendar | ASP.NET + CSRF (auth required) |
| [SVEMO TA](https://ta.svemo.se) | Official SM/RM results | HTML scraping (public) |
| [UIM Sport](https://www.uim.sport) | International calendar | WebForms/Telerik (public) |
| [Powerboat Racing World](https://powerboatracingworld.com) | International news | WP REST API (public) |
| [F1H2O](https://www.f1h2o.com) | F1 powerboat news | HTML scraping (public) |
| [Powerboat News](https://powerboat.news) | International news | WP REST API (public) |

See [SOURCES.md](SOURCES.md) for a complete inventory of all scraped URLs and endpoints.

## Configuration

### config.json

Created by `setup.sh` or manually from `config.json.example`. Contains:

| Section | What | Required for |
|---------|------|-------------|
| `hosting` | SFTP host, user, password, webroot | Deployment (`deploy.sh`) |
| `api_keys` | OpenRouter API key, DeepSeek model, Qwen ZDR fallback model | AI digest, email worker, ZDR routing |
| `email` | IMAP/SMTP credentials, admin sender | Email worker (`email_worker.py`) |
| `data_sources.svemo_tam` | SVEMO personnummer + password | Calendar + results scraping |
| `data_sources.webtracking` | (no auth needed) | Race data |
| `data_sources.uim_calendar` | (no auth needed) | International calendar |

**Never commit config.json** — it is gitignored. Use `config.json.example` as reference.

### Minimal setup (no auth scrapers only)

If you don't have SVEMO credentials or email hosting, you can still run the public scrapers:

```bash
# These work without any credentials:
python3 bot/scrapers/webtracking.py --force
python3 bot/scrapers/webtracking_results.py --force
python3 bot/scrapers/uim_calendar.py --force
python3 bot/scrapers/news_aggregator.py

# Build pages from scraped data:
python3 bot/builders/build_resultat.py
python3 bot/builders/build_kalender.py
python3 bot/builders/build_champions.py
# (build_news.py requires OpenRouter API key for AI summary)
```

## Contributing

Have information about Swedish powerboat racing? Old results, photos, or club info?
Contact us via [svera.nu/kontakt](https://www.svera.nu/kontakt.html) or open an issue.

## License

This project is open source. The scraped data belongs to its respective sources (WebTracking.se, SVEMO, UIM, PRW, F1H2O, Powerboat News).

---

*SVERA — Oberoende informationsresurs sedan 2026*

[![Buy Me A Coffee](https://img.shields.io/badge/Buy%20Me%20A%20Coffee-support-yellow?style=flat&logo=buy-me-a-coffee)](https://buymeacoffee.com/theralley)
