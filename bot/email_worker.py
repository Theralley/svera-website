#!/usr/bin/env python3
"""SVERA Email Worker — "Charlie Webber, the web developer"

Smart email-to-AI pipeline that classifies tasks and routes them
with ZDR (Zero Data Retention) compliance for personal data:

  LOW (no names)  → DeepSeek V4 Pro (cheap, fast)
  LOW (names)     → Qwen ZDR (protects personal data)
  MEDIUM          → Qwen ZDR (always)
  HIGH (no names) → DeepSeek crafts prompt → Claude Code CLI
  HIGH (names)    → Qwen ZDR crafts prompt → mask names → Claude Code CLI

Flow:
  1. IMAP: fetch unread emails from admin (configured in config.json)
  2. Extract subject + body + PDF attachments
  3. DeepSeek classifies: LOW / MEDIUM / HIGH
  4. Detect personal names in email content (regex)
  5. Route based on level + name presence (see table above)
  6. Always reply with result + engine used (persona: Charlie Webber)
  7. Log task to history

Run: python3 bot/email_worker.py
"""
import imaplib
import email
import smtplib
from email.header import decode_header
from email.utils import parseaddr
from email.mime.text import MIMEText
import json
import os
import re
import shutil
import subprocess
import tempfile
import urllib.request
import urllib.error
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)
DOCUMENTS_DIR = os.path.expanduser("~/Documents")
CONFIG_FILE = os.path.join(PROJECT_DIR, "config.json")
LOG_FILE = os.path.join(SCRIPT_DIR, "email_worker.log")
PROCESSED_FILE = os.path.join(SCRIPT_DIR, "processed_emails.json")
TASK_HISTORY_FILE = os.path.join(SCRIPT_DIR, "task_history.json")

MAX_TURNS = 25
MAX_HISTORY = 20
CLAUDE_CLI = os.path.expanduser("~/.local/bin/claude")
CLAUDE_TIMEOUT = 600  # 10 minutes

BOT_NAME = "Charlie Webber"
BOT_TITLE = "SVERA Web Developer"


# ==============================================================
# Logging
# ==============================================================
def log(msg):
    line = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")


# ==============================================================
# Name detection — regex-based, supports Swedish characters
# ==============================================================
_NAME_PATTERN = re.compile(
    r'\b([A-ZAÄÖÅÉÜ][a-zàáâãäåæçèéêëìíîïðñòóôõöøùúûüýþÿ]+'
    r'(?:-[A-ZAÄÖÅÉÜ][a-zàáâãäåæçèéêëìíîïðñòóôõöøùúûüýþÿ]+)?)'
    r'(?:\s+'
    r'([A-ZAÄÖÅÉÜ][a-zàáâãäåæçèéêëìíîïðñòóôõöøùúûüýþÿ]+'
    r'(?:-[A-ZAÄÖÅÉÜ][a-zàáâãäåæçèéêëìíîïðñòóôõöøùúûüýþÿ]+)?))'
)

_NAME_STOPWORDS = {
    "Den", "Det", "De", "Denna", "Detta", "Dessa",
    "Alla", "Andra", "Varje", "Hela", "Samma",
    "Inte", "Eller", "Utan", "Under", "Efter", "Innan", "Mellan",
    "Hos", "Genom", "Enligt", "Sedan", "Charlie", "Webber",
    "The", "This", "That", "These", "Those",
    "With", "From", "About", "Into", "Your", "Their",
    "First", "Last", "Grand", "World", "South", "North", "East", "West",
    "Formula", "Powerboat", "Racing", "Championship", "British", "Masters",
    "Series", "Round", "Season", "Class", "Team", "River", "Area", "Lake",
    "January", "February", "March", "April", "June", "July",
    "August", "September", "October", "November", "December",
    "Svenska", "Svemo", "Evenemang",
}


def detect_names_regex(text):
    """Regex-based name detection. Returns list of unique 'First Last' strings."""
    if not text:
        return []
    matches = _NAME_PATTERN.findall(text)
    names, seen = [], set()
    for first, last in matches:
        if first in _NAME_STOPWORDS or last in _NAME_STOPWORDS:
            continue
        full = f"{first} {last}"
        if full not in seen:
            seen.add(full)
            names.append(full)
    return names


def has_names(text):
    """Quick boolean: does text contain personal names?"""
    return len(detect_names_regex(text)) > 0


def mask_names(text, names):
    """Replace names with [PERSON_1], [PERSON_2] etc.
    Returns (masked_text, name_map) where name_map = {placeholder: real_name}.
    """
    if not names:
        return text, {}
    sorted_names = sorted(names, key=len, reverse=True)
    name_map = {}
    masked = text
    for i, name in enumerate(sorted_names, 1):
        placeholder = f"[PERSON_{i}]"
        name_map[placeholder] = name
        masked = masked.replace(name, placeholder)
    return masked, name_map


# ==============================================================
# Config / state
# ==============================================================
def load_config():
    with open(CONFIG_FILE) as f:
        return json.load(f)


def load_processed():
    if os.path.exists(PROCESSED_FILE):
        try:
            with open(PROCESSED_FILE) as f:
                data = json.load(f)
            if len(data) > 500:
                data = data[-500:]
            return data
        except (json.JSONDecodeError, IOError):
            return []
    return []


def save_processed(ids):
    with open(PROCESSED_FILE, "w") as f:
        json.dump(ids, f, indent=2)


def load_task_history():
    if os.path.exists(TASK_HISTORY_FILE):
        try:
            with open(TASK_HISTORY_FILE) as f:
                history = json.load(f)
            return history[-MAX_HISTORY:]
        except (json.JSONDecodeError, IOError):
            return []
    return []


def save_task(subject, body, result_summary, success, engine="deepseek", level="low"):
    history = load_task_history()
    history.append({
        "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "subject": subject,
        "task": body[:200],
        "result": result_summary[:300],
        "success": success,
        "engine": engine,
        "level": level,
    })
    history = history[-MAX_HISTORY:]
    with open(TASK_HISTORY_FILE, "w") as f:
        json.dump(history, f, indent=2, ensure_ascii=False)


def format_history_for_prompt():
    history = load_task_history()
    if not history:
        return "Ingen tidigare historik."
    lines = []
    for t in history:
        status = "OK" if t.get("success") else "MISSLYCKADES"
        eng = t.get("engine", "?")
        lines.append(f"- [{t['date']}] [{status}] [{eng}] {t['subject']}: {t['result']}")
    return "\n".join(lines)


# ==============================================================
# Email replies — always reply, persona: Charlie Webber
# ==============================================================
def send_reply(email_cfg, admin_addr, original_subject, body_text, is_error=False):
    """Always send a reply. Charlie Webber persona."""
    try:
        tag = "FEL" if is_error else "OK"
        msg = MIMEText(body_text, "plain", "utf-8")
        msg["From"] = f"{BOT_NAME} <{email_cfg['address']}>"
        msg["To"] = admin_addr
        msg["Subject"] = f"[SVERA {tag}] {original_subject}"

        with smtplib.SMTP_SSL(email_cfg["smtp_host"], email_cfg["smtp_port"]) as smtp:
            smtp.login(email_cfg["address"], email_cfg["password"])
            smtp.send_message(msg)
        log(f"  Reply sent ({tag})")
    except Exception as e:
        log(f"  Failed to send reply: {e}")


def build_success_reply(subject, engine, level):
    engine_labels = {
        "claude": "Claude Code",
        "deepseek": "DeepSeek V4 Pro",
        "qwen-zdr": "Qwen ZDR (Zero Data Retention)",
    }
    engine_label = engine_labels.get(engine, engine)
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    return (
        f"Hej!\n\n"
        f"Uppgiften ar klar och deployad till svera.nu.\n\n"
        f"  Uppgift:  {subject}\n"
        f"  Motor:    {engine_label}\n"
        f"  Niva:     {level.upper()}\n"
        f"  Tid:      {ts}\n\n"
        f"Kolla sajten sa allt ser bra ut.\n\n"
        f"/ {BOT_NAME}\n"
        f"  {BOT_TITLE}\n"
    )


def build_error_reply(subject, error_msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    return (
        f"Hej!\n\n"
        f"Jag kunde tyvärr inte slutfora uppgiften.\n\n"
        f"  Uppgift:  {subject}\n"
        f"  Tid:      {ts}\n"
        f"  Fel:      {error_msg[:400]}\n\n"
        f"Skicka emailet igen for att forsoka pa nytt, "
        f"eller vanta tills admin kan kolla manuellt.\n\n"
        f"/ {BOT_NAME}\n"
        f"  {BOT_TITLE}\n"
    )


# ==============================================================
# PDF handling
# ==============================================================
UPLOADS_DIR = os.path.join(PROJECT_DIR, "assets", "uploads")


def save_pdfs_to_project(attachments):
    if not attachments:
        return []
    os.makedirs(UPLOADS_DIR, exist_ok=True)
    saved = []
    for fn, tmppath in attachments:
        safe = fn.replace(" ", "-").replace("/", "_").replace("\\", "_")
        dest = os.path.join(UPLOADS_DIR, safe)
        if os.path.exists(dest):
            base, ext = os.path.splitext(safe)
            safe = f"{base}_{datetime.now().strftime('%Y%m%d%H%M')}{ext}"
            dest = os.path.join(UPLOADS_DIR, safe)
        shutil.copy2(tmppath, dest)
        web_path = f"assets/uploads/{safe}"
        saved.append((fn, web_path))
        log(f"  PDF saved: {web_path}")
    return saved


# ==============================================================
# Email parsing
# ==============================================================
def decode_str(s):
    if s is None:
        return ""
    decoded = decode_header(s)
    parts = []
    for part, charset in decoded:
        if isinstance(part, bytes):
            parts.append(part.decode(charset or "utf-8", errors="replace"))
        else:
            parts.append(part)
    return " ".join(parts)


def get_body(msg):
    text_body = None
    if msg.is_multipart():
        for part in msg.walk():
            ct = part.get_content_type()
            disp = str(part.get("Content-Disposition", ""))
            if "attachment" in disp:
                continue
            if ct == "text/plain" and text_body is None:
                payload = part.get_payload(decode=True)
                if payload:
                    charset = part.get_content_charset() or "utf-8"
                    text_body = payload.decode(charset, errors="replace")
    else:
        if msg.get_content_type() == "text/plain":
            payload = msg.get_payload(decode=True)
            if payload:
                charset = msg.get_content_charset() or "utf-8"
                text_body = payload.decode(charset, errors="replace")
    return text_body.strip() if text_body else ""


def get_attachments(msg, tmpdir):
    files = []
    if not msg.is_multipart():
        return files
    for part in msg.walk():
        fn = part.get_filename()
        if not fn:
            continue
        fn = decode_str(fn)
        if not fn.lower().endswith(".pdf"):
            log(f"  Ignored attachment: {fn} (only .pdf)")
            continue
        safe_fn = fn.replace("/", "_").replace("\\", "_")
        path = os.path.join(tmpdir, safe_fn)
        payload = part.get_payload(decode=True)
        if payload:
            with open(path, "wb") as f:
                f.write(payload)
            files.append((fn, path))
            log(f"  PDF: {fn} ({len(payload)} bytes)")
    return files


# ==============================================================
# OpenRouter API — shared by classifier, prompt crafter, agent
# ==============================================================
def call_openrouter_simple(prompt, api_key, model, max_tokens=256, zdr=False):
    """Single-turn, no tools. For classifier and prompt crafter."""
    url = "https://openrouter.ai/api/v1/chat/completions"
    body = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
    }
    if zdr:
        body["provider"] = {"zdr": True}
    payload = json.dumps(body).encode("utf-8")

    req = urllib.request.Request(url, data=payload, headers={
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://svera.nu",
        "X-Title": "SVERA Charlie Webber",
    })

    try:
        resp = urllib.request.urlopen(req, timeout=60)
        data = json.loads(resp.read().decode())
        return data["choices"][0]["message"]["content"].strip()
    except Exception as e:
        log(f"  API simple call failed: {e}")
        return None


def call_openrouter(messages, api_key, model, zdr=False):
    """Multi-turn with tools. For agent loop (DeepSeek or Qwen ZDR)."""
    url = "https://openrouter.ai/api/v1/chat/completions"
    body = {
        "model": model,
        "messages": messages,
        "tools": TOOLS,
        "max_tokens": 4096,
    }
    if zdr:
        body["provider"] = {"zdr": True}
    payload = json.dumps(body).encode("utf-8")

    req = urllib.request.Request(url, data=payload, headers={
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://svera.nu",
        "X-Title": "SVERA Charlie Webber",
    })

    try:
        resp = urllib.request.urlopen(req, timeout=120)
        data = json.loads(resp.read().decode())
        return data["choices"][0]["message"]
    except urllib.error.HTTPError as e:
        body = e.read().decode() if e.fp else ""
        log(f"  API error {e.code}: {body[:300]}")
        return None
    except Exception as e:
        log(f"  API error: {e}")
        return None


# ==============================================================
# Qwen ZDR name extraction — for HIGH tasks before Claude
# ==============================================================
def extract_names_with_qwen(text, api_key, model_zdr):
    """Use Qwen (ZDR) to extract all personal names from text.
    Falls back to regex if Qwen fails."""
    prompt = (
        "Lista ALLA personnamn (for- och efternamn) som forekommar i foljande text. "
        "Svara med ETT namn per rad, inget annat. Om inga namn finns, svara INGA.\n\n"
        f"TEXT:\n{text[:2000]}\n\nNAMN:"
    )
    result = call_openrouter_simple(prompt, api_key, model_zdr, max_tokens=256, zdr=True)
    if not result or "INGA" in result.upper():
        return []
    names = []
    for line in result.strip().split("\n"):
        line = line.strip().strip("-").strip("*").strip()
        line = re.sub(r'^\d+[\.\)]\s*', '', line).strip()
        if line and len(line) > 2 and " " in line:
            names.append(line)
    return names if names else detect_names_regex(text)


# ==============================================================
# Task classifier — LOW / MEDIUM / HIGH
# ==============================================================
# Keywords that indicate content creation tasks — DeepSeek struggles with these
# so we escalate to at least MEDIUM (Qwen ZDR) for better HTML output quality
_CONTENT_CREATION_KEYWORDS = re.compile(
    r'(?:inl[aä]gg|skapa.*(?:nyhet|post|artikel)|skriv.*(?:nyhet|post|artikel)|'
    r'publicera|l[aä]gg\s*till.*(?:nyhet|post)|skapa\s*(?:en|ett)\s)',
    re.IGNORECASE,
)


def classify_task(subject, body, api_key, model):
    """DeepSeek classifies task complexity. Returns 'low', 'medium', or 'high'.

    Content creation tasks (posts, articles) are escalated to at least 'medium'
    because the cheaper model can struggle with HTML news card templates.
    """
    prompt = (
        "Du ar en task-klassificerare for webbplatsen svera.nu (statisk HTML/CSS/JS).\n"
        "Klassificera uppgiften som LOW, MEDIUM eller HIGH.\n\n"
        "LOW = enkel textandring, byta ett ord, "
        "andra en lank, trigga deploy, ta bort nagon rad.\n\n"
        "MEDIUM = lagga till/skapa nyheter eller inlagg, fixa en bugg i en fil, "
        "smarre CSS-tweak, andra en specifik "
        "komponent, lagga till en enkel funktion i en befintlig fil.\n\n"
        "HIGH = designandringar, layout-omgorningar, andringar som spanner "
        "flera filer, ny funktionalitet, nya scrapers, JavaScript-andringar, "
        "responsiv design, refaktorering, 'gor om', 'fixa UI', 'uppdatera designen', "
        "nya sidor, integration med externa tjanster.\n\n"
        f"Amne: {subject}\n"
        f"Innehall: {body[:500]}\n\n"
        "Svara med EXAKT ett ord: LOW, MEDIUM eller HIGH"
    )

    answer = call_openrouter_simple(prompt, api_key, model, max_tokens=10)
    level = "low"
    if answer:
        answer = answer.upper().strip()
        if "HIGH" in answer:
            level = "high"
        elif "MEDIUM" in answer:
            level = "medium"

    # Escalate content creation tasks — DeepSeek can't reliably produce
    # correct HTML news cards, so route these to Qwen ZDR at minimum
    if level == "low":
        combined = f"{subject}\n{body[:300]}"
        if _CONTENT_CREATION_KEYWORDS.search(combined):
            log(f"  Escalating LOW -> MEDIUM (content creation detected)")
            level = "medium"

    return level


# ==============================================================
# Prompt crafter — DeepSeek writes a structured prompt for Claude
# ==============================================================
def craft_claude_prompt(subject, body, saved_pdfs, api_key, model):
    """DeepSeek reads the raw email and crafts a clear, structured prompt for Claude Code."""
    pdf_context = ""
    if saved_pdfs:
        pdf_lines = [f"  - {fn} -> {wp}" for fn, wp in saved_pdfs]
        pdf_context = "\nBifogade PDF:er (sparade i projektet):\n" + "\n".join(pdf_lines)

    prompt = (
        "Du ar en prompt-ingenjor. Las foljande email-uppgift och skriv en "
        "TYDLIG, STRUKTURERAD prompt pa engelska for en AI-kodagent (Claude Code) "
        "som ska utfora uppgiften pa webbplatsen svera.nu.\n\n"
        "Prompten ska:\n"
        "1. Borja med en tydlig sammanfattning av vad som ska goras\n"
        "2. Lista specifika steg i ordning\n"
        "3. Namna vilka filer som troligen berors\n"
        "4. Inkludera regler: las filer forst, behall befintligt innehall, deploya nar klar\n"
        "5. Vara max 300 ord\n\n"
        f"EMAIL:\n"
        f"Amne: {subject}\n"
        f"Innehall:\n{body}\n"
        f"{pdf_context}\n\n"
        "SVERA-KONTEXT:\n"
        "- Statisk HTML/CSS/JS-sajt pa svera.nu\n"
        f"- Projektmapp: {PROJECT_DIR}\n"
        "- Sidor: index.html, resultat.html, kalender.html, klasser.html, "
        "klubbar.html, team.html, arkivet.html, om.html, sponsorer.html, "
        "nyheter.html, social.html, champions.html, kontakt.html, api.html, policy.html\n"
        "- CSS: assets/css/style.css\n"
        "- JS: assets/js/main.js\n"
        "- Scrapers: bot/scrapers/ (webtracking, svemo, uim, news, social)\n"
        "- Builders: bot/builders/ (kalender, resultat, news, champions, rss, social)\n"
        "- Deploy: bash bot/deploy.sh\n"
        "- Navigation: Om SVERA (dropdown: Om SVERA + Sponsorer), "
        "Nyheter (dropdown: Nyheter + Social), Klubbar (dropdown: Klubbar + Team)\n"
        "- VIKTIGT: Las CLAUDE.md for fullstandig dokumentation av alla sidor, "
        "scrapers, builders och nyhetsformat\n\n"
        "Skriv prompten nu (pa engelska):"
    )

    result = call_openrouter_simple(prompt, api_key, model, max_tokens=1024)
    if result:
        log(f"  Crafted prompt: {result[:200]}...")
        return result
    # Fallback: use raw email as prompt
    log(f"  Prompt crafting failed, using raw email")
    return f"Task from email:\nSubject: {subject}\nBody: {body}"


# ==============================================================
# Tool definitions for DeepSeek agent
# ==============================================================
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read a file from the project. Returns the file contents.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Path relative to project root"}
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Write/overwrite a file with new content.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Path relative to project root"},
                    "content": {"type": "string", "description": "The full file content"}
                },
                "required": ["path", "content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "edit_file",
            "description": "Replace a specific string in a file.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Path relative to project root"},
                    "old_string": {"type": "string", "description": "Exact string to find"},
                    "new_string": {"type": "string", "description": "Replacement string"}
                },
                "required": ["path", "old_string", "new_string"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "run_bash",
            "description": "Run a bash command in the project directory.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "The bash command to run"}
                },
                "required": ["command"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_files",
            "description": "List files in a directory.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Directory path relative to project root"}
                },
                "required": ["path"]
            }
        }
    },
]


# ==============================================================
# Tool execution
# ==============================================================
def resolve_path(path):
    if os.path.isabs(path):
        return path
    return os.path.join(PROJECT_DIR, path)


def exec_tool(name, args):
    try:
        if name == "read_file":
            fpath = resolve_path(args["path"])
            if not os.path.exists(fpath):
                return f"Error: file not found: {fpath}"
            with open(fpath, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
            if len(content) > 30000:
                return content[:30000] + f"\n\n... (truncated, {len(content)} chars total)"
            return content

        elif name == "write_file":
            fpath = resolve_path(args["path"])
            os.makedirs(os.path.dirname(fpath), exist_ok=True)
            with open(fpath, "w", encoding="utf-8") as f:
                f.write(args["content"])
            return f"OK: wrote {len(args['content'])} chars to {fpath}"

        elif name == "edit_file":
            fpath = resolve_path(args["path"])
            if not os.path.exists(fpath):
                return f"Error: file not found: {fpath}"
            with open(fpath, "r", encoding="utf-8") as f:
                content = f.read()
            old = args["old_string"]
            if old not in content:
                return f"Error: old_string not found in {fpath}"
            count = content.count(old)
            content = content.replace(old, args["new_string"], 1)
            with open(fpath, "w", encoding="utf-8") as f:
                f.write(content)
            return f"OK: replaced in {fpath} ({count} occurrence(s), replaced first)"

        elif name == "run_bash":
            result = subprocess.run(
                args["command"], shell=True, cwd=PROJECT_DIR,
                capture_output=True, text=True, timeout=120,
            )
            output = ""
            if result.stdout:
                output += result.stdout
            if result.stderr:
                output += "\nSTDERR: " + result.stderr
            if result.returncode != 0:
                output += f"\n(exit code {result.returncode})"
            return output.strip() or "(no output)"

        elif name == "list_files":
            dpath = resolve_path(args["path"])
            if not os.path.isdir(dpath):
                return f"Error: not a directory: {dpath}"
            entries = sorted(os.listdir(dpath))
            lines = []
            for e in entries:
                full = os.path.join(dpath, e)
                if os.path.isdir(full):
                    lines.append(f"  {e}/")
                else:
                    lines.append(f"  {e} ({os.path.getsize(full)} bytes)")
            return "\n".join(lines) or "(empty)"

        else:
            return f"Error: unknown tool: {name}"
    except Exception as e:
        return f"Error: {e}"


# ==============================================================
# Claude Code runner — for HIGH tasks
# ==============================================================
def run_claude(crafted_prompt):
    """Run task via Claude Code CLI with the parent CLAUDE.md context."""
    if not os.path.exists(CLAUDE_CLI):
        log(f"  Claude CLI not found at {CLAUDE_CLI}")
        return False, "Claude Code CLI not found"

    history_text = format_history_for_prompt()

    # Point Claude at ~/Documents/CLAUDE.md which has all the skill refs
    parent_claude_md = os.path.join(DOCUMENTS_DIR, "CLAUDE.md")
    claude_md_ref = ""
    if os.path.exists(parent_claude_md):
        claude_md_ref = (
            f"IMPORTANT: Read {parent_claude_md} for your full agent configuration.\n"
            f"It references UI/UX skills, scraping tools, and other resources you can use.\n\n"
        )

    full_prompt = (
        f"You are Charlie Webber, the SVERA web developer.\n"
        f"You maintain the website svera.nu (static HTML/CSS/JS).\n"
        f"Project directory: {PROJECT_DIR}\n\n"
        f"{claude_md_ref}"
        f"Also read {PROJECT_DIR}/CLAUDE.md for project-specific rules.\n\n"
        f"RULES:\n"
        f"- ALWAYS read relevant files before editing them\n"
        f"- Keep all existing content — never delete anything unless asked\n"
        f"- All text content in Swedish (lang='sv')\n"
        f"- When done, deploy with: bash bot/deploy.sh\n"
        f"- Be thorough but focused — do what's asked, nothing extra\n\n"
        f"RECENT TASK HISTORY:\n{history_text}\n\n"
        f"---\n\n"
        f"TASK:\n{crafted_prompt}\n"
    )

    log(f"  Starting Claude Code (timeout: {CLAUDE_TIMEOUT}s)...")
    try:
        result = subprocess.run(
            [
                CLAUDE_CLI, "-p",
                "--dangerously-skip-permissions",
                "--max-turns", "50",
                "--output-format", "text",
                full_prompt,
            ],
            cwd=PROJECT_DIR,
            capture_output=True,
            text=True,
            timeout=CLAUDE_TIMEOUT,
            env={
                **{k: v for k, v in os.environ.items() if k != "CLAUDECODE"},
                "CLAUDE_CODE_ENTRYPOINT": "cli",
            },
        )
        output = result.stdout.strip()
        if result.returncode != 0:
            err = result.stderr.strip()
            log(f"  Claude exited {result.returncode}")
            if err:
                log(f"  stderr: {err[:500]}")
            if output:
                log(f"  stdout: {output[:500]}")
                return True, output[:500]
            return False, f"Claude Code exit {result.returncode}: {err[:200]}"

        log(f"  Claude done")
        if output:
            log(f"  Result: {output[:500]}")
        return True, output[:500] if output else "Uppgift utford via Claude Code"

    except subprocess.TimeoutExpired:
        log(f"  Claude timed out ({CLAUDE_TIMEOUT}s)")
        return False, f"Claude Code timeout ({CLAUDE_TIMEOUT}s)"
    except Exception as e:
        log(f"  Claude error: {e}")
        return False, f"Claude Code fel: {e}"


# ==============================================================
# DeepSeek agent loop — for LOW / MEDIUM tasks
# ==============================================================
def run_agent(prompt, api_key, model, zdr=False):
    """Tool-use agent loop via DeepSeek or Qwen ZDR. Returns (success, summary)."""
    model_label = "Qwen ZDR" if zdr else "DeepSeek"
    log(f"  Starting {model_label} agent...")

    claude_md = ""
    claude_md_path = os.path.join(PROJECT_DIR, "CLAUDE.md")
    if os.path.exists(claude_md_path):
        with open(claude_md_path) as f:
            claude_md = f.read()

    messages = [
        {
            "role": "system",
            "content": (
                "Du ar Charlie Webber, SVERA:s webbutvecklare.\n"
                "Du underhaller webbplatsen svera.nu (statisk HTML/CSS/JS).\n"
                "Du har verktyg for att lasa, redigera, skriva filer och kora bash.\n"
                "Projektet: " + PROJECT_DIR + "\n\n"
                "PROJEKTSTRUKTUR:\n" + claude_md + "\n\n"
                "REGLER:\n"
                "- Gor BARA det uppgiften ber om\n"
                "- Las ALLTID relevanta filer FORST\n"
                "- Anvand edit_file for andringar, write_file bara for helt nya filer\n"
                "- Nyheter laggs i index.html div.news-list\n"
                "- Skapa ALDRIG separata HTML-filer for nyheter\n"
                "- Nyhets-kort har INGEN bild/news-image — anvand compact format:\n"
                '  <article class="news-card" style="border-left:4px solid FARG;">'
                '<div class="news-body">\n'
                '    <div class="news-meta">'
                '<span class="category" style="background:FARG;color:#fff;">Kategori</span>'
                '<span class="separator"></span>'
                '<span class="news-date">YYYY-MM-DD</span></div>\n'
                "    <h3>Rubrik</h3><p>Text</p>\n"
                '    <a href="url" class="read-more">Las mer &rarr;</a>\n'
                "  </div></article>\n"
                "- KATEGORI-FARGER (badge + border-left maste matcha):\n"
                "  Evenemang: #c0392b (rod) | Internationellt: #e67e22 (orange)\n"
                "  Ny funktion: linear-gradient(135deg,#ffd700,#f0c800) + color:#5a4700 + border #ffd700\n"
                "  Tavling: #2980b9 (bla) | Nyhet/Arkivet/Klasser: default gul (ingen inline style)\n"
                "- VIKTIGT: news-date ska ALLTID vara dagens datum (publiceringsdatum), "
                "INTE evenemangsdatum. Evenemangsdatum skrivs i texten.\n"
                "  Dagens datum: " + datetime.now().strftime("%Y-%m-%d") + "\n"
                "- SORTERING: Nya kort laggs FORST i div.news-list (nyast overst)\n"
                "- FORMATERING: Anvand ALDRIG <ul>/<li> i nyhetskort. "
                "Skriv info som inline text med middot-separator: "
                "<strong>Var:</strong> X &middot; <strong>Nar:</strong> Y\n"
                "- LANKAR: Anvand ALDRIG href='#'. Om ingen riktig URL finns, "
                "skippa <a class='read-more'> helt.\n"
                "- PDF-bilagor ar sparade i assets/uploads/\n"
                "- Nar klar: run_bash('bash bot/deploy.sh')\n"
                "- Svara kort pa svenska (max 3 meningar)\n\n"
                "TIDIGARE UPPGIFTER:\n" + format_history_for_prompt() + "\n"
            )
        },
        {"role": "user", "content": prompt},
    ]

    for turn in range(MAX_TURNS):
        response = call_openrouter(messages, api_key, model, zdr=zdr)
        if response is None:
            log(f"  Agent failed at turn {turn + 1}")
            return False, "API-anrop misslyckades"

        messages.append(response)

        tool_calls = response.get("tool_calls")
        if not tool_calls:
            summary = response.get("content", "") or "Uppgift utford"
            log(f"  Agent done after {turn + 1} turns")
            if summary:
                log(f"  Result: {summary[:500]}")
            return True, summary

        for tc in tool_calls:
            fn_name = tc["function"]["name"]
            try:
                fn_args = json.loads(tc["function"]["arguments"])
            except json.JSONDecodeError:
                fn_args = {}

            log(f"  [{turn + 1}] {fn_name}({', '.join(f'{k}={repr(v)[:60]}' for k, v in fn_args.items())})")
            result = exec_tool(fn_name, fn_args)

            messages.append({
                "role": "tool",
                "tool_call_id": tc["id"],
                "content": result,
            })

    log(f"  Agent hit max turns ({MAX_TURNS})")
    return True, "Uppgift avslutad (max antal steg)"


# ==============================================================
# Email prompt builder
# ==============================================================
def build_prompt(subject, body, tmp_attachments, saved_pdfs):
    parts = [
        f"UPPGIFT VIA EMAIL",
        f"Amne: {subject}",
        f"",
        f"Innehall:",
        body,
    ]
    if tmp_attachments:
        parts.append("")
        parts.append("Bifogade PDF-filer (las med read_file):")
        for fn, path in tmp_attachments:
            parts.append(f"  - {path}")
    if saved_pdfs:
        parts.append("")
        parts.append("PDF:er sparade i projektet:")
        for fn, web_path in saved_pdfs:
            parts.append(f'  - {fn} -> <a href="{web_path}" target="_blank">{fn}</a>')
    parts.extend(["", "Utfor uppgiften. Deploya nar klar: run_bash('bash bot/deploy.sh')"])
    return "\n".join(parts)


# ==============================================================
# Inbox checker — main pipeline
# ==============================================================
def check_inbox():
    config = load_config()
    email_cfg = config.get("email")
    api_cfg = config.get("api_keys", {})

    if not email_cfg:
        log("No email config")
        return 0

    admin = email_cfg.get("admin_sender", "").lower().strip()
    if not admin:
        log("No admin_sender")
        return 0

    api_key = api_cfg.get("openrouter", "")
    model = api_cfg.get("openrouter_model", "deepseek/deepseek-v4-pro")
    model_zdr = api_cfg.get("openrouter_model_fallback", "qwen/qwen-2.5-72b-instruct")
    if not api_key:
        log("No OpenRouter API key")
        return 0

    processed = load_processed()
    tasks_run = 0

    log("Connecting to IMAP...")
    try:
        mail = imaplib.IMAP4_SSL(email_cfg["imap_host"], email_cfg["imap_port"])
        mail.login(email_cfg["address"], email_cfg["password"])
        mail.select("INBOX")
    except Exception as e:
        log(f"IMAP failed: {e}")
        return 0

    try:
        status, messages = mail.search(None, "UNSEEN")
        if status != "OK" or not messages[0]:
            log("No unread emails")
            return 0

        msg_ids = messages[0].split()
        log(f"Found {len(msg_ids)} unread email(s)")

        for msg_id in msg_ids:
            status, data = mail.fetch(msg_id, "(RFC822)")
            if status != "OK":
                continue

            msg = email.message_from_bytes(data[0][1])
            sender = parseaddr(msg.get("From", ""))[1].lower().strip()
            subject = decode_str(msg.get("Subject", "(inget amne)"))
            message_id = msg.get("Message-ID", msg_id.decode())

            log(f"")
            log(f"Email: {subject}")
            log(f"  From: {sender}")

            if sender != admin:
                log(f"  SKIP — not admin")
                continue

            if message_id in processed:
                log(f"  SKIP — already processed")
                continue

            body = get_body(msg)
            if not body:
                log(f"  SKIP — empty body")
                processed.append(message_id)
                save_processed(processed)
                continue

            log(f"  Body: {len(body)} chars")

            with tempfile.TemporaryDirectory(prefix="svera_email_") as tmpdir:
                attachments = get_attachments(msg, tmpdir)
                saved_pdfs = save_pdfs_to_project(attachments)

                # Step 1: Classify — LOW / MEDIUM / HIGH
                level = classify_task(subject, body, api_key, model)
                log(f"  Level: {level.upper()}")

                # Step 1b: Detect personal names
                email_text = f"{subject}\n{body}"
                names_found = detect_names_regex(email_text)
                if names_found:
                    log(f"  Names detected ({len(names_found)}): {', '.join(names_found[:5])}")

                # Step 2: Route based on level + name presence
                if level == "high":
                    # HIGH: Qwen ZDR scans for names → mask → Claude executes
                    log(f"  HIGH task — scanning for names with Qwen ZDR...")
                    accurate_names = extract_names_with_qwen(email_text, api_key, model_zdr)

                    if accurate_names:
                        log(f"  Names found — crafting prompt with Qwen ZDR...")
                        crafted = craft_claude_prompt(subject, body, saved_pdfs, api_key, model_zdr)
                        log(f"  Masking {len(accurate_names)} name(s) before Claude...")
                        crafted, name_map = mask_names(crafted, accurate_names)
                        log(f"  Masked: {list(name_map.keys())}")
                    else:
                        log(f"  No names — crafting prompt with DeepSeek...")
                        crafted = craft_claude_prompt(subject, body, saved_pdfs, api_key, model)

                    log(f"  Routing to Claude Code...")
                    engine = "claude"
                    success, result_summary = run_claude(crafted)

                elif level == "medium" or names_found:
                    # MEDIUM (always) or LOW+names → Qwen ZDR
                    reason = "medium task" if level == "medium" else "names detected"
                    log(f"  Routing to Qwen ZDR ({reason})...")
                    engine = "qwen-zdr"
                    prompt = build_prompt(subject, body, attachments, saved_pdfs)
                    success, result_summary = run_agent(prompt, api_key, model_zdr, zdr=True)

                else:
                    # LOW + no names → DeepSeek (cheap, fast)
                    log(f"  Routing to DeepSeek ({level}, no names)...")
                    engine = "deepseek"
                    prompt = build_prompt(subject, body, attachments, saved_pdfs)
                    success, result_summary = run_agent(prompt, api_key, model)

                # Step 3: Log
                save_task(subject, body, result_summary, success, engine=engine, level=level)

                # Step 4: Always reply
                if success:
                    log(f"  DONE ({engine}/{level})")
                    tasks_run += 1
                    reply_body = build_success_reply(subject, engine, level)
                    send_reply(email_cfg, admin, subject, reply_body, is_error=False)
                else:
                    log(f"  FAILED ({engine}/{level})")
                    reply_body = build_error_reply(subject, result_summary)
                    send_reply(email_cfg, admin, subject, reply_body, is_error=True)

            processed.append(message_id)
            save_processed(processed)

    finally:
        try:
            mail.close()
        except Exception:
            pass
        mail.logout()

    log(f"Inbox check complete: {tasks_run} task(s)")
    return tasks_run


if __name__ == "__main__":
    log("=" * 50)
    log(f"{BOT_NAME} — {BOT_TITLE}")
    log("=" * 50)
    check_inbox()
