#!/usr/bin/env python3
"""Build/update kalender.html from scraped SVEMO and UIM calendar data."""
import json
import os
import re
from collections import OrderedDict
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


BADGE_CLASSES = {
    "Offshore": "badge-offshore",
    "Rundbana": "badge-rundbana",
    "Aquabike": "badge-aquabike",
}


def merge_events(events):
    """Merge events with same date + location into single entries with multiple branches."""
    grouped = OrderedDict()
    for e in events:
        key = (e.get("date", ""), e.get("location", ""))
        if key not in grouped:
            grouped[key] = {
                "date": e.get("date", ""),
                "name": e.get("name", ""),
                "location": e.get("location", ""),
                "organizer": e.get("organizer", ""),
                "branches": [],
                "classes_list": [],
                "status": e.get("status", ""),
            }
        merged = grouped[key]
        branch = e.get("branch", "")
        if branch and branch not in merged["branches"]:
            merged["branches"].append(branch)
        classes = e.get("classes", [])
        if isinstance(classes, list):
            for c in classes:
                if c and c not in merged["classes_list"]:
                    merged["classes_list"].append(c)
        elif classes and classes not in merged["classes_list"]:
            merged["classes_list"].append(classes)
    return list(grouped.values())


def build_badges(branches):
    """Build HTML badge spans for one or more branches."""
    parts = []
    for b in branches:
        cls = BADGE_CLASSES.get(b, "badge-open")
        parts.append(f'<span class="badge {cls}">{b}</span>')
    return " ".join(parts)


def build_uim_table(events):
    """Build HTML table rows for UIM events.

    UIM data fields: date, name, venue, country, discipline
    Table columns: Datum | Tävling | Gren | Plats | Klasser (hide-mobile)
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

        # Build plats from venue + country
        venue = e.get("venue", "")
        country = e.get("country", "")
        if venue and country:
            plats = f"{venue}, {country}"
        elif country:
            plats = country
        else:
            plats = venue or "TBA"

        # Format date to prevent phone detection on iOS
        date_str = e.get("date", "")
        date_cell = f'<span style="white-space:nowrap;" x-apple-data-detectors="false">{date_str}</span>'

        rows += (
            f'<tr data-branches="{e.get("discipline", "").lower()}" class="uim">'
            f'<td>{date_cell}</td>'
            f'<td>{e.get("name", "")}</td>'
            f'<td><span class="badge {badge_class}">{e.get("discipline", "")}</span></td>'
            f'<td>{plats}</td>'
            f'<td class="hide-mobile">{e.get("classes", "")}</td>'
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

        # Merge events with same date + location into single rows
        merged = merge_events(future)

        svemo_rows = ""
        for e in merged:
            branches = e.get("branches", [])
            branches_attr = " ".join(b.lower() for b in branches)
            badges_html = build_badges(branches)
            classes_combined = ", ".join(e.get("classes_list", []))

            # Format date to prevent phone detection on iOS
            date_str = e.get("date", "")
            date_cell = f'<span style="white-space:nowrap;" x-apple-data-detectors="false">{date_str}</span>'

            svemo_rows += (
                f'<tr data-branches="{branches_attr}">'
                f'<td>{date_cell}</td>'
                f'<td>{e.get("name", "")}</td>'
                f'<td>{badges_html}</td>'
                f'<td>{e.get("location", "")}</td>'
                f'<td class="hide-mobile">{e.get("organizer", "")}</td>'
                f'<td class="hide-mobile">{classes_combined}</td>'
                f'<td class="hide-mobile">{e.get("status", "")}</td>'
                f'</tr>\n        '
            )

        if not svemo_rows:
            svemo_rows = '<tr><td colspan="7">Inga kommande svenska tävlingar hittade.</td></tr>'

        html = re.sub(svemo_pattern, rf'\1\n        {svemo_rows}\2', html, flags=re.DOTALL)
        updated = True
        print(f"[build_kalender] Updated SVEMO section: {len(merged)} events ({len(future)} raw, {len(future) - len(merged)} merged)")

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

    # Update "Senast kontrollerad" to today (content-change detection in
    # check_content_changes.py handles the "Uppdaterad" date at deploy time)
    today_str = datetime.now().strftime("%Y-%m-%d")
    html = re.sub(r'Senast kontrollerad \d{4}-\d{2}-\d{2}', f'Senast kontrollerad {today_str}', html)

    if updated:
        with open(kalender_path, "w") as f:
            f.write(html)
        print(f"[build_kalender] kalender.html updated successfully")
    else:
        print(f"[build_kalender] SVEMO: {len(svemo)} events, UIM: {len(uim)} events (no markers found)")

    return True


if __name__ == "__main__":
    build()
