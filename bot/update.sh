#!/usr/bin/env bash
# DEPRECATED — The daemon (svera_daemon.sh) now handles scheduling.
# This script can still be run manually for a one-off full scrape + deploy.
#
# Old cron (no longer active):
# 0 6 * * * /path/to/svera-website/bot/update.sh >> /path/to/svera-website/bot/update.log 2>&1
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
LOG_FILE="$SCRIPT_DIR/update.log"

echo ""
echo "============================================"
echo "SVERA Auto-Update — $(date '+%Y-%m-%d %H:%M:%S')"
echo "============================================"

cd "$PROJECT_DIR"

# Step 1: Run scrapers
echo ""
echo "--- Step 1: Scraping data sources ---"

echo "[1/6] WebTracking.se races..."
python3 "$SCRIPT_DIR/scrapers/webtracking.py" || echo "WARNING: webtracking scraper failed"

echo "[2/6] WebTracking.se results..."
python3 "$SCRIPT_DIR/scrapers/webtracking_results.py" || echo "WARNING: webtracking results scraper failed"

echo "[3/6] SVEMO calendar..."
python3 "$SCRIPT_DIR/scrapers/svemo_calendar.py" || echo "WARNING: svemo calendar scraper failed"

echo "[4/6] UIM calendar..."
python3 "$SCRIPT_DIR/scrapers/uim_calendar.py" || echo "WARNING: uim calendar scraper failed"

echo "[5/6] Rules & regulations..."
python3 "$SCRIPT_DIR/scrapers/svemo_rules.py" || echo "WARNING: rules scraper failed"

echo "[6/6] International powerboat news..."
python3 "$SCRIPT_DIR/scrapers/news_aggregator.py" || echo "WARNING: news aggregator failed"

# Step 2: Rebuild pages from scraped data
echo ""
echo "--- Step 2: Rebuilding pages ---"

echo "[1/4] Rebuilding resultat.html..."
python3 "$SCRIPT_DIR/builders/build_resultat.py" || echo "WARNING: resultat builder failed"

echo "[2/4] Rebuilding kalender.html..."
python3 "$SCRIPT_DIR/builders/build_kalender.py" || echo "WARNING: kalender builder failed"

echo "[3/4] Building nyheter.html (news + AI summary)..."
python3 "$SCRIPT_DIR/builders/build_news.py" || echo "WARNING: news builder failed"

echo "[4/4] Building champions.html (SM/RM standings)..."
python3 "$SCRIPT_DIR/builders/build_champions.py" || echo "WARNING: champions builder failed"

# Step 3: Update footer dates
echo ""
echo "--- Step 3: Updating footer dates ---"
python3 "$SCRIPT_DIR/update_footer.py" || echo "WARNING: footer update failed"

# Step 4: Deploy to one.com
echo ""
echo "--- Step 4: Deploying to one.com ---"
bash "$SCRIPT_DIR/deploy.sh"

echo ""
echo "============================================"
echo "SVERA Auto-Update COMPLETE — $(date '+%Y-%m-%d %H:%M:%S')"
echo "============================================"
