#!/usr/bin/env bash
# ============================================================
# SVERA Daemon — runs on boot, manages everything
# ============================================================
#
#  What it does:
#    - Checks email every 60s for tasks from admin
#    - Scrapes data sources once a week
#    - Deploys only if files have changed
#
#  Startup:
#    systemctl --user enable svera.service
#    systemctl --user start svera.service
#
# ============================================================
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
LOG="$SCRIPT_DIR/daemon.log"
LAST_SCRAPE="$SCRIPT_DIR/.last_scrape"
LAST_DEPLOY_HASH="$SCRIPT_DIR/.last_deploy_hash"
LAST_NEWS="$SCRIPT_DIR/.last_news"
SCRAPE_INTERVAL=604800  # 7 days in seconds
EMAIL_INTERVAL=60       # check email every 60 seconds (lightweight IMAP poll)
NEWS_DAY=5              # Friday (1=Mon ... 5=Fri, per date +%u)

# ---- Logging ----
log() { echo "[$(date '+%Y-%m-%d %H:%M')] $*" | tee -a "$LOG"; }

# ---- Rotate log if > 1 MB ----
rotate_log() {
    if [ -f "$LOG" ] && [ "$(stat -c%s "$LOG" 2>/dev/null || echo 0)" -gt 1048576 ]; then
        mv "$LOG" "$LOG.old"
        log "Log rotated"
    fi
}

# ---- Compute hash of all deployable files ----
site_hash() {
    {
        find "$PROJECT_DIR" -maxdepth 1 -name "*.html" -exec md5sum {} \;
        md5sum "$PROJECT_DIR/assets/css/style.css" 2>/dev/null
        md5sum "$PROJECT_DIR/assets/js/main.js" 2>/dev/null
        md5sum "$PROJECT_DIR/.htaccess" 2>/dev/null
        find "$PROJECT_DIR/assets/images" -type f -exec md5sum {} \; 2>/dev/null
        find "$PROJECT_DIR/assets/uploads" -type f -exec md5sum {} \; 2>/dev/null
    } | md5sum | cut -d' ' -f1
}

# ---- Deploy only if site changed ----
deploy_if_changed() {
    local current_hash
    current_hash=$(site_hash)
    local prev_hash
    prev_hash=$(cat "$LAST_DEPLOY_HASH" 2>/dev/null || echo "none")

    if [ "$current_hash" = "$prev_hash" ]; then
        log "No changes — skipping deploy"
        return 1
    fi

    log "Changes detected — deploying..."
    bash "$SCRIPT_DIR/deploy.sh" 2>&1 | tee -a "$LOG"
    echo "$current_hash" > "$LAST_DEPLOY_HASH"
    log "Deploy complete"
    return 0
}

# ---- Check if weekly scrape is due ----
needs_scrape() {
    [ ! -f "$LAST_SCRAPE" ] && return 0
    local last now diff
    last=$(cat "$LAST_SCRAPE" 2>/dev/null || echo "0")
    [[ "$last" =~ ^[0-9]+$ ]] || return 0
    now=$(date +%s)
    diff=$(( now - last ))
    [ "$diff" -ge "$SCRAPE_INTERVAL" ]
}

# ---- Weekly scrape + build ----
run_scrape() {
    log "========== WEEKLY SCRAPE =========="
    cd "$PROJECT_DIR"

    log "[1/7] WebTracking races..."
    python3 "$SCRIPT_DIR/scrapers/webtracking.py" --force 2>&1 | tee -a "$LOG" || true

    log "[2/7] WebTracking results..."
    python3 "$SCRIPT_DIR/scrapers/webtracking_results.py" --force 2>&1 | tee -a "$LOG" || true

    log "[3/7] SVEMO calendar..."
    python3 "$SCRIPT_DIR/scrapers/svemo_calendar.py" --force 2>&1 | tee -a "$LOG" || true

    log "[4/7] SVEMO results..."
    python3 "$SCRIPT_DIR/scrapers/svemo_results.py" --force 2>&1 | tee -a "$LOG" || true

    log "[5/7] UIM calendar..."
    python3 "$SCRIPT_DIR/scrapers/uim_calendar.py" --force 2>&1 | tee -a "$LOG" || true

    log "[6/7] Rules..."
    python3 "$SCRIPT_DIR/scrapers/svemo_rules.py" --force 2>&1 | tee -a "$LOG" || true

    log "[7/8] News aggregator + weekly digest..."
    python3 "$SCRIPT_DIR/scrapers/news_aggregator.py" 2>&1 | tee -a "$LOG" || true
    python3 "$SCRIPT_DIR/builders/build_news.py" 2>&1 | tee -a "$LOG" || true
    python3 "$SCRIPT_DIR/builders/build_rss.py" 2>&1 | tee -a "$LOG" || true

    log "[8/8] Social media (TikTok)..."
    python3 "$SCRIPT_DIR/scrapers/social_tiktok.py" 2>&1 | tee -a "$LOG" || true
    python3 "$SCRIPT_DIR/builders/build_social.py" 2>&1 | tee -a "$LOG" || true

    log "Rebuilding pages..."
    python3 "$SCRIPT_DIR/builders/build_resultat.py" 2>&1 | tee -a "$LOG" || true
    python3 "$SCRIPT_DIR/builders/build_kalender.py" 2>&1 | tee -a "$LOG" || true
    python3 "$SCRIPT_DIR/builders/build_champions.py" 2>&1 | tee -a "$LOG" || true

    log "Updating footers..."
    python3 "$SCRIPT_DIR/update_footer.py" 2>&1 | tee -a "$LOG" || true

    date +%s > "$LAST_SCRAPE"
    deploy_if_changed
    log "========== SCRAPE DONE =========="
}

# ---- Friday news refresh ----
needs_news_refresh() {
    # Only run on Fridays
    [ "$(date +%u)" -ne "$NEWS_DAY" ] && return 1
    # Check if already ran today
    [ -f "$LAST_NEWS" ] && [ "$(cat "$LAST_NEWS")" = "$(date +%F)" ] && return 1
    return 0
}

run_news_refresh() {
    log "========== FRIDAY NEWS REFRESH =========="
    cd "$PROJECT_DIR"
    python3 "$SCRIPT_DIR/scrapers/news_aggregator.py" 2>&1 | tee -a "$LOG" || true
    python3 "$SCRIPT_DIR/builders/build_news.py" 2>&1 | tee -a "$LOG" || true
    python3 "$SCRIPT_DIR/builders/build_rss.py" 2>&1 | tee -a "$LOG" || true
    python3 "$SCRIPT_DIR/update_footer.py" 2>&1 | tee -a "$LOG" || true
    date +%F > "$LAST_NEWS"
    deploy_if_changed
    log "========== NEWS REFRESH DONE =========="
}

# ---- Check email for tasks ----
check_email() {
    python3 "$SCRIPT_DIR/email_worker.py" 2>&1 | tee -a "$LOG"
    local exit_code=$?
    if [ $exit_code -ne 0 ]; then
        log "WARN: email check failed (exit $exit_code)"
    fi
    # If email_worker made changes, deploy them
    deploy_if_changed || true
}

# ============================================================
# MAIN LOOP
# ============================================================
log ""
log "###################################"
log "# SVERA Daemon started"
log "# Email:  every ${EMAIL_INTERVAL}s"
log "# Scrape: every ${SCRAPE_INTERVAL}s (7 days)"
log "# News:   every Friday"
log "###################################"

LOOPS_SINCE_STATUS=0
STATUS_EVERY=60  # log "next scrape" every ~60 loops (once/hour at 60s interval)

while true; do
    rotate_log

    # 1. Check email — every loop (60s)
    check_email

    # 1.5. Friday news refresh
    if needs_news_refresh; then
        run_news_refresh
    fi

    # 2. Weekly scrape if due
    if needs_scrape; then
        run_scrape
        LOOPS_SINCE_STATUS=0
    fi

    # 3. Periodic status log (avoid spamming every 60s)
    LOOPS_SINCE_STATUS=$(( LOOPS_SINCE_STATUS + 1 ))
    if [ "$LOOPS_SINCE_STATUS" -ge "$STATUS_EVERY" ]; then
        local_remaining=$(( SCRAPE_INTERVAL - ($(date +%s) - $(cat "$LAST_SCRAPE" 2>/dev/null || echo 0)) ))
        log "Status: next scrape in ~$(( local_remaining / 3600 ))h"
        LOOPS_SINCE_STATUS=0
    fi

    sleep "$EMAIL_INTERVAL"
done
