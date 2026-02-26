# SVERA — Svenska Evenemang & Racerbåtsarkivet

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
- **Archive** — Historical timeline from the first race in Marstrand 1904
- **Email-to-AI Worker** — Send an email and an AI agent updates the site automatically
- **Automated Updates** — Weekly scraping, incremental caching, deploy-on-change

## Tech Stack

- **Frontend:** Pure HTML/CSS/JS — no frameworks, works on one.com free hosting
- **Scrapers:** Python 3 (stdlib only — zero pip dependencies)
- **AI Agent:** DeepSeek V3 via OpenRouter (low/medium tasks) + Claude Code CLI (high-complexity tasks)
- **Deployment:** SFTP to one.com via `sshpass`
- **Automation:** systemd user service — starts at boot, checks email every 60s, full scrape weekly

## Project Structure

```
svera-website/
├── index.html                 Homepage
├── nyheter.html               News + weekly AI digest
├── resultat.html              Race results (auto-generated, gitignored)
├── kalender.html              Event calendar
├── klasser.html               Classes & rules
├── klubbar.html               Clubs directory
├── arkivet.html               Historical archive
├── om.html                    About SVERA
├── kontakt.html               Contact
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
│   │   └── build_news.py            Updates nyheter.html + AI digest
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
                             svemo_results.py     ┘
                                                                          deploy.sh
UIM Sport       ──────────►  uim_calendar.py     ────► build_kalender     ──► one.com
                                                                              (SFTP)
PRW / F1H2O /   ──────────►  news_aggregator.py  ────► build_news     ──► nyheter.html
Powerboat News

SVEMO / UIM     ──────────►  svemo_rules.py      ────► (embedded in klasser.html)
```

## Scrape Intervals

The daemon runs a full scrape every 7 days. Individual scrapers also respect per-source intervals via `scrape_tracker.py`:

| Source | Scraper | Interval | Notes |
|--------|---------|----------|-------|
| WebTracking races | `webtracking.py` | 24h | Public API, 277+ races |
| WebTracking results | `webtracking_results.py` | 24h | Incremental by default |
| SVEMO calendar | `svemo_calendar.py` | 48h | Requires TAM login |
| SVEMO results | `svemo_results.py` | 48h | Requires TAM login |
| UIM calendar | `uim_calendar.py` | 48h | Public, ASP.NET WebForms |
| News (PRW, F1H2O, PBN) | `news_aggregator.py` | 12h | WP REST API + HTML scraping |
| Rules / regulations | `svemo_rules.py` | 168h (weekly) | PDF links rarely change |

### Manual scraper commands

```bash
# Check what needs re-scraping
python3 bot/scrape_tracker.py

# Force scrape a specific source
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

# Deploy
bash bot/deploy.sh
```

## Email-to-AI Worker — "Charlie Webber"

Send an email from the admin address to the configured email and **Charlie Webber** (the AI web developer) automatically handles it.

### How it works

1. Daemon checks inbox every 60 seconds
2. Only processes emails from `admin_sender` (configured in config.json)
3. Accepts plain text body + .pdf attachments
4. DeepSeek classifies the task:
   - **LOW** — simple text change, add/remove news, swap a link
   - **MEDIUM** — single-file bug fix, small CSS tweak, minor feature
   - **HIGH** — multi-file changes, design work, new features, JS changes
5. **LOW/MEDIUM** — DeepSeek V3 handles directly via tool-use agent loop
6. **HIGH** — DeepSeek crafts a structured prompt, then Claude Code CLI executes it
7. Deploys to one.com automatically
8. Always replies with result (success or error)

### Example

```
Subject: Nytt inlagg om SM i Oregrund
Body: Lagg till en nyhet om att SM i offshore kors 8-9 augusti i Oregrund.
Attach: inbjudan-sm-2026.pdf

-> Classified LOW -> DeepSeek handles -> reply in ~30s
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
| `api_keys` | OpenRouter API key + model | AI digest (`build_news.py`), email worker |
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
# (build_news.py requires OpenRouter API key for AI summary)
```

## Contributing

Have information about Swedish powerboat racing? Old results, photos, or club info?
Contact us via [svera.nu/kontakt](https://www.svera.nu/kontakt.html) or open an issue.

## License

This project is open source. The scraped data belongs to its respective sources (WebTracking.se, SVEMO, UIM, PRW, F1H2O, Powerboat News).

---

*SVERA — Oberoende informationsresurs sedan 2026*
