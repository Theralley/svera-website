#!/usr/bin/env bash
# SVERA deploy script — uploads site to one.com via SFTP
# All credentials read from config.json
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

# Read all SFTP config from config.json
read_config() {
    /usr/bin/python3 -c "
import json, sys
with open('$PROJECT_DIR/config.json') as f:
    c = json.load(f)
h = c['hosting']
print(h.get('sftp_host', ''))
print(h.get('sftp_user', ''))
print(h.get('sftp_password', ''))
print(str(h.get('sftp_port', 22)))
print(h.get('webroot', ''))
" 2>/dev/null
}

CONFIG_LINES=$(read_config)
if [ -z "$CONFIG_LINES" ]; then
    echo "ERROR: Could not read config.json"
    exit 1
fi

SFTP_HOST=$(echo "$CONFIG_LINES" | sed -n '1p')
SFTP_USER=$(echo "$CONFIG_LINES" | sed -n '2p')
SFTP_PASS=$(echo "$CONFIG_LINES" | sed -n '3p')
SFTP_PORT=$(echo "$CONFIG_LINES" | sed -n '4p')
WEBROOT=$(echo "$CONFIG_LINES" | sed -n '5p')

if [ -z "$SFTP_PASS" ] || [ -z "$SFTP_HOST" ] || [ -z "$WEBROOT" ]; then
    echo "ERROR: Missing SFTP credentials in config.json"
    exit 1
fi

# Pre-deploy: detect content changes and update dates
echo "Checking for content changes..."
python3 "$SCRIPT_DIR/check_content_changes.py" || echo "WARNING: content change check failed"

echo ""
echo "Deploying SVERA to one.com..."
echo "Host: $SFTP_HOST"
echo "Webroot: $WEBROOT"

# Build SFTP commands — .htaccess + favicon + CSS + JS
CMDS="put $PROJECT_DIR/.htaccess $WEBROOT/.htaccess
put $PROJECT_DIR/favicon.ico $WEBROOT/favicon.ico
put $PROJECT_DIR/assets/css/style.css $WEBROOT/assets/css/style.css
put $PROJECT_DIR/assets/js/main.js $WEBROOT/assets/js/main.js
"

# Add ALL HTML files in project root
for html in "$PROJECT_DIR"/*.html; do
  if [ -f "$html" ]; then
    CMDS+="put $html $WEBROOT/$(basename "$html")
"
  fi
done

# Add images
if [ -d "$PROJECT_DIR/assets/images" ]; then
  for img in "$PROJECT_DIR"/assets/images/*; do
    if [ -f "$img" ]; then
      CMDS+="put $img $WEBROOT/assets/images/$(basename "$img")
"
    fi
  done
fi

# Add uploaded PDFs
if [ -d "$PROJECT_DIR/assets/uploads" ]; then
  CMDS+="-mkdir $WEBROOT/assets/uploads
"
  for pdf in "$PROJECT_DIR"/assets/uploads/*; do
    if [ -f "$pdf" ]; then
      CMDS+="put $pdf $WEBROOT/assets/uploads/$(basename "$pdf")
"
    fi
  done
fi

CMDS+="quit
"

if echo "$CMDS" | sshpass -p "$SFTP_PASS" sftp -o StrictHostKeyChecking=no -o BatchMode=no -P "$SFTP_PORT" "$SFTP_USER@$SFTP_HOST"; then
    echo "Deploy complete!"
else
    echo "ERROR: SFTP deploy failed"
    exit 1
fi
