#!/usr/bin/env bash
# ============================================================
# SVERA Setup Script
# Installs dependencies, creates config.json, sets up daemon
# ============================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CONFIG="$SCRIPT_DIR/config.json"
EXAMPLE="$SCRIPT_DIR/config.json.example"
SERVICE_DIR="$HOME/.config/systemd/user"
SERVICE_FILE="$SERVICE_DIR/svera.service"

echo ""
echo "=========================================="
echo "  SVERA — Initial Setup"
echo "=========================================="

# ============================================================
# Step 1: Check & install system dependencies
# ============================================================
echo ""
echo "--- Step 1: Checking dependencies ---"

MISSING=()

# Python 3
if command -v python3 &>/dev/null; then
    PY_VER=$(python3 --version 2>&1)
    echo "  [OK] $PY_VER"
else
    MISSING+=("python3")
    echo "  [MISSING] python3"
fi

# sshpass (for SFTP deployment)
if command -v sshpass &>/dev/null; then
    echo "  [OK] sshpass"
else
    MISSING+=("sshpass")
    echo "  [MISSING] sshpass"
fi

# gh CLI (for GitHub operations, optional)
if command -v gh &>/dev/null; then
    echo "  [OK] gh (GitHub CLI)"
else
    echo "  [OPTIONAL] gh (GitHub CLI) — not installed"
fi

# Claude Code CLI (for HIGH tasks, optional)
CLAUDE_CLI="$HOME/.local/bin/claude"
if [ -f "$CLAUDE_CLI" ]; then
    echo "  [OK] Claude Code CLI"
else
    echo "  [OPTIONAL] Claude Code CLI — not installed (needed for HIGH email tasks)"
    echo "           Install: npm install -g @anthropic-ai/claude-code"
fi

# Install missing required dependencies
if [ ${#MISSING[@]} -gt 0 ]; then
    echo ""
    echo "  Installing missing packages: ${MISSING[*]}"
    sudo apt update -qq
    sudo apt install -y "${MISSING[@]}"
    echo "  [OK] Dependencies installed"
else
    echo ""
    echo "  All required dependencies are installed."
fi

# ============================================================
# Step 2: Create bot/data directory
# ============================================================
echo ""
echo "--- Step 2: Creating data directories ---"
mkdir -p "$SCRIPT_DIR/bot/data"
echo "  [OK] bot/data/"

# ============================================================
# Step 3: Configure credentials (config.json)
# ============================================================
echo ""
echo "--- Step 3: Credentials (config.json) ---"

if [ -f "$CONFIG" ]; then
    echo "  config.json already exists."
    read -rp "  Overwrite? (y/N) " confirm
    if [[ ! "$confirm" =~ ^[Yy]$ ]]; then
        echo "  Keeping existing config.json."
        SKIP_CONFIG=true
    else
        SKIP_CONFIG=false
    fi
else
    SKIP_CONFIG=false
fi

if [ "$SKIP_CONFIG" = false ]; then
    if [ ! -f "$EXAMPLE" ]; then
        echo "  ERROR: config.json.example not found."
        exit 1
    fi

    cp "$EXAMPLE" "$CONFIG"

    echo ""
    echo "  Fill in your credentials below."
    echo "  Press Enter to skip optional fields."
    echo ""

    # --- Hosting (one.com SFTP) ---
    echo "  --- Hosting (one.com SFTP) ---"
    read -rp "  SFTP host (e.g. ssh.abc123.service.one): " sftp_host
    read -rp "  SFTP user (e.g. abc123_ssh): " sftp_user
    read -rsp "  SFTP password: " sftp_pass; echo
    read -rp "  Webroot path (e.g. /customers/X/X/X/abc123/webroots/xyz): " webroot

    # --- API Keys ---
    echo ""
    echo "  --- API Keys ---"
    read -rp "  OpenRouter API key (sk-or-v1-...): " openrouter_key

    # --- Email ---
    echo ""
    echo "  --- Email (for Charlie Webber AI worker) ---"
    read -rp "  Email address (e.g. info@yourdomain.com): " email_addr
    read -rsp "  Email password: " email_pass; echo
    read -rp "  Admin sender email (trusted address that triggers AI tasks): " admin_sender

    # --- SVEMO TAM ---
    echo ""
    echo "  --- SVEMO TAM (optional — needed for calendar + results scraping) ---"
    read -rp "  SVEMO username (personnummer, or skip): " svemo_user
    read -rsp "  SVEMO password (or skip): " svemo_pass; echo

    # --- Write config.json using Python for safe JSON handling ---
    python3 << PYEOF
import json

with open("$CONFIG") as f:
    c = json.load(f)

# Hosting
if "$sftp_host":
    c["hosting"]["sftp_host"] = "$sftp_host"
if "$sftp_user":
    c["hosting"]["sftp_user"] = "$sftp_user"
if "$sftp_pass":
    c["hosting"]["sftp_password"] = "$sftp_pass"
if "$webroot":
    c["hosting"]["webroot"] = "$webroot"

# API
if "$openrouter_key":
    c["api_keys"]["openrouter"] = "$openrouter_key"

# Email
if "$email_addr":
    c["email"]["address"] = "$email_addr"
if "$email_pass":
    c["email"]["password"] = "$email_pass"
if "$admin_sender":
    c["email"]["admin_sender"] = "$admin_sender"

# SVEMO
if "$svemo_user":
    c["data_sources"]["svemo_tam"]["username"] = "$svemo_user"
if "$svemo_pass":
    c["data_sources"]["svemo_tam"]["password"] = "$svemo_pass"

with open("$CONFIG", "w") as f:
    json.dump(c, f, indent=2, ensure_ascii=False)

PYEOF

    echo ""
    echo "  [OK] config.json created"
fi

# ============================================================
# Step 4: Initial scrape (optional)
# ============================================================
echo ""
echo "--- Step 4: Initial data scrape ---"
read -rp "  Run initial scrape now? This fetches data from all sources. (y/N) " do_scrape
if [[ "$do_scrape" =~ ^[Yy]$ ]]; then
    echo ""
    echo "  [1/7] WebTracking races..."
    python3 "$SCRIPT_DIR/bot/scrapers/webtracking.py" --force 2>&1 | sed 's/^/    /' || true

    echo "  [2/7] WebTracking results..."
    python3 "$SCRIPT_DIR/bot/scrapers/webtracking_results.py" --force 2>&1 | sed 's/^/    /' || true

    echo "  [3/7] SVEMO calendar..."
    python3 "$SCRIPT_DIR/bot/scrapers/svemo_calendar.py" --force 2>&1 | sed 's/^/    /' || true

    echo "  [4/7] SVEMO results..."
    python3 "$SCRIPT_DIR/bot/scrapers/svemo_results.py" --force 2>&1 | sed 's/^/    /' || true

    echo "  [5/7] UIM calendar..."
    python3 "$SCRIPT_DIR/bot/scrapers/uim_calendar.py" --force 2>&1 | sed 's/^/    /' || true

    echo "  [6/7] Rules & regulations..."
    python3 "$SCRIPT_DIR/bot/scrapers/svemo_rules.py" --force 2>&1 | sed 's/^/    /' || true

    echo "  [7/7] News aggregator..."
    python3 "$SCRIPT_DIR/bot/scrapers/news_aggregator.py" 2>&1 | sed 's/^/    /' || true

    echo ""
    echo "  Building pages from scraped data..."
    python3 "$SCRIPT_DIR/bot/builders/build_resultat.py" 2>&1 | sed 's/^/    /' || true
    python3 "$SCRIPT_DIR/bot/builders/build_kalender.py" 2>&1 | sed 's/^/    /' || true
    python3 "$SCRIPT_DIR/bot/builders/build_news.py" 2>&1 | sed 's/^/    /' || true

    echo "  [OK] Initial scrape complete"
else
    echo "  Skipped. Run manually later: bash bot/update.sh"
fi

# ============================================================
# Step 5: Set up systemd daemon (optional)
# ============================================================
echo ""
echo "--- Step 5: Daemon setup ---"
read -rp "  Install systemd service for auto-scraping + email worker? (y/N) " do_daemon
if [[ "$do_daemon" =~ ^[Yy]$ ]]; then
    mkdir -p "$SERVICE_DIR"
    cat > "$SERVICE_FILE" << SVCEOF
[Unit]
Description=SVERA Daemon — email tasks + weekly scrape + auto-deploy
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=$SCRIPT_DIR
ExecStart=/bin/bash $SCRIPT_DIR/bot/svera_daemon.sh
Restart=on-failure
RestartSec=60
Environment=PATH=$HOME/.local/bin:/usr/local/bin:/usr/bin:/bin

[Install]
WantedBy=default.target
SVCEOF

    systemctl --user daemon-reload
    systemctl --user enable svera.service
    systemctl --user start svera.service
    echo "  [OK] Daemon installed and started"
    echo "  Check status: systemctl --user status svera.service"
    echo "  View logs:    tail -f bot/daemon.log"
else
    echo "  Skipped. Set up later — see README.md"
fi

# ============================================================
# Done
# ============================================================
echo ""
echo "=========================================="
echo "  Setup complete!"
echo "=========================================="
echo ""
echo "Quick commands:"
echo "  bash bot/deploy.sh                  Deploy to one.com"
echo "  python3 bot/scrape_tracker.py       Check scrape status"
echo "  bash bot/update.sh                  Manual full scrape + deploy"
echo "  python3 bot/email_worker.py         Manual email check"
echo "  systemctl --user status svera        Daemon status"
echo ""
