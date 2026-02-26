#!/usr/bin/env python3
"""Build/update kalender.html from scraped SVEMO and UIM calendar data."""
import json
import os
import re
from datetime import datetime

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")

MONTHS_SV = {
    1: "januari", 2: "februari", 3: "mars", 4: "april",
    5: "maj", 6: "juni", 7: "juli", 8: "augusti",
    9: "september", 10: "oktober", 11: "november", 12: "december",
}


def load_data():
    svemo_path = os.path.join(DATA_DIR, "svemo_calendar.json")
    uim_path = os.path.join(DATA_DIR, "uim_calendar.json")

    svemo = []
    uim = []

    if os.path.exists(svemo_path):
        with open(svemo_path) as f:
            svemo = json.load(f)
    else:
        print("[build_kalender] No SVEMO data found")

    if os.path.exists(uim_path):
        with open(uim_path) as f:
            uim = json.load(f)
    else:
        print("[build_kalender] No UIM data found")

    return svemo, uim


def build_svemo_table(events):
    """Build HTML table for SVEMO events."""
    if not events:
        return "<p>Inga kommande svenska tävlingar hittade.</p>"

    today = datetime.now().strftime("%Y-%m-%d")
    future = [e for e in events if e.get("date", "") >= today]
    future.sort(key=lambda e: e["date"])

    rows = ""
    for e in future:
        badge_class = {
            "Offshore": "badge-offshore",
            "Rundbana": "badge-rundbana",
            "Aquabike": "badge-aquabike",
        }.get(e.get("branch", ""), "badge-open")

        rows += f"""<tr data-type="{e.get('branch', '').lower()}">
  <td>{e.get('date', '')}</td>
  <td>{e.get('name', '')}</td>
  <td><span class="badge {badge_class}">{e.get('branch', '')}</span></td>
  <td>{e.get('location', '')}</td>
  <td class="hide-mobile">{e.get('organizer', '')}</td>
  <td class="hide-mobile">{e.get('status', '')}</td>
</tr>"""

    return f"""<table class="cal-table">
<thead><tr>
  <th>Datum</th><th>Tävling</th><th>Gren</th><th>Plats</th>
  <th class="hide-mobile">Arrangör</th><th class="hide-mobile">Status</th>
</tr></thead>
<tbody>{rows}</tbody></table>"""


def build_uim_table(events):
    """Build HTML table rows for UIM events.

    UIM data fields: date, name, venue, country, discipline
    """
    if not events:
        return "<tr><td colspan='5'>Inga internationella tävlingar hittade.</td></tr>"

    rows = ""
    for e in events:
        badge_class = {
            "Offshore": "badge-offshore",
            "Aquabike": "badge-aquabike",
            "Circuit": "badge-circuit",
        }.get(e.get("discipline", ""), "badge-uim")

        rows += (
            f'<tr data-branch="{e.get("discipline", "").lower()}" class="uim">'
            f'<td>{e.get("date", "")}</td>'
            f'<td>{e.get("venue", "")}</td>'
            f'<td><span class="badge {badge_class}">{e.get("name", "")}</span></td>'
            f'<td class="hide-mobile">{e.get("country", "")}</td>'
            f'<td>{e.get("discipline", "")}</td>'
            f'</tr>'
        )
    return rows


def build():
    svemo, uim = load_data()
    kalender_path = os.path.join(PROJECT_DIR, "kalender.html")

    if not os.path.exists(kalender_path):
        print("[build_kalender] kalender.html not found")
        return False

    with open(kalender_path) as f:
        html = f.read()

    updated = False

    # Update SVEMO table body — only if we have scraped SVEMO data
    svemo_pattern = r'(<tbody id="svemo-events">).*?(</tbody>)'
    if re.search(svemo_pattern, html, re.DOTALL) and svemo:
        today = datetime.now().strftime("%Y-%m-%d")
        future = [e for e in svemo if e.get("date", "") >= today]
        future.sort(key=lambda e: e["date"])

        svemo_rows = ""
        for e in future:
            badge_class = {
                "Offshore": "badge-offshore",
                "Rundbana": "badge-rundbana",
                "Aquabike": "badge-aquabike",
            }.get(e.get("branch", ""), "badge-open")

            svemo_rows += (
                f'<tr data-branch="{e.get("branch", "").lower()}">'
                f'<td>{e.get("date", "")}</td>'
                f'<td>{e.get("name", "")}</td>'
                f'<td><span class="badge {badge_class}">{e.get("branch", "")}</span></td>'
                f'<td class="hide-mobile">{e.get("organizer", "")}</td>'
                f'<td class="hide-mobile">{e.get("classes", "")}</td>'
                f'<td>{e.get("status", "")}</td>'
                f'</tr>\n        '
            )

        if not svemo_rows:
            svemo_rows = '<tr><td colspan="6">Inga kommande svenska tävlingar hittade.</td></tr>'

        html = re.sub(svemo_pattern, rf'\1\n        {svemo_rows}\2', html, flags=re.DOTALL)
        updated = True
        print(f"[build_kalender] Updated SVEMO section: {len(future)} future events")

    # Update UIM table body — only if data has proper date fields (YYYY-MM-DD format)
    uim_pattern = r'(<tbody id="uim-events">).*?(</tbody>)'
    uim_has_dates = uim and any(len(e.get("date", "")) > 4 for e in uim)
    if re.search(uim_pattern, html, re.DOTALL) and uim_has_dates:
        uim_rows = build_uim_table(uim)
        html = re.sub(uim_pattern, rf'\1\n        {uim_rows}\2', html, flags=re.DOTALL)
        updated = True
        print(f"[build_kalender] Updated UIM section: {len(uim)} events")
    elif uim:
        print(f"[build_kalender] UIM: {len(uim)} events (skipped — raw data lacks full dates)")

    # Update the "Uppdaterad" date in source notes
    today_str = datetime.now().strftime("%Y-%m-%d")
    html = re.sub(r'Uppdaterad \d{4}-\d{2}-\d{2}', f'Uppdaterad {today_str}', html)

    if updated:
        with open(kalender_path, "w") as f:
            f.write(html)
        print(f"[build_kalender] kalender.html updated successfully")
    else:
        print(f"[build_kalender] SVEMO: {len(svemo)} events, UIM: {len(uim)} events (no markers found)")

    return True


if __name__ == "__main__":
    build()
