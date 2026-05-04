#!/usr/bin/env python3
"""SVERA Email Worker — "Charlie Webber, the web developer"

Email-to-AI pipeline for svera.nu.

  LOW (no names)   → DeepSeek V4 Pro agent loop
  LOW (with names) → Qwen ZDR (Zero Data Retention)
  MEDIUM           → Qwen ZDR
  HIGH             → DeepSeek/Qwen ZDR crafts prompt → Claude Code CLI (with name masking)

Privacy: personal names trigger ZDR routing. HIGH tasks scan for names with Qwen
and mask them as [PERSON_1], [PERSON_2]... before handing the prompt to Claude.

Two-step approval flow:
  1. Email arrives from an approved sender (config.email.admin_senders / admin_sender).
  2. Subject/body must contain a trigger keyword
     (update, uppdatera, fixa, ändra, byt ut, skapa, lägg till, create, add).
  3. Worker classifies + researches + drafts a recommendation, replies:
       "Här är min rekommendation för plan #SXXXX..."
     and saves a pending plan (bot/pending_plans.json).
  4. Sender replies with "jag godkanner" / "accept". Worker executes,
     deploys, and replies with the result.
  5. Sender can revise: "uppdatera plan #SXXXX <new instructions>" → re-research + re-draft.
  6. Pending plans expire after PLAN_TTL_DAYS. Cancel with "avbryt"/"cancel".

Run: python3 bot/email_worker.py
"""
import imaplib
import email
import smtplib
from email.header import decode_header
from email.utils import parseaddr
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from html import escape as html_escape
import json
import os
import re
import shutil
import subprocess
import tempfile
import urllib.request
import urllib.error
from datetime import datetime, timedelta

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)
DOCUMENTS_DIR = os.path.expanduser("~/Documents")
CONFIG_FILE = os.path.join(PROJECT_DIR, "config.json")
LOG_FILE = os.path.join(SCRIPT_DIR, "email_worker.log")
PROCESSED_FILE = os.path.join(SCRIPT_DIR, "processed_emails.json")
TASK_HISTORY_FILE = os.path.join(SCRIPT_DIR, "task_history.json")
PENDING_PLANS_FILE = os.path.join(SCRIPT_DIR, "pending_plans.json")
TASK_COUNTER_FILE = os.path.join(SCRIPT_DIR, ".task_counter")
TASK_ID_RE = re.compile(r'#?(S\d{3,5})\b', re.IGNORECASE)

MAX_TURNS = 25
MAX_HISTORY = 20
PLAN_TTL_DAYS = 7
CLAUDE_CLI = os.path.expanduser("~/.local/bin/claude")
CLAUDE_TIMEOUT = 600  # 10 minutes

DEFAULT_MODEL = "deepseek/deepseek-v4-pro"

BOT_NAME = "Charlie Webber"
BOT_TITLE = "SVERA — Web Developer"
SITE_DOMAIN = "svera.nu"
REPLY_TAG = "SVERA"


# Trigger keywords — fresh task is only acted upon if any of these appear
# (Swedish change-action verbs + English "update").
TRIGGER_PATTERN = re.compile(
    r'\b('
    r'updates?|updated|updating'
    r'|uppdatera(?:r|t|s|de)?|uppdatering(?:ar|en)?'
    r'|fixa(?:r|t|s|de)?|fix(?:es|ed|ing)?'
    r'|ändra(?:r|t|s|de)?|andra(?:r|t|s|de)?'
    r'|byt(?:a|er|t|s)?\s*ut'
    r'|skapa(?:r|t|s|de)?|skapande'
    r'|create[ds]?|creating'
    r'|lägg(?:er|a|s|t)?\s*(?:till|in)|lagg(?:er|a|s|t)?\s*(?:till|in)|add(?:s|ed|ing)?'
    r')\b',
    re.IGNORECASE | re.UNICODE,
)

# Approval keywords — short reply confirming a pending plan.
# Swedish "godkänna" has both single- and double-n forms across tenses
# (godkänner / godkänt / godkänd / godkände), so allow nn?.
APPROVAL_PATTERN = re.compile(
    r'\b('
    r'accepts?|accepted|approve[ds]?'
    r'|godk(?:ä|a)nn?(?:er|t|d|s|a|de|e)?'
    r'|kör\s*det?|kor\s*det?|gör\s*det|gor\s*det'
    r'|okej|okay'
    r')\b',
    re.IGNORECASE | re.UNICODE,
)

# Cancel keywords — short reply rejecting a pending plan
CANCEL_PATTERN = re.compile(
    r'\b('
    r'cancel(?:led)?|avbryt|stoppa|stopp'
    r'|nej\s*tack|nope|skippa|skip'
    r'|avbruten'
    r')\b',
    re.IGNORECASE | re.UNICODE,
)

# Edit-plan keywords — admin wants to revise a pending recommendation
EDIT_PLAN_PATTERN = re.compile(
    r'\b('
    r'uppdatera\s*plan(?:en)?|ändra\s*plan(?:en)?|andra\s*plan(?:en)?'
    r'|revidera\s*plan(?:en)?|reviderad\s*plan|ny\s*version'
    r'|update\s*plan|edit\s*plan|revise\s*plan'
    r')\b',
    re.IGNORECASE | re.UNICODE,
)


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

# Content-creation keywords — auto-escalate LOW → MEDIUM so Qwen handles
# the news-card HTML rather than DeepSeek (which struggles with templates).
_CONTENT_CREATION_KEYWORDS = re.compile(
    r'(?:inl[aä]gg|skapa.*(?:nyhet|post|artikel)|skriv.*(?:nyhet|post|artikel)|'
    r'publicera|l[aä]gg\s*till.*(?:nyhet|post)|skapa\s*(?:en|ett)\s)',
    re.IGNORECASE,
)


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
    return len(detect_names_regex(text)) > 0


def mask_names(text, names):
    """Replace names with [PERSON_1], [PERSON_2] etc.
    Returns (masked_text, name_map) where name_map = {placeholder: real_name}."""
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
# Logging
# ==============================================================
def log(msg):
    line = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")


# ==============================================================
# Reply text extraction — strip quoted previous messages
# ==============================================================
_QUOTE_HEADER = re.compile(
    r'^\s*('
    r'On\s.+?wrote:|'
    r'Den\s.+?skrev:|'
    r'Den\s.+?skrev\s.*?:|'
    r'From:\s.+|Från:\s.+|Skickat:\s.+|Sent:\s.+'
    r')\s*$',
    re.IGNORECASE,
)


def strip_quoted(body):
    """Return the active part of a reply, dropping quoted history."""
    if not body:
        return ""
    out = []
    for line in body.split("\n"):
        s = line.strip()
        if s.startswith(">"):
            continue
        if _QUOTE_HEADER.match(s):
            break
        out.append(line)
    return "\n".join(out).strip()


def has_trigger(subject, body):
    """True if any trigger verb appears in subject or body."""
    haystack = f"{subject}\n{body}"
    return bool(TRIGGER_PATTERN.search(haystack))


def is_approval(subject, body):
    """True if reply approves a pending plan."""
    text = f"{subject}\n{body}"
    if CANCEL_PATTERN.search(text):
        return False
    return bool(APPROVAL_PATTERN.search(text))


def is_edit_plan(subject, body):
    return bool(EDIT_PLAN_PATTERN.search(f"{subject}\n{body}"))


def extract_task_id(text):
    """Find a #R0042-style task ID in text. Returns the bare ID (e.g. 'R0042') or None."""
    if not text:
        return None
    m = TASK_ID_RE.search(text)
    return m.group(1).upper() if m else None


def next_task_id(plans=None):
    """Sequential 'R0001' style ID. Persists in TASK_COUNTER_FILE.
    Also scans existing plans so we never collide if the counter file is lost."""
    n = 0
    try:
        with open(TASK_COUNTER_FILE) as f:
            n = int(f.read().strip())
    except (FileNotFoundError, ValueError, OSError):
        pass
    if plans:
        for p in plans.values():
            tid = (p.get("task_id") or "").upper()
            m = re.match(r"^R(\d+)$", tid)
            if m:
                n = max(n, int(m.group(1)))
    n += 1
    try:
        with open(TASK_COUNTER_FILE, "w") as f:
            f.write(str(n))
    except OSError:
        pass
    return f"S{n:04d}"


def is_cancel(subject, body):
    text = f"{subject}\n{body}"
    return bool(CANCEL_PATTERN.search(text))


# ==============================================================
# Config / state
# ==============================================================
def load_config():
    with open(CONFIG_FILE) as f:
        return json.load(f)


def get_admin_senders(email_cfg):
    """Returns lowercase list of approved senders.
    Supports new admin_senders (list) and legacy admin_sender (string)."""
    senders = email_cfg.get("admin_senders") or []
    if isinstance(senders, str):
        senders = [senders]
    legacy = email_cfg.get("admin_sender")
    if legacy:
        senders = list(senders) + [legacy]
    return [s.strip().lower() for s in senders if s and s.strip()]


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
# Pending plans (recommendation awaiting approval)
# ==============================================================
def normalize_msgid(s):
    if not s:
        return ""
    s = s.strip()
    if s.startswith("<") and s.endswith(">"):
        s = s[1:-1]
    return s.strip()


def load_pending_plans():
    if not os.path.exists(PENDING_PLANS_FILE):
        return {}
    try:
        with open(PENDING_PLANS_FILE) as f:
            plans = json.load(f)
    except (json.JSONDecodeError, IOError):
        return {}
    # Backfill task_id on legacy plans (pre-task-ID worker)
    dirty = False
    for pid, p in plans.items():
        if not p.get("task_id"):
            p["task_id"] = next_task_id(plans)
            dirty = True
    if dirty:
        save_pending_plans(plans)
    return plans


def save_pending_plans(plans):
    with open(PENDING_PLANS_FILE, "w") as f:
        json.dump(plans, f, indent=2, ensure_ascii=False)


def cleanup_expired_pending(plans):
    """Drop plans older than PLAN_TTL_DAYS. Returns updated dict."""
    cutoff = datetime.now() - timedelta(days=PLAN_TTL_DAYS)
    fresh = {}
    for pid, plan in plans.items():
        try:
            created = datetime.fromisoformat(plan["created_at"])
            if created >= cutoff:
                fresh[pid] = plan
            else:
                log(f"  Plan expired: {pid} ({plan.get('subject', '?')})")
        except (ValueError, KeyError):
            fresh[pid] = plan
    return fresh


def find_pending_for_reply(plans, in_reply_to_ids, sender, task_id=None):
    """Find a pending plan that matches a reply.
    Priority: explicit task_id > In-Reply-To/References + sender > most recent for sender.
    The sender check is skipped when task_id matches — admins can reference a plan
    even from a fresh email."""
    sender = sender.lower().strip()
    # 1) Explicit task ID — highest priority
    if task_id:
        for pid, p in plans.items():
            if (p.get("task_id") or "").upper() == task_id.upper():
                return pid, p
    # 2) Reply-chain match (with sender check)
    for ref in in_reply_to_ids:
        if not ref:
            continue
        if ref in plans and plans[ref].get("sender", "").lower() == sender:
            return ref, plans[ref]
    # 3) Most recent pending plan from same sender
    candidates = [
        (pid, p) for pid, p in plans.items()
        if p.get("sender", "").lower() == sender
    ]
    if candidates:
        candidates.sort(key=lambda x: x[1].get("created_at", ""), reverse=True)
        return candidates[0]
    return None, None


def collect_reply_refs(msg):
    """Pull In-Reply-To + References into a list of normalized message-IDs."""
    refs = []
    irt = msg.get("In-Reply-To", "")
    if irt:
        refs.append(normalize_msgid(irt))
    references = msg.get("References", "")
    if references:
        for r in references.split():
            refs.append(normalize_msgid(r))
    return [r for r in refs if r]


# ==============================================================
# Email replies — Roller Webber persona
# ==============================================================
def send_reply(email_cfg, admin_addr, original_subject, body, is_error=False, tag_override=None):
    """body may be a plain string OR a (text, html) tuple."""
    try:
        tag = tag_override or ("FEL" if is_error else "OK")
        if isinstance(body, tuple):
            text_body, html_body = body
            msg = MIMEMultipart("alternative")
            msg.attach(MIMEText(text_body, "plain", "utf-8"))
            msg.attach(MIMEText(html_body, "html", "utf-8"))
        else:
            msg = MIMEText(body, "plain", "utf-8")
        msg["From"] = f"{BOT_NAME} <{email_cfg['address']}>"
        msg["To"] = admin_addr
        msg["Subject"] = f"[{REPLY_TAG} {tag}] {original_subject}"

        with smtplib.SMTP_SSL(email_cfg["smtp_host"], email_cfg["smtp_port"]) as smtp:
            smtp.login(email_cfg["address"], email_cfg["password"])
            smtp.send_message(msg)
        log(f"  Reply sent ({tag})")
    except Exception as e:
        log(f"  Failed to send reply: {e}")


# ==============================================================
# Markdown → HTML (minimal subset, sized to what DeepSeek emits)
# ==============================================================
_FENCE = re.compile(r"^```(\w+)?\s*\n(.*?)\n```", re.DOTALL | re.MULTILINE)
_INLINE_CODE = re.compile(r"`([^`\n]+?)`")
_BOLD = re.compile(r"\*\*(.+?)\*\*", re.DOTALL)
_ITALIC = re.compile(r"(?<!\*)\*(?!\s)([^\*\n]+?)(?<!\s)\*(?!\*)")


def markdown_to_html(text):
    """Tiny converter: code fences, inline code, bold, italic, headers,
    ordered/unordered lists (with one level of nesting via 3+ space indent),
    and paragraphs separated by blank lines."""
    if not text:
        return ""

    # 1) Pull out fenced code blocks first; they bypass all other parsing.
    placeholders = {}
    def stash_fence(m):
        lang = (m.group(1) or "").strip()
        code = m.group(2)
        key = f"\x00FENCE{len(placeholders)}\x00"
        placeholders[key] = (
            f'<pre style="margin:12px 0;padding:12px 14px;background:#0f1320;'
            f'color:#e6e9f2;border-radius:6px;overflow-x:auto;'
            f'font-family:\'JetBrains Mono\',\'SF Mono\',Menlo,Consolas,monospace;'
            f'font-size:13px;line-height:1.5;">'
            f'<code>{html_escape(code)}</code></pre>'
        )
        return key
    text = _FENCE.sub(stash_fence, text)

    out_blocks = []
    lines = text.split("\n")
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        if not stripped:
            i += 1
            continue

        # Headers
        m = re.match(r"^(#{1,4})\s+(.+)$", stripped)
        if m:
            level = min(len(m.group(1)) + 1, 4)  # # → h2, ## → h3, etc.
            out_blocks.append(
                f'<h{level} style="margin:18px 0 8px;font-family:\'Big Shoulders Display\',Impact,Arial Black,sans-serif;'
                f'font-weight:800;letter-spacing:0.02em;color:#0a0e1f;">{_inline(m.group(2))}</h{level}>'
            )
            i += 1
            continue

        # Lists (ordered or unordered) — collect consecutive list items
        is_ol = bool(re.match(r"^\d+\.\s", stripped))
        is_ul = bool(re.match(r"^[-*]\s", stripped))
        if is_ol or is_ul:
            tag = "ol" if is_ol else "ul"
            items_html = []
            while i < len(lines):
                cur = lines[i]
                cur_stripped = cur.strip()
                if not cur_stripped:
                    # blank line breaks the list
                    break
                # Top-level item?
                m_top = re.match(r"^(?:\d+\.|[-*])\s+(.+)$", cur_stripped)
                indent = len(cur) - len(cur.lstrip(" "))
                same_kind_top = m_top and indent < 2 and (
                    (is_ol and re.match(r"^\d+\.\s", cur_stripped)) or
                    (is_ul and re.match(r"^[-*]\s", cur_stripped))
                )
                if same_kind_top:
                    item_text = m_top.group(1)
                    sub_lines = []
                    i += 1
                    # Collect continuation lines + sub-bullets (indent >= 2)
                    while i < len(lines):
                        nxt = lines[i]
                        nxt_stripped = nxt.strip()
                        if not nxt_stripped:
                            break
                        nxt_indent = len(nxt) - len(nxt.lstrip(" "))
                        if nxt_indent >= 2:
                            sub_lines.append(nxt)
                            i += 1
                        else:
                            break
                    sub_html = ""
                    if sub_lines:
                        sub_html = _render_sublist(sub_lines)
                    items_html.append(
                        f'<li style="margin:6px 0;line-height:1.55;">{_inline(item_text)}{sub_html}</li>'
                    )
                else:
                    break
            out_blocks.append(
                f'<{tag} style="margin:8px 0 12px;padding-left:24px;color:#1a1a2e;">' +
                "".join(items_html) +
                f'</{tag}>'
            )
            continue

        # Plain paragraph: collect until blank line
        para = [line]
        i += 1
        while i < len(lines) and lines[i].strip():
            para.append(lines[i])
            i += 1
        joined = "<br>".join(_inline(l.strip()) for l in para)
        out_blocks.append(
            f'<p style="margin:10px 0;line-height:1.6;color:#1a1a2e;">{joined}</p>'
        )

    html = "\n".join(out_blocks)
    for key, html_block in placeholders.items():
        html = html.replace(key, html_block)
    return html


def _inline(text):
    """Apply inline transforms: escape, then bold/italic/code."""
    text = html_escape(text)
    text = _INLINE_CODE.sub(
        r'<code style="background:#eef0f6;padding:1px 6px;border-radius:3px;'
        r'font-family:\'JetBrains Mono\',\'SF Mono\',Menlo,Consolas,monospace;'
        r'font-size:0.92em;color:#365AB4;">\1</code>',
        text,
    )
    text = _BOLD.sub(r'<strong style="color:#0a0e1f;">\1</strong>', text)
    text = _ITALIC.sub(r'<em>\1</em>', text)
    return text


def _render_sublist(sub_lines):
    """Render an indented sub-block (treated as bullet list)."""
    items = []
    for raw in sub_lines:
        s = raw.strip()
        m = re.match(r"^[-*]\s+(.+)$", s)
        if m:
            items.append(
                f'<li style="margin:4px 0;line-height:1.5;">{_inline(m.group(1))}</li>'
            )
        else:
            items.append(
                f'<li style="margin:4px 0;line-height:1.5;list-style:none;">{_inline(s)}</li>'
            )
    return (
        '<ul style="margin:6px 0 4px;padding-left:20px;color:#3a3a52;">' +
        "".join(items) +
        '</ul>'
    )


# ==============================================================
# Branded HTML email shell
# ==============================================================
def html_email_shell(content_html, accent="#365AB4"):
    """Wrap content in RBR-branded email scaffold (inline CSS, table-based)."""
    return f"""<!DOCTYPE html>
<html lang="sv">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{BOT_NAME}</title>
</head>
<body style="margin:0;padding:0;background:#0a0e1f;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif;">
<table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="background:#0a0e1f;">
<tr><td align="center" style="padding:24px 12px;">
<table role="presentation" width="640" cellspacing="0" cellpadding="0" border="0" style="max-width:640px;width:100%;background:#ffffff;border-radius:8px;overflow:hidden;box-shadow:0 4px 24px rgba(0,0,0,0.25);">
  <tr><td style="background:{accent};padding:22px 28px;color:#ffffff;">
    <div style="font-family:'Big Shoulders Display',Impact,'Arial Black',sans-serif;font-weight:900;font-size:30px;letter-spacing:0.04em;text-transform:uppercase;line-height:1;">{BOT_NAME}</div>
    <div style="font-size:11px;letter-spacing:0.18em;text-transform:uppercase;opacity:0.85;margin-top:6px;font-family:'JetBrains Mono','SF Mono',Menlo,Consolas,monospace;">RBR · Web Developer</div>
  </td></tr>
  <tr><td style="height:4px;background:#DF4447;line-height:0;font-size:0;">&nbsp;</td></tr>
  <tr><td style="height:4px;background:#F6EA59;line-height:0;font-size:0;">&nbsp;</td></tr>
  <tr><td style="height:4px;background:#365AB4;line-height:0;font-size:0;">&nbsp;</td></tr>
  <tr><td style="padding:28px 28px 8px;color:#1a1a2e;font-size:15px;">
    {content_html}
  </td></tr>
  <tr><td style="background:#0a0e1f;color:#a0a8c0;padding:18px 28px;font-size:12px;line-height:1.5;">
    <div style="color:#ffffff;font-weight:600;">Vänliga hälsningar,</div>
    <div style="color:#ffffff;font-weight:700;font-family:'Big Shoulders Display',Impact,'Arial Black',sans-serif;letter-spacing:0.04em;font-size:15px;text-transform:uppercase;margin-top:2px;">{BOT_NAME}</div>
    <div style="margin-top:4px;">{BOT_TITLE}</div>
    <div style="margin-top:2px;"><a href="https://{SITE_DOMAIN}" style="color:#F6EA59;text-decoration:none;">{SITE_DOMAIN}</a></div>
  </td></tr>
</table>
</td></tr>
</table>
</body>
</html>"""


def build_recommendation_reply(subject, recommendation, level, task_id=None, revised=False):
    tid = task_id or "?"
    intro = "Reviderad plan" if revised else "Här är min rekommendation"
    text = (
        f"Hej!\n\n"
        f"{intro} för plan #{tid}:\n\n"
        f"{recommendation}\n\n"
        f"——\n\n"
        f"Säg till om jag ska köra — svara med 'jag godkänner' "
        f"(eller 'accept' / 'kör det').\n"
        f"Behöver du ändra något? Svara med 'uppdatera plan #{tid}' och beskriv "
        f"vad som ska bli annorlunda.\n"
        f"Vill du släppa det? Svara med 'avbryt'.\n\n"
        f"Vänliga hälsningar,\n"
        f"{BOT_NAME}\n"
        f"{BOT_TITLE} · https://{SITE_DOMAIN}\n"
    )
    badge = (
        f'<span style="display:inline-block;background:#0a0e1f;color:#F6EA59;'
        f'font-family:\'JetBrains Mono\',\'SF Mono\',Menlo,Consolas,monospace;'
        f'font-size:12px;letter-spacing:0.08em;padding:3px 10px;border-radius:3px;'
        f'margin-left:8px;vertical-align:middle;">#{tid}</span>'
    )
    revised_note = ""
    if revised:
        revised_note = (
            f'<div style="margin:0 0 14px;padding:8px 12px;background:#fff8d8;'
            f'border-left:3px solid #F6EA59;border-radius:0 4px 4px 0;font-size:13px;color:#5a4a00;">'
            f'Detta är en <strong>reviderad</strong> version av plan #{tid}.</div>'
        )
    body_html = (
        f'<p style="margin:0 0 14px;line-height:1.6;color:#1a1a2e;">Hej!</p>'
        f'<p style="margin:0 0 16px;line-height:1.6;color:#1a1a2e;">'
        f'{intro} för plan{badge}</p>'
        f'{revised_note}'
        f'<div style="border-left:3px solid #365AB4;padding:4px 18px;margin:0 0 22px;background:#f7f8fb;border-radius:0 4px 4px 0;">'
        f'{markdown_to_html(recommendation)}'
        f'</div>'
        f'<table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="margin:18px 0 8px;">'
        f'  <tr><td style="border-top:2px solid #DF4447;line-height:0;font-size:0;height:2px;">&nbsp;</td></tr>'
        f'</table>'
        f'<p style="margin:14px 0 8px;line-height:1.6;color:#1a1a2e;">Säg till om jag ska köra — svara med '
        f'<strong style="color:#365AB4;">jag godkänner</strong> '
        f'(eller <em>accept</em> / <em>kör det</em>).</p>'
        f'<p style="margin:0 0 8px;line-height:1.6;color:#1a1a2e;">Behöver du ändra något? Svara med '
        f'<strong style="color:#F6EA59;background:#0a0e1f;padding:1px 6px;border-radius:3px;'
        f'font-family:\'JetBrains Mono\',\'SF Mono\',Menlo,Consolas,monospace;font-size:0.92em;">'
        f'uppdatera plan #{tid}</strong> och beskriv vad som ska bli annorlunda.</p>'
        f'<p style="margin:0 0 12px;line-height:1.6;color:#1a1a2e;">Vill du släppa det? Svara med '
        f'<strong style="color:#DF4447;">avbryt</strong>.</p>'
    )
    return text, html_email_shell(body_html, accent="#365AB4")


def build_success_reply(subject, engine, level):
    text = (
        f"Hej!\n\n"
        f"Klart — ändringen är gjord på {SITE_DOMAIN}.\n\n"
        f"Ta gärna en titt så allt ser bra ut. Hör av dig om "
        f"något behöver justeras.\n\n"
        f"Vänliga hälsningar,\n"
        f"{BOT_NAME}\n"
        f"{BOT_TITLE} · https://{SITE_DOMAIN}\n"
    )
    body_html = (
        f'<p style="margin:0 0 14px;line-height:1.6;color:#1a1a2e;">Hej!</p>'
        f'<p style="margin:0 0 16px;line-height:1.6;color:#1a1a2e;">'
        f'<strong style="color:#365AB4;">Klart</strong> — ändringen är gjord på '
        f'<a href="https://{SITE_DOMAIN}" style="color:#365AB4;text-decoration:none;font-weight:600;">{SITE_DOMAIN}</a>.</p>'
        f'<p style="margin:0 0 12px;line-height:1.6;color:#1a1a2e;">'
        f'Ta gärna en titt så allt ser bra ut. Hör av dig om något behöver justeras.</p>'
    )
    return text, html_email_shell(body_html, accent="#365AB4")


def build_error_reply(subject, error_msg):
    text = (
        f"Hej!\n\n"
        f"Tyvärr — jag fick inte uppgiften att gå igenom.\n\n"
        f"Felet var:\n"
        f"{error_msg[:600]}\n\n"
        f"Skicka mejlet igen om du vill att jag försöker en gång till, "
        f"eller låt det vara så kollar någon manuellt.\n\n"
        f"Vänliga hälsningar,\n"
        f"{BOT_NAME}\n"
        f"{BOT_TITLE} · https://{SITE_DOMAIN}\n"
    )
    body_html = (
        f'<p style="margin:0 0 14px;line-height:1.6;color:#1a1a2e;">Hej!</p>'
        f'<p style="margin:0 0 16px;line-height:1.6;color:#1a1a2e;">'
        f'<strong style="color:#DF4447;">Tyvärr</strong> — jag fick inte uppgiften att gå igenom.</p>'
        f'<div style="margin:0 0 18px;padding:12px 14px;background:#fef3f3;border-left:3px solid #DF4447;border-radius:0 4px 4px 0;'
        f'font-family:\'JetBrains Mono\',\'SF Mono\',Menlo,Consolas,monospace;font-size:13px;line-height:1.5;color:#5a1a1a;'
        f'white-space:pre-wrap;word-break:break-word;">{html_escape(error_msg[:1000])}</div>'
        f'<p style="margin:0 0 12px;line-height:1.6;color:#1a1a2e;">'
        f'Skicka mejlet igen om du vill att jag försöker en gång till, '
        f'eller låt det vara så kollar någon manuellt.</p>'
    )
    return text, html_email_shell(body_html, accent="#DF4447")


def build_cancel_reply(subject):
    text = (
        f"Hej!\n\n"
        f"Avbrutet — ingen ändring utförd.\n\n"
        f"Hör av dig när det är dags igen.\n\n"
        f"Vänliga hälsningar,\n"
        f"{BOT_NAME}\n"
        f"{BOT_TITLE} · https://{SITE_DOMAIN}\n"
    )
    body_html = (
        f'<p style="margin:0 0 14px;line-height:1.6;color:#1a1a2e;">Hej!</p>'
        f'<p style="margin:0 0 16px;line-height:1.6;color:#1a1a2e;">'
        f'<strong style="color:#a0a8c0;">Avbrutet</strong> — ingen ändring utförd.</p>'
        f'<p style="margin:0 0 12px;line-height:1.6;color:#1a1a2e;">Hör av dig när det är dags igen.</p>'
    )
    return text, html_email_shell(body_html, accent="#a0a8c0")


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
# OpenRouter API
# ==============================================================
def call_openrouter_simple(prompt, api_key, model, max_tokens=256, zdr=False):
    """Single-turn, no tools. `zdr=True` requests Zero Data Retention provider."""
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
        "HTTP-Referer": f"https://{SITE_DOMAIN}",
        "X-Title": f"SVERA {BOT_NAME}",
    })

    try:
        resp = urllib.request.urlopen(req, timeout=60)
        data = json.loads(resp.read().decode())
        content = data["choices"][0]["message"].get("content")
        return content.strip() if content else None
    except Exception as e:
        log(f"  API simple call failed: {e}")
        return None


def call_openrouter(messages, api_key, model, tools=None, zdr=False):
    """Multi-turn with tools. Pass `tools=` to restrict, `zdr=True` for ZDR provider."""
    url = "https://openrouter.ai/api/v1/chat/completions"
    body = {
        "model": model,
        "messages": messages,
        "tools": tools if tools is not None else TOOLS,
        "max_tokens": 4096,
    }
    if zdr:
        body["provider"] = {"zdr": True}
    payload = json.dumps(body).encode("utf-8")

    req = urllib.request.Request(url, data=payload, headers={
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": f"https://{SITE_DOMAIN}",
        "X-Title": f"SVERA {BOT_NAME}",
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
# Task classifier — LOW / MEDIUM / HIGH
# ==============================================================
def classify_task(subject, body, api_key, model):
    """Returns 'low', 'medium', or 'high'."""
    prompt = (
        f"Du ar en task-klassificerare for webbplatsen {SITE_DOMAIN} (statisk HTML/CSS/JS).\n"
        "Klassificera uppgiften som LOW, MEDIUM eller HIGH.\n\n"
        "LOW = enkel textandring, byta ett ord, "
        "andra en lank, trigga deploy, ta bort nagon rad.\n\n"
        "MEDIUM = lagga till/skapa nyheter eller inlagg, fixa en bugg i en fil, "
        "smarre CSS-tweak, andra en specifik "
        "komponent, lagga till en enkel funktion i en befintlig fil, "
        "andra ett team i bot/teams.json, lagga till bilder i bot/gallery.json.\n\n"
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

    # Escalate content-creation tasks — DeepSeek struggles with the news-card
    # HTML template, so route these through Qwen ZDR (MEDIUM) at minimum.
    if level == "low":
        combined = f"{subject}\n{body[:300]}"
        if _CONTENT_CREATION_KEYWORDS.search(combined):
            log(f"  Escalating LOW -> MEDIUM (content creation detected)")
            level = "medium"
    return level


# ==============================================================
# Qwen ZDR name extraction — used before HIGH tasks reach Claude
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
# Recommendation drafter — research first, then plan, then send
# ==============================================================
RESEARCH_MAX_TURNS = 12  # cap on read_file/list_files calls during research


def research_then_draft(subject, body, saved_pdfs, level, api_key, model,
                        edit_instructions=None, prior_recommendation=None):
    """Two-stage: research the project (read-only tools), then write a recommendation.

    If edit_instructions is given, this is a *revision* of an existing plan —
    DeepSeek gets the prior recommendation and the new guidance to revise from.
    Returns the recommendation text (markdown).
    """
    pdf_context = ""
    if saved_pdfs:
        pdf_lines = [f"  - {fn} -> {wp}" for fn, wp in saved_pdfs]
        pdf_context = "\n\nBifogade PDF:er (sparade i projektet):\n" + "\n".join(pdf_lines)

    project_context = (
        f"PROJEKT: {SITE_DOMAIN} — statisk HTML/CSS/JS-sajt\n"
        f"Projektmapp: {PROJECT_DIR}\n"
        "  Sidor:    index.html, kalender.html, resultat.html, klasser.html, "
        "klubbar.html, team.html, arkivet.html, om.html, sponsorer.html, "
        "nyheter.html, social.html, champions.html, kontakt.html, api.html, policy.html\n"
        "  CSS:      assets/css/style.css\n"
        "  JS:       assets/js/main.js\n"
        "  Data:     bot/data/*.json (svemo_calendar, uim_calendar, webtracking_*, news_feed, social_*)\n"
        "  Builders: bot/builders/build_kalender.py, build_resultat.py, build_news.py, "
        "build_champions.py, build_rss.py, build_social.py\n"
        "  Scrapers: bot/scrapers/ (svemo, uim, webtracking, news_aggregator, social_*)\n"
        "  Docs:     CLAUDE.md (full projektbeskrivning, news-card format, kategori-färger)\n"
    )

    revision_block = ""
    if edit_instructions:
        revision_block = (
            "\n=== REVIDERING ===\n"
            "Detta är en uppdatering av en tidigare plan. "
            "Läs den gamla rekommendationen och de nya instruktionerna nedan, "
            "och skriv en reviderad rekommendation som tar hänsyn till båda.\n"
            f"\n--- TIDIGARE REKOMMENDATION ---\n{prior_recommendation or '(ingen)'}\n"
            f"\n--- NYA INSTRUKTIONER FRÅN ADMIN ---\n{edit_instructions}\n"
        )

    system = (
        f"Du är {BOT_NAME}, SVERA:s webbutvecklare.\n"
        "Du ska INTE utföra uppgiften — bara forska i projektet och rekommendera.\n\n"
        "ARBETSGÅNG (följ exakt):\n"
        "1. RESEARCH FÖRST. Använd list_files och read_file för att förstå relevanta filer. "
        "Läs CLAUDE.md, relevanta datafiler i bot/data/, och de HTML/CSS-filer "
        "som troligen berörs. För nyhetsuppgifter: läs index.html (news-list), nyheter.html, "
        "och CLAUDE.md för news-card formatet och kategori-färger. "
        "Slösa inte tokens — bara filer som faktiskt är relevanta.\n"
        "2. PLAN. När du har tillräckligt underlag, skriv en strukturerad rekommendation på svenska "
        "i ditt avslutande meddelande (utan tool-anrop).\n\n"
        "REKOMMENDATIONENS STRUKTUR (markdown):\n"
        "1. **Sammanfattning** — 1-2 meningar om vad uppgiften innebär.\n"
        "2. **Filer att redigera** — kort lista med varför varje fil berörs.\n"
        "3. **Konkreta ändringar** — specifika strängar/värden, gärna med kodexempel.\n"
        "4. **Risker & antaganden** — vad som kan gå fel; vad du antar utan att veta säkert.\n\n"
        "Skriv på svenska. Ta dig tid och var noggrann — kvalitet före hastighet. "
        "Inga tool-anrop i sista turn.\n\n"
        f"{project_context}\n"
        f"Klassificerad nivå för uppgiften: {level.upper()}\n"
        f"Dagens datum: {datetime.now().strftime('%Y-%m-%d')}"
    )

    user_msg = (
        f"EMAIL-UPPGIFT:\n"
        f"Ämne: {subject}\n"
        f"Innehåll:\n{body}"
        f"{pdf_context}"
        f"{revision_block}\n\n"
        "Forska först (read_file/list_files efter behov), skriv sedan rekommendationen."
    )

    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user_msg},
    ]

    final_text = ""
    for turn in range(RESEARCH_MAX_TURNS):
        response = call_openrouter(messages, api_key, model, tools=TOOLS_READ_ONLY)
        if response is None:
            log(f"  Research API failed at turn {turn + 1}")
            break

        messages.append(response)
        tool_calls = response.get("tool_calls")

        if not tool_calls:
            final_text = (response.get("content") or "").strip()
            log(f"  Research+draft done after {turn + 1} turn(s), {len(final_text)} chars")
            break

        for tc in tool_calls:
            fn_name = tc["function"]["name"]
            try:
                fn_args = json.loads(tc["function"]["arguments"])
            except json.JSONDecodeError:
                fn_args = {}
            log(f"  [research {turn + 1}] {fn_name}({', '.join(f'{k}={repr(v)[:60]}' for k, v in fn_args.items())})")
            result = exec_tool(fn_name, fn_args)
            messages.append({
                "role": "tool",
                "tool_call_id": tc["id"],
                "content": result[:6000],  # cap tool output to keep prompt sane
            })
    else:
        log(f"  Research hit max turns ({RESEARCH_MAX_TURNS})")

    if final_text:
        return final_text
    return (
        f"(Kunde inte slutföra forskningen — uppgift enligt email:\n{body[:400]})"
    )


# Backwards-compatible alias (no callers should use this; kept until removal)
def draft_recommendation(subject, body, saved_pdfs, level, api_key, model):
    return research_then_draft(subject, body, saved_pdfs, level, api_key, model)


# ==============================================================
# Prompt crafter — DeepSeek writes a structured prompt for Claude
# ==============================================================
def craft_claude_prompt(subject, body, saved_pdfs, api_key, model):
    pdf_context = ""
    if saved_pdfs:
        pdf_lines = [f"  - {fn} -> {wp}" for fn, wp in saved_pdfs]
        pdf_context = "\nBifogade PDF:er (sparade i projektet):\n" + "\n".join(pdf_lines)

    prompt = (
        "Du ar en prompt-ingenjor. Las foljande email-uppgift och skriv en "
        "TYDLIG, STRUKTURERAD prompt pa engelska for en AI-kodagent (Claude Code) "
        f"som ska utfora uppgiften pa webbplatsen {SITE_DOMAIN}.\n\n"
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
        f"- Statisk HTML/CSS/JS-sajt pa {SITE_DOMAIN}\n"
        f"- Projektmapp: {PROJECT_DIR}\n"
        "- Sidor: index.html, resultat.html, kalender.html, klasser.html, "
        "klubbar.html, team.html, arkivet.html, om.html, sponsorer.html, "
        "nyheter.html, social.html, champions.html, kontakt.html, api.html, policy.html\n"
        "- CSS: assets/css/style.css\n"
        "- JS: assets/js/main.js\n"
        "- Scrapers: bot/scrapers/ (webtracking, svemo, uim, news_aggregator, social_*)\n"
        "- Builders: bot/builders/ (kalender, resultat, news, champions, rss, social)\n"
        "- Deploy: bash bot/deploy.sh\n"
        "- Navigation: Om SVERA (Om SVERA + Sponsorer), Nyheter (Nyheter + Social), "
        "Klubbar (Klubbar + Team)\n"
        "- VIKTIGT: Las CLAUDE.md for fullstandig dokumentation, news-card format, "
        "kategori-färger, builders och scrapers\n\n"
        "Skriv prompten nu (pa engelska):"
    )

    result = call_openrouter_simple(prompt, api_key, model, max_tokens=1024)
    if result:
        log(f"  Crafted prompt: {result[:200]}...")
        return result
    log(f"  Prompt crafting failed, using raw email")
    return f"Task from email:\nSubject: {subject}\nBody: {body}"


# ==============================================================
# Tool definitions for agent
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

# Read-only subset for the research-then-draft phase (no writes, no shell).
TOOLS_READ_ONLY = [t for t in TOOLS if t["function"]["name"] in ("read_file", "list_files")]


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
    if not os.path.exists(CLAUDE_CLI):
        log(f"  Claude CLI not found at {CLAUDE_CLI}")
        return False, "Claude Code CLI not found"

    history_text = format_history_for_prompt()

    parent_claude_md = os.path.join(DOCUMENTS_DIR, "CLAUDE.md")
    claude_md_ref = ""
    if os.path.exists(parent_claude_md):
        claude_md_ref = (
            f"IMPORTANT: Read {parent_claude_md} for your full agent configuration.\n"
            f"It references UI/UX skills, scraping tools, and other resources you can use.\n\n"
        )

    full_prompt = (
        f"You are {BOT_NAME}, the RBR web developer.\n"
        f"You maintain the website {SITE_DOMAIN} (static HTML/CSS/JS).\n"
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
# DeepSeek/Qwen ZDR agent loop — for LOW / MEDIUM tasks
# ==============================================================
def run_agent(prompt, api_key, model, zdr=False):
    """Tool-use agent loop. `zdr=True` routes through Qwen ZDR for privacy."""
    label = "Qwen ZDR" if zdr else "DeepSeek"
    log(f"  Starting {label} agent...")

    claude_md = ""
    claude_md_path = os.path.join(PROJECT_DIR, "CLAUDE.md")
    if os.path.exists(claude_md_path):
        with open(claude_md_path) as f:
            claude_md = f.read()

    messages = [
        {
            "role": "system",
            "content": (
                f"Du ar {BOT_NAME}, SVERA:s webbutvecklare.\n"
                f"Du underhaller webbplatsen {SITE_DOMAIN} (statisk HTML/CSS/JS).\n"
                "Du har verktyg for att lasa, redigera, skriva filer och kora bash.\n"
                f"Projektet: {PROJECT_DIR}\n\n"
                "PROJEKTSTRUKTUR:\n" + claude_md + "\n\n"
                "REGLER:\n"
                "- Gor BARA det uppgiften ber om\n"
                "- Las ALLTID relevanta filer FORST\n"
                "- Anvand edit_file for andringar, write_file bara for helt nya filer\n"
                "- Nyheter laggs i index.html div.news-list (NYAST OVERST)\n"
                "- Skapa ALDRIG separata HTML-filer for nyheter\n"
                "- Nyhets-kort har INGEN bild/news-image — kompakt format:\n"
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
                "- FORMATERING: Anvand ALDRIG <ul>/<li> i nyhetskort. "
                "Skriv info som inline text med middot-separator: "
                "<strong>Var:</strong> X &middot; <strong>Nar:</strong> Y\n"
                "- LANKAR: Anvand ALDRIG href='#'. Om ingen riktig URL finns, "
                "skippa <a class='read-more'> helt.\n"
                "- PDF-bilagor ar sparade i assets/uploads/\n"
                "- Nar klar: run_bash('bash bot/deploy.sh')\n"
                "- Svara kort pa svenska (max 3 meningar)\n"
                f"  Dagens datum: {datetime.now().strftime('%Y-%m-%d')}\n\n"
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
# Build a prompt from a stored pending plan
# ==============================================================
def build_prompt_from_plan(plan):
    parts = [
        "UPPGIFT VIA EMAIL (godkand)",
        f"Amne: {plan['subject']}",
        "",
        "Innehall:",
        plan["body"],
    ]
    saved_pdfs = plan.get("saved_pdfs", [])
    if saved_pdfs:
        parts.append("")
        parts.append("PDF:er sparade i projektet:")
        for fn, web_path in saved_pdfs:
            parts.append(f'  - {fn} -> <a href="{web_path}" target="_blank">{fn}</a>')
    parts.extend(["", "Utfor uppgiften. Deploya nar klar: run_bash('bash bot/deploy.sh')"])
    return "\n".join(parts)


def execute_plan(plan, api_key, model, model_zdr=None):
    """Run an approved pending plan with svera's privacy-aware multi-engine routing.

    Returns (engine, success, summary).

    Routing:
      LOW + no names  → DeepSeek (fast/cheap)
      LOW + names     → Qwen ZDR (privacy)
      MEDIUM          → Qwen ZDR (privacy + better HTML output)
      HIGH            → Claude Code CLI; if names, mask via Qwen first
    """
    level = plan.get("level", "low")
    subject = plan.get("subject", "")
    body = plan.get("body", "")
    saved_pdfs = plan.get("saved_pdfs", [])
    model_zdr = model_zdr or model

    email_text = f"{subject}\n{body}"
    names_found = detect_names_regex(email_text)
    if names_found:
        log(f"  Names detected ({len(names_found)}): {', '.join(names_found[:5])}")

    if level == "high":
        if names_found:
            log(f"  HIGH + names — Qwen ZDR scans for names then crafts prompt...")
            accurate_names = extract_names_with_qwen(email_text, api_key, model_zdr)
            if accurate_names:
                crafted = craft_claude_prompt(subject, body, saved_pdfs, api_key, model_zdr)
                crafted, name_map = mask_names(crafted, accurate_names)
                log(f"  Masked {len(name_map)} name(s) before Claude")
            else:
                crafted = craft_claude_prompt(subject, body, saved_pdfs, api_key, model)
        else:
            log(f"  HIGH task — DeepSeek crafts prompt for Claude...")
            crafted = craft_claude_prompt(subject, body, saved_pdfs, api_key, model)
        log(f"  Routing to Claude Code...")
        success, summary = run_claude(crafted)
        return "claude", success, summary

    if level == "medium" or names_found:
        reason = "MEDIUM" if level == "medium" else "names detected"
        log(f"  Routing to Qwen ZDR ({reason})...")
        prompt = build_prompt_from_plan(plan)
        success, summary = run_agent(prompt, api_key, model_zdr, zdr=True)
        return "qwen-zdr", success, summary

    log(f"  Routing to DeepSeek (LOW, no names)...")
    prompt = build_prompt_from_plan(plan)
    success, summary = run_agent(prompt, api_key, model)
    return "deepseek", success, summary


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

    admins = get_admin_senders(email_cfg)
    if not admins:
        log("No admin_senders configured")
        return 0

    api_key = api_cfg.get("openrouter", "")
    model = api_cfg.get("openrouter_model", DEFAULT_MODEL)
    model_zdr = api_cfg.get("openrouter_model_fallback") or api_cfg.get("openrouter_model_zdr") or "qwen/qwen-2.5-72b-instruct"
    if not api_key:
        log("No OpenRouter API key")
        return 0

    processed = load_processed()
    plans = cleanup_expired_pending(load_pending_plans())
    save_pending_plans(plans)
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
            message_id_raw = msg.get("Message-ID", msg_id.decode())
            message_id = normalize_msgid(message_id_raw) or msg_id.decode()

            log("")
            log(f"Email: {subject}")
            log(f"  From: {sender}")

            if sender not in admins:
                log(f"  SKIP — not an approved sender")
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

            reply_text = strip_quoted(body)
            log(f"  Body: {len(body)} chars (active reply: {len(reply_text)} chars)")

            # Step A: lookup pending plan — by explicit task ID first, then reply chain
            explicit_task_id = extract_task_id(subject) or extract_task_id(reply_text)
            refs = collect_reply_refs(msg)
            pid, plan = find_pending_for_reply(plans, refs, sender, task_id=explicit_task_id)

            if plan:
                tid = plan.get("task_id", "?")
                log(f"  Reply matches pending plan #{tid}: {plan.get('subject', '')!r}")

                if is_cancel(subject, reply_text):
                    log(f"  CANCEL — dropping pending plan #{tid}")
                    plans.pop(pid, None)
                    save_pending_plans(plans)
                    save_task(plan["subject"], plan["body"], "Avbruten av admin", True,
                              engine="cancel", level=plan.get("level", "low"))
                    send_reply(email_cfg, sender, plan["subject"],
                               build_cancel_reply(plan["subject"]),
                               tag_override=f"AVBRUTEN #{tid}")
                    processed.append(message_id)
                    save_processed(processed)
                    continue

                # Edit-plan: revise the recommendation with new instructions
                if is_edit_plan(subject, reply_text):
                    log(f"  EDIT — revising plan #{tid}")
                    edit_text = strip_quoted(reply_text)
                    new_recommendation = research_then_draft(
                        plan["subject"], plan["body"], plan.get("saved_pdfs", []),
                        plan.get("level", "low"), api_key, model,
                        edit_instructions=edit_text,
                        prior_recommendation=plan.get("recommendation"),
                    )
                    plan["recommendation"] = new_recommendation
                    plan["created_at"] = datetime.now().isoformat(timespec="seconds")
                    plan["revisions"] = (plan.get("revisions") or 0) + 1
                    plans[pid] = plan
                    save_pending_plans(plans)
                    send_reply(
                        email_cfg, sender, plan["subject"],
                        build_recommendation_reply(plan["subject"], new_recommendation,
                                                   plan.get("level", "low"),
                                                   task_id=tid, revised=True),
                        tag_override=f"REVIDERAD #{tid}",
                    )
                    log(f"  Revised plan #{tid} sent — awaiting approval")
                    processed.append(message_id)
                    save_processed(processed)
                    continue

                if is_approval(subject, reply_text):
                    log(f"  APPROVED #{tid} — executing plan")
                    plans.pop(pid, None)
                    save_pending_plans(plans)
                    engine, success, summary = execute_plan(plan, api_key, model, model_zdr=model_zdr)
                    save_task(plan["subject"], plan["body"], summary, success,
                              engine=engine, level=plan.get("level", "low"))
                    if success:
                        tasks_run += 1
                        send_reply(email_cfg, sender, plan["subject"],
                                   build_success_reply(plan["subject"], engine, plan.get("level", "low")),
                                   tag_override=f"OK #{tid}")
                    else:
                        send_reply(email_cfg, sender, plan["subject"],
                                   build_error_reply(plan["subject"], summary), is_error=True,
                                   tag_override=f"FEL #{tid}")
                    processed.append(message_id)
                    save_processed(processed)
                    continue

                log(f"  Reply on plan #{tid} but no approval/cancel/edit keyword — ignoring")
                processed.append(message_id)
                save_processed(processed)
                continue

            # Step B: fresh request — must contain a trigger keyword
            if not has_trigger(subject, reply_text):
                log(f"  SKIP — no trigger keyword (update/uppdatera/fixa/andra/byt ut/skapa/...)")
                processed.append(message_id)
                save_processed(processed)
                continue

            # Step C: classify + research + draft + save pending plan with task ID
            with tempfile.TemporaryDirectory(prefix="svera_email_") as tmpdir:
                attachments = get_attachments(msg, tmpdir)
                saved_pdfs = save_pdfs_to_project(attachments)

                level = classify_task(subject, reply_text, api_key, model)
                log(f"  Level: {level.upper()}")

                task_id = next_task_id(plans)
                log(f"  Plan #{task_id} — researching + drafting...")
                recommendation = research_then_draft(
                    subject, reply_text, saved_pdfs, level, api_key, model
                )

                plans[message_id] = {
                    "id": message_id,
                    "task_id": task_id,
                    "sender": sender,
                    "subject": subject,
                    "body": reply_text,
                    "level": level,
                    "recommendation": recommendation,
                    "saved_pdfs": saved_pdfs,
                    "created_at": datetime.now().isoformat(timespec="seconds"),
                    "revisions": 0,
                }
                save_pending_plans(plans)

                send_reply(
                    email_cfg, sender, subject,
                    build_recommendation_reply(subject, recommendation, level, task_id=task_id),
                    tag_override=f"REKOMMENDATION #{task_id}",
                )

                log(f"  Plan #{task_id} sent — awaiting approval")
                processed.append(message_id)
                save_processed(processed)

    finally:
        try:
            mail.close()
        except Exception:
            pass
        mail.logout()

    log(f"Inbox check complete: {tasks_run} task(s) executed")
    return tasks_run


if __name__ == "__main__":
    log("=" * 50)
    log(f"{BOT_NAME} — {BOT_TITLE}")
    log("=" * 50)
    check_inbox()
