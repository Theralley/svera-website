#!/usr/bin/env bash
# ============================================================
# SVERA Setup Script
# Creates config.json from user input
# ============================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CONFIG="$SCRIPT_DIR/config.json"
EXAMPLE="$SCRIPT_DIR/config.json.example"

echo ""
echo "=========================================="
echo "  SVERA — Initial Setup"
echo "=========================================="
echo ""

if [ -f "$CONFIG" ]; then
    echo "WARNING: config.json already exists."
    read -rp "Overwrite? (y/N) " confirm
    if [[ ! "$confirm" =~ ^[Yy]$ ]]; then
        echo "Aborted."
        exit 0
    fi
fi

if [ ! -f "$EXAMPLE" ]; then
    echo "ERROR: config.json.example not found."
    exit 1
fi

# Start from the example template
cp "$EXAMPLE" "$CONFIG"

echo "Fill in your credentials below."
echo "Press Enter to skip optional fields."
echo ""

# --- Hosting (one.com SFTP) ---
echo "--- Hosting (one.com SFTP) ---"
read -rp "SFTP host (e.g. ssh.abc123.service.one): " sftp_host
read -rp "SFTP user (e.g. abc123_ssh): " sftp_user
read -rsp "SFTP password: " sftp_pass; echo
read -rp "Webroot path (e.g. /customers/X/X/X/abc123/webroots/xyz): " webroot

# --- API Keys ---
echo ""
echo "--- API Keys ---"
read -rp "OpenRouter API key (sk-or-v1-...): " openrouter_key

# --- Email ---
echo ""
echo "--- Email (for Charlie Webber AI worker) ---"
read -rp "Email address (e.g. info@svera.nu): " email_addr
read -rsp "Email password: " email_pass; echo
read -rp "Admin sender email (trusted address that triggers AI tasks): " admin_sender

# --- SVEMO TAM ---
echo ""
echo "--- SVEMO TAM (optional — needed for calendar + results scraping) ---"
read -rp "SVEMO username (personnummer, or skip): " svemo_user
read -rsp "SVEMO password (or skip): " svemo_pass; echo

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
echo "=========================================="
echo "  config.json created!"
echo "=========================================="
echo ""
echo "Next steps:"
echo "  1. Review config.json and fill in any remaining fields"
echo "  2. Install sshpass:  sudo apt install sshpass"
echo "  3. Test deploy:      bash bot/deploy.sh"
echo "  4. Test scrapers:    python3 bot/scrape_tracker.py"
echo "  5. Start daemon:     See README.md for systemd setup"
echo ""
