# SVERA Website — Agent Instructions

## What This Is
**SVERA — Svenska Evenemang & Racerbåtsarkivet** (svera.nu)
A static website for Sweden's collected information platform for powerboat racing.
Replaces the old Svenska Racerbåtförbundet site with an independent archive/information resource.

## Architecture
```
svera-website/
  *.html              Static pages (hand-crafted, except resultat.html)
  assets/css/style.css Main stylesheet
  assets/js/main.js   Client-side interactions (nav, dropdowns)
  config.json          Credentials (NEVER commit)
  bot/
    update.sh          Master cron script (daily 06:00)
    deploy.sh          SFTP deploy to one.com
    scrape_tracker.py  Tracks scrape timestamps (avoids redundant work)
    scrape_log.json    Scrape history log
    scrapers/          Data scrapers (webtracking, svemo, uim)
    builders/          Page generators (resultat.html, kalender.html)
    data/              Cached JSON from scrapers (gitignored)
```

## Data Flow
1. **Scrapers** fetch from external APIs → save to `bot/data/*.json`
2. **Builders** read cached JSON → generate/update HTML pages
3. **deploy.sh** uploads everything to one.com via SFTP
4. **scrape_tracker.py** prevents re-scraping unchanged sources

## Key APIs
- **WebTracking.se** (`/pbl`): `reqType=rc` (races), `reqType=rs` (results), `reqType=en` (entrants)
- **SVEMO TAM** (`tam.svemo.se`): ASP.NET calendar + results list with CSRF auth
- **SVEMO TA** (`ta.svemo.se`): Public results pages (no auth needed for results)
- **UIM Sport** (`uim.sport`): WebForms calendar with Telerik grid
- **News**: PRW + F1H2O + PBN (see SOURCES.md for full URL inventory)

## Design Rules
- Colors: `--primary: #253686`, `--accent: #fde506`, dark nav, light content
- Font: Titillium Web
- Mobile-first responsive, pure HTML/CSS/JS (no frameworks)
- All content in Swedish (`lang="sv"`)
- No emojis unless user requests them

## Deployment
- Host: one.com (free plan), SFTP only (no SSH)
- Creds in config.json, deploy via `sshpass`
- Cron: `0 6 * * * bot/update.sh`

## Security
- NEVER expose config.json or API keys
- Email on kontakt.html is JS-assembled (bot-proof)
- Filter out PB (Patrol Boat) and R (Rescue) from race results

## Testing Scrapers
```bash
# Check what needs re-scraping
python3 bot/scrape_tracker.py

# Force re-scrape everything
python3 bot/scrapers/webtracking.py --force
python3 bot/scrapers/webtracking_results.py --force
python3 bot/scrapers/svemo_calendar.py --force
python3 bot/scrapers/svemo_results.py --force

# Incremental results (only new/recent races)
python3 bot/scrapers/webtracking_results.py

# Full results rebuild (re-scrape ALL races)
python3 bot/scrapers/webtracking_results.py --full --force

# Rebuild resultat.html from cached data
python3 bot/builders/build_resultat.py

# Deploy
bash bot/deploy.sh
```
