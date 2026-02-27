#!/usr/bin/env python3
"""Build champions.html — SM/RM championship standings from SVEMO results.

Reads bot/data/svemo_results.json, calculates points per driver per class per year,
determines SM vs RM status, and generates a standalone champions.html page.
"""
import json
import os
import re
from collections import defaultdict

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")

# Points table: position → base points (1-indexed)
BASE_POINTS = {1: 20, 2: 17, 3: 15, 4: 13, 5: 11, 6: 10, 7: 9, 8: 8, 9: 7,
               10: 6, 11: 5, 12: 4, 13: 3, 14: 2, 15: 1}
SM_BONUS = 2  # +2 for SM status (tech inspection + drivers meeting)
SM_STARTER_THRESHOLD = 3

# Classes to skip entirely
SKIP_CLASSES = {
    "Classic Cup", "Classic Offshore", "Knop Cupen", "Thundercat",
    "Aquabike Offshore Runabout GP1", "Runabout GP1",
}

# Class name normalization: short letter → canonical name
# V=V24, W=W150, Z=V150 (confirmed by driver cross-reference)
LETTER_RENAMES = {"V": "V24", "W": "W150", "Z": "V150", "T": "T"}


def load_data():
    path = os.path.join(DATA_DIR, "svemo_results.json")
    if not os.path.exists(path):
        print("[build_champions] svemo_results.json not found")
        return None
    with open(path) as f:
        return json.load(f)


def is_sm_competition(comp):
    """Check if competition is an SM/RM event."""
    name = comp["name"]
    return "SM" in name or "RM" in name


def normalize_class_name(raw):
    """Normalize a raw class name to canonical form.

    Examples:
        'Offshore 3A Total' → 'A'
        '3B'                → 'B'
        'V90 (Offshore, >16)' → 'V90'
        'Offshore K Heat 1' → 'K'  (heat flag handled separately)
        'A (Offshore, >16)' → 'A'
    """
    name = raw.strip()

    # Strip "Offshore " prefix
    name = re.sub(r"^Offshore\s+", "", name)

    # Strip Total/Heat suffixes
    name = re.sub(r"\s+(Total|total|Heat\s*\d+)$", "", name)

    # Strip age/type qualifiers like "(Offshore, >16)"
    name = re.sub(r"\s*\(.*?\)\s*$", "", name)

    # Strip "3" prefix from letter classes: 3A → A, 3B → B, etc.
    # But NOT from V90, V24, V150, W150
    m = re.match(r"^3([A-Z])$", name)
    if m:
        name = m.group(1)

    # Rename single-letter classes to canonical
    if name in LETTER_RENAMES:
        name = LETTER_RENAMES[name]

    return name


def should_skip_class(raw_name):
    """Check if a class name should be skipped."""
    name = raw_name.strip()

    # Skip SM TABELL cumulative standings
    if "SM TABELL" in name or "SM Tabell" in name:
        return True

    # Skip known non-SM classes
    for skip in SKIP_CLASSES:
        if skip.lower() in name.lower():
            return True

    # Skip RA GP1 / Aquabike / Runabout
    if "RA GP1" in name or "Aquabike" in name or "Runabout" in name:
        return True

    # Skip Roslagsloppet/Östhammars as class names (2023 combined results)
    if name.startswith("Roslagsloppet") or name.startswith("Östhammars"):
        return True

    # Skip combined foreign driver classes
    if "foreign drivers" in name.lower():
        return True

    return False


def is_heat(raw_name):
    """Check if a class name is a Heat entry."""
    return bool(re.search(r"Heat\s*\d+", raw_name, re.IGNORECASE))


def is_total(raw_name):
    """Check if a class name is a Total entry."""
    return bool(re.search(r"\b[Tt]otal\b", raw_name))


def get_class_base(raw_name):
    """Get the base class name (without Heat/Total suffix) for grouping."""
    name = raw_name.strip()
    name = re.sub(r"\s+(Total|total|Heat\s*\d+)$", "", name)
    name = re.sub(r"^Offshore\s+", "", name)
    # Handle typo: "3JHeat 2" → "3J"
    name = re.sub(r"Heat\s*\d+$", "", name)
    return name.strip()


def select_classes(comp):
    """Select which class entries to use from a competition.

    Rules:
    - Skip SM TABELL, Classic, Knop Cupen, etc.
    - If both Heat and Total exist for a class, use only Total
    - If only Heat entries exist (no Total), skip
    - Return dict of {raw_class_name: entries}
    """
    classes = comp.get("classes", {})
    if not classes:
        return {}

    # Group by base class name
    base_groups = defaultdict(list)
    for raw_name in classes:
        if should_skip_class(raw_name):
            continue
        base = get_class_base(raw_name)
        base_groups[base].append(raw_name)

    selected = {}
    for base, raw_names in base_groups.items():
        has_total = any(is_total(n) for n in raw_names)
        has_heat = any(is_heat(n) for n in raw_names)

        if has_total:
            # Use only Total entries
            for n in raw_names:
                if is_total(n):
                    selected[n] = classes[n]
        elif has_heat:
            # Only heats, no total — skip (incomplete data)
            continue
        else:
            # Plain class name (no Heat/Total suffix) — use directly
            for n in raw_names:
                if not is_heat(n):
                    selected[n] = classes[n]

    return selected


def parse_position(pos_str):
    """Parse position string to int or special status.

    Returns (int_pos, status) where:
    - int_pos is 1-based position or None
    - status is 'ok', 'dnf', 'dsq', 'dns', or 'skip'
    """
    p = pos_str.strip().upper()
    if not p:
        return None, "skip"
    if p == "DNF":
        return None, "dnf"
    if p == "DSQ":
        return None, "dsq"
    if p == "DNS":
        return None, "dns"
    try:
        return int(p), "ok"
    except ValueError:
        # Position contains non-numeric (e.g. a name due to misaligned data)
        return None, "skip"


def is_numeric_points(val):
    """Check if a points value is a valid numeric score."""
    try:
        v = int(val)
        return 0 <= v <= 100
    except (ValueError, TypeError):
        return False


def calc_points(position, starter_count, is_sm):
    """Calculate points for a given position and SM/RM status."""
    if position is None:
        return 0
    base = BASE_POINTS.get(position, 0)
    if base == 0 and position > 15:
        return 0
    bonus = SM_BONUS if is_sm else 0
    return base + bonus


def calc_dnf_points(is_sm):
    """Points for DNF/DSQ: 2 for SM, 0 for RM."""
    return 2 if is_sm else 0


def process_race(entries, is_sm_race):
    """Process entries for a single class at a single race.

    Returns list of {driver, club, nr, position, points, status}
    """
    results = []
    for e in entries:
        pos_int, status = parse_position(e.get("pos", ""))
        if status == "skip" or status == "dns":
            continue

        driver = e.get("driver", "").strip()
        if not driver:
            continue

        # Determine club: if club field is empty, check if points field has club name
        club = e.get("club", "").strip()
        points_raw = e.get("points", "").strip()

        if is_numeric_points(points_raw):
            points = int(points_raw)
        else:
            # Non-numeric points — calculate from position
            # Also: if club is empty and points looks like a club name, use it
            if not club and points_raw and not is_numeric_points(points_raw):
                # Points field likely contains club name (misaligned scraper data)
                club = points_raw

            if status in ("dnf", "dsq"):
                points = calc_dnf_points(is_sm_race)
            elif pos_int is not None:
                points = calc_points(pos_int, 0, is_sm_race)
            else:
                points = 0

        results.append({
            "driver": driver,
            "club": club,
            "nr": e.get("nr", ""),
            "position": pos_int,
            "points": points,
            "status": status,
        })

    return results


def build_standings():
    """Main logic: load data, calculate standings, return structured results."""
    data = load_data()
    if not data:
        return None

    competitions = data.get("competitions", [])
    sm_comps = [c for c in competitions if is_sm_competition(c)]
    print(f"[build_champions] Found {len(sm_comps)} SM/RM competitions")

    # Structure: year → class → driver → {points_list, positions, clubs, races}
    standings = defaultdict(lambda: defaultdict(lambda: defaultdict(lambda: {
        "total_points": 0,
        "race_points": [],
        "positions": [],
        "clubs": set(),
        "nrs": set(),
        "race_count": 0,
    })))

    # Track starters per class per race for SM/RM determination
    # year → class → list of starter_counts per race
    class_race_starters = defaultdict(lambda: defaultdict(list))
    # year → class → set of unique crew identifiers
    class_unique_crews = defaultdict(lambda: defaultdict(set))

    for comp in sm_comps:
        year = comp["date"][:4]
        comp_name = comp["name"]
        comp_date = comp["date"]

        selected = select_classes(comp)
        if not selected:
            print(f"  [{comp_date}] {comp_name}: no valid classes")
            continue

        for raw_class, entries in selected.items():
            norm_class = normalize_class_name(raw_class)

            # Count starters: everyone who showed up (pos is non-empty).
            # DNF/DSQ count — they participated. Only DNS and empty skip.
            starters = 0
            for e in entries:
                pos_int, status = parse_position(e.get("pos", ""))
                if status in ("ok", "dnf", "dsq"):
                    starters += 1

            is_sm_race = starters >= SM_STARTER_THRESHOLD
            class_race_starters[year][norm_class].append(starters)

            # Track unique crews
            for e in entries:
                driver = e.get("driver", "").strip()
                if driver:
                    class_unique_crews[year][norm_class].add(driver)

            # Process race results
            results = process_race(entries, is_sm_race)
            if not results:
                continue

            race_label = f"{comp_date} {comp_name}"

            for r in results:
                driver = r["driver"]
                d = standings[year][norm_class][driver]
                d["total_points"] += r["points"]
                d["race_points"].append({
                    "race": race_label,
                    "points": r["points"],
                    "position": r["position"],
                    "status": r["status"],
                    "is_sm": is_sm_race,
                })
                d["positions"].append(r["position"])
                if r["club"]:
                    d["clubs"].add(r["club"])
                if r["nr"]:
                    d["nrs"].add(r["nr"])
                d["race_count"] += 1

        print(f"  [{comp_date}] {comp_name}: {len(selected)} classes processed")

    # Determine SM vs RM vs no-title per class per year
    class_status = {}  # (year, class) → "SM", "RM", or "–"
    for year in standings:
        for cls in standings[year]:
            starter_counts = class_race_starters[year][cls]
            unique_count = len(class_unique_crews[year][cls])

            if all(s >= SM_STARTER_THRESHOLD for s in starter_counts) and starter_counts:
                class_status[(year, cls)] = "SM"
            elif unique_count >= SM_STARTER_THRESHOLD:
                class_status[(year, cls)] = "RM"
            else:
                class_status[(year, cls)] = "\u2013"  # no championship title

    # Build final sorted standings
    final = {}
    for year in sorted(standings.keys(), reverse=True):
        final[year] = {}
        for cls in sorted(standings[year].keys()):
            drivers = []
            for driver, d in standings[year][cls].items():
                first_places = sum(1 for p in d["positions"] if p == 1)
                clubs_list = sorted(d["clubs"])
                drivers.append({
                    "driver": driver,
                    "club": clubs_list[0] if clubs_list else "",
                    "clubs": clubs_list,
                    "nr": sorted(d["nrs"])[0] if d["nrs"] else "",
                    "total_points": d["total_points"],
                    "race_count": d["race_count"],
                    "first_places": first_places,
                    "race_details": d["race_points"],
                })

            # Sort: total points desc, then first places desc (tiebreaker)
            drivers.sort(key=lambda x: (-x["total_points"], -x["first_places"]))

            status = class_status.get((year, cls), "RM")
            final[year][cls] = {
                "status": status,
                "drivers": drivers,
                "race_count": max((d["race_count"] for d in drivers), default=0),
                "unique_crews": len(class_unique_crews[year][cls]),
            }

    return final


def html_escape(s):
    """Escape HTML special characters."""
    return (s.replace("&", "&amp;").replace("<", "&lt;")
             .replace(">", "&gt;").replace('"', "&quot;"))


def generate_html(standings):
    """Generate the champions.html page."""
    years = sorted(standings.keys(), reverse=True)

    # Build year tabs and content
    year_tabs = ""
    year_content = ""

    for i, year in enumerate(years):
        active = " active" if i == 0 else ""
        display = "block" if i == 0 else "none"
        year_tabs += f'        <button class="year-tab{active}" data-year="{year}">{year}</button>\n'

        classes_html = ""
        year_data = standings[year]

        if not year_data:
            classes_html = '<p class="no-data">Inga mästerskapsdata tillgängliga för detta år.</p>'
        else:
            # Split into championship classes and no-title classes
            champ_classes = []
            notitle_classes = []
            for cn in sorted(year_data.keys()):
                if year_data[cn]["status"] in ("SM", "RM"):
                    champ_classes.append(cn)
                else:
                    notitle_classes.append(cn)

            all_ordered = champ_classes + notitle_classes
            notitle_header_added = False

            for cls_name in all_ordered:
                cls = year_data[cls_name]
                status = cls["status"]
                is_notitle = status not in ("SM", "RM")

                if is_notitle:
                    badge_class = "badge-notitle"
                elif status == "SM":
                    badge_class = "badge-sm"
                else:
                    badge_class = "badge-rm"

                drivers = cls["drivers"]

                if not drivers:
                    continue

                # Add a separator before no-title classes
                if is_notitle and not notitle_header_added and notitle_classes:
                    notitle_header_added = True
                    classes_html += '      <div class="notitle-separator"><span>Klasser utan mästerskapsstatus (&lt;3 unika ekipage under säsongen)</span></div>\n'

                rows = ""
                for rank, d in enumerate(drivers, 1):
                    medal = ""
                    row_class = ""
                    if rank == 1:
                        medal = '<span class="medal gold">1</span>'
                        row_class = " gold-row"
                    elif rank == 2:
                        medal = '<span class="medal silver">2</span>'
                        row_class = " silver-row"
                    elif rank == 3:
                        medal = '<span class="medal bronze">3</span>'
                        row_class = " bronze-row"
                    else:
                        medal = f'<span class="rank">{rank}</span>'

                    driver_esc = html_escape(d["driver"])
                    club_esc = html_escape(d["club"])

                    # Race details for expandable row
                    details = ""
                    for rd in d["race_details"]:
                        race_short = rd["race"]
                        # Shorten race name
                        race_short = re.sub(r"^\d{4}-\d{2}-\d{2}\s+", "", race_short)
                        race_short = re.sub(r"SM/RM Offshore \d{4}\s+", "", race_short)
                        race_short = re.sub(r"^SM \d+ - ", "", race_short)
                        race_esc = html_escape(race_short)
                        pos_str = str(rd["position"]) if rd["position"] else rd["status"].upper()
                        sm_tag = "SM" if rd["is_sm"] else "RM"
                        details += (
                            f'<div class="race-detail">'
                            f'<span class="rd-race">{race_esc}</span>'
                            f'<span class="rd-pos">P{pos_str}</span>'
                            f'<span class="rd-pts">{rd["points"]}p</span>'
                            f'<span class="rd-sm {sm_tag.lower()}">{sm_tag}</span>'
                            f'</div>'
                        )

                    detail_id = f"detail-{year}-{cls_name}-{rank}"
                    rows += f"""              <tr class="driver-row{row_class}" data-detail="{detail_id}">
                <td class="col-pos">{medal}</td>
                <td class="col-driver">{driver_esc}<span class="driver-club">{club_esc}</span></td>
                <td class="col-pts">{d["total_points"]}</td>
                <td class="col-races">{d["race_count"]}</td>
                <td class="col-wins">{d["first_places"]}</td>
              </tr>
              <tr class="detail-row" id="{detail_id}">
                <td colspan="5"><div class="race-details">{details}</div></td>
              </tr>
"""

                cls_esc = html_escape(cls_name)
                status_label = status if status in ("SM", "RM") else "Ej m\u00e4sterskap"
                block_extra = " notitle-block" if is_notitle else ""
                classes_html += f"""      <div class="class-block{block_extra}">
        <div class="class-header">
          <h3>Klass {cls_esc}</h3>
          <span class="status-badge {badge_class}">{status_label}</span>
          <span class="class-meta">{cls["unique_crews"]} ekipage &middot; {cls["race_count"]} deltävlingar</span>
        </div>
        <div class="table-wrap">
          <table class="standings-table">
            <thead>
              <tr>
                <th class="col-pos">#</th>
                <th class="col-driver">Förare</th>
                <th class="col-pts">Poäng</th>
                <th class="col-races">Starter</th>
                <th class="col-wins">Segrar</th>
              </tr>
            </thead>
            <tbody>
{rows}            </tbody>
          </table>
        </div>
      </div>
"""

        year_content += f'      <div class="year-content" id="year-{year}" style="display:{display}">\n{classes_html}      </div>\n'

    today = __import__("time").strftime("%Y-%m-%d")

    html = f"""<!DOCTYPE html>
<html lang="sv">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Svenska- och Riksmästare — SVERA</title>
  <meta name="description" content="SM och RM-ställningar för svensk offshore-racing. Mästerskapsresultat beräknade från SVEMO:s officiella resultat.">
  <meta property="og:title" content="Champions — SVERA">
  <meta property="og:description" content="SM och RM-ställningar för svensk offshore-racing.">
  <meta property="og:type" content="website">
  <meta property="og:url" content="https://www.svera.nu/champions.html">
  <meta property="og:locale" content="sv_SE">
  <link rel="icon" type="image/x-icon" href="favicon.ico">
  <link rel="icon" type="image/png" sizes="32x32" href="assets/images/favicon-32x32.png">
  <link rel="icon" type="image/png" sizes="16x16" href="assets/images/favicon-16x16.png">
  <link rel="apple-touch-icon" sizes="180x180" href="assets/images/apple-touch-icon.png">
  <link rel="stylesheet" href="assets/css/style.css">
  <style>
    .champ-intro{{font-size:.92rem;color:var(--text-light);line-height:1.7;max-width:720px;margin-bottom:8px}}
    .test-badge{{display:inline-block;background:#e74c3c;color:#fff;padding:4px 12px;border-radius:4px;font-size:.7rem;font-weight:700;text-transform:uppercase;letter-spacing:.8px;margin-left:10px;vertical-align:middle}}

    .year-tabs{{display:flex;gap:6px;margin:0 0 24px;flex-wrap:wrap}}
    .year-tab{{padding:10px 24px;border:2px solid var(--border);background:var(--white);border-radius:6px;font-size:.88rem;font-weight:700;color:var(--text-light);cursor:pointer;transition:all var(--transition);font-family:var(--font)}}
    .year-tab:hover{{border-color:var(--primary);color:var(--primary)}}
    .year-tab.active{{background:var(--primary);color:#fff;border-color:var(--primary)}}

    .class-block{{background:var(--white);border-radius:var(--radius);box-shadow:var(--shadow);border:1px solid var(--border);margin-bottom:22px;overflow:hidden}}
    .class-header{{display:flex;align-items:center;gap:12px;padding:16px 22px;border-bottom:2px solid var(--accent);flex-wrap:wrap}}
    .class-header h3{{font-size:1.1rem;color:var(--primary);margin:0;font-weight:700}}
    .status-badge{{display:inline-block;padding:3px 12px;border-radius:4px;font-size:.72rem;font-weight:700;text-transform:uppercase;letter-spacing:.6px}}
    .badge-sm{{background:rgba(253,229,6,0.18);color:#9a7b00;border:1px solid rgba(253,229,6,0.4)}}
    .badge-rm{{background:rgba(37,54,134,0.08);color:var(--primary);border:1px solid rgba(37,54,134,0.2)}}
    .badge-notitle{{background:rgba(90,96,112,0.08);color:var(--text-light);border:1px solid rgba(90,96,112,0.2);font-style:italic}}
    .class-meta{{font-size:.78rem;color:var(--text-light);margin-left:auto}}
    .notitle-block{{opacity:.7}}
    .notitle-block:hover{{opacity:1}}
    .notitle-separator{{padding:18px 0 10px;font-size:.78rem;color:var(--text-light);border-top:1px dashed var(--border);margin-top:8px;text-align:center}}

    .table-wrap{{overflow-x:auto}}
    .standings-table{{width:100%;border-collapse:collapse;font-size:.88rem}}
    .standings-table th{{text-align:left;padding:10px 14px;font-size:.74rem;text-transform:uppercase;letter-spacing:.5px;color:var(--text-light);border-bottom:1px solid var(--border);font-weight:700}}
    .standings-table td{{padding:12px 14px;border-bottom:1px solid var(--border)}}
    .standings-table tbody tr.driver-row{{cursor:pointer;transition:background var(--transition)}}
    .standings-table tbody tr.driver-row:hover{{background:rgba(37,54,134,0.03)}}

    .col-pos{{width:50px;text-align:center}}
    .col-pts,.col-races,.col-wins{{width:70px;text-align:center;font-weight:600}}
    .col-driver{{min-width:180px}}

    .medal{{display:inline-flex;align-items:center;justify-content:center;width:28px;height:28px;border-radius:50%;font-size:.78rem;font-weight:700}}
    .medal.gold{{background:linear-gradient(135deg,#ffd700,#f0c800);color:#5a4700;box-shadow:0 2px 6px rgba(255,215,0,0.35)}}
    .medal.silver{{background:linear-gradient(135deg,#c0c0c0,#a8a8a8);color:#3a3a3a;box-shadow:0 2px 6px rgba(192,192,192,0.35)}}
    .medal.bronze{{background:linear-gradient(135deg,#cd7f32,#b8722e);color:#fff;box-shadow:0 2px 6px rgba(205,127,50,0.35)}}
    .rank{{font-size:.85rem;color:var(--text-light);font-weight:600}}

    .gold-row td{{background:rgba(255,215,0,0.04)}}
    .silver-row td{{background:rgba(192,192,192,0.04)}}
    .bronze-row td{{background:rgba(205,127,50,0.04)}}

    .driver-club{{display:block;font-size:.76rem;color:var(--text-light);font-weight:400;margin-top:2px}}

    .detail-row{{display:none}}
    .detail-row.open{{display:table-row}}
    .detail-row td{{padding:0 14px 14px;background:#f8f9fc}}
    .race-details{{display:flex;flex-wrap:wrap;gap:8px;padding-top:8px}}
    .race-detail{{display:flex;align-items:center;gap:8px;padding:6px 12px;background:var(--white);border-radius:6px;border:1px solid var(--border);font-size:.78rem}}
    .rd-race{{color:var(--text);font-weight:500;max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}
    .rd-pos{{color:var(--primary);font-weight:700}}
    .rd-pts{{color:var(--text-light);font-weight:600}}
    .rd-sm{{padding:2px 6px;border-radius:3px;font-size:.65rem;font-weight:700}}
    .rd-sm.sm{{background:rgba(253,229,6,0.2);color:#9a7b00}}
    .rd-sm.rm{{background:rgba(37,54,134,0.08);color:var(--primary)}}

    .no-data{{font-size:.9rem;color:var(--text-light);padding:24px;text-align:center;font-style:italic}}

    .points-info{{margin-top:28px;background:var(--white);border-radius:var(--radius);box-shadow:var(--shadow);border:1px solid var(--border);padding:24px}}
    .points-info h3{{font-size:1rem;color:var(--primary);margin:0 0 12px;padding-bottom:8px;border-bottom:2px solid var(--accent)}}
    .points-info p{{font-size:.84rem;line-height:1.7;color:var(--text-light);margin-bottom:8px}}
    .points-table{{width:100%;max-width:500px;border-collapse:collapse;font-size:.82rem;margin:12px 0}}
    .points-table th,.points-table td{{padding:6px 12px;border:1px solid var(--border);text-align:center}}
    .points-table th{{background:var(--bg);font-weight:700;color:var(--text)}}

    @media(max-width:600px){{
      .class-header{{padding:12px 16px}}
      .class-header h3{{font-size:.95rem}}
      .class-meta{{width:100%;margin-left:0;margin-top:4px}}
      .standings-table th,.standings-table td{{padding:8px 8px;font-size:.8rem}}
      .col-pos{{width:36px}}
      .col-pts,.col-races,.col-wins{{width:50px}}
      .medal{{width:24px;height:24px;font-size:.7rem}}
      .race-detail{{flex-direction:column;gap:2px;align-items:flex-start}}
      .rd-race{{max-width:160px}}
      .year-tab{{padding:8px 16px;font-size:.82rem}}
    }}
  </style>
</head>
<body>

<a href="#main" class="skip-link">Hoppa till innehåll</a>
<div class="top-bar"><div class="container"><span>Oberoende informationsresurs sedan 2026</span></div></div>

<header class="site-header">
  <div class="container">
    <div class="header-inner">
      <a href="/" class="logo">
        <img class="logo-img" src="assets/images/svera-logo.png" alt="SVERA">
        <div class="logo-text"><h1>SVERA</h1><span class="tagline">Svenska Evenemang &amp; Racerbåtsarkivet</span></div>
      </a>
      <button class="hamburger" aria-label="Meny"><span></span><span></span><span></span></button>
    </div>
  </div>
  <nav class="main-nav">
    <div class="container">
      <ul class="nav-list">
        <li><a href="/">Hem</a></li>
        <li><a href="om.html">Om SVERA</a></li>
        <li><a href="arkivet.html">Arkivet</a></li>
        <li><a href="klasser.html">Klasser &amp; Regler</a></li>
        <li><a href="kalender.html">Kalender</a></li>
        <li>
          <a href="resultat.html" class="active">Resultat</a>
          <ul class="dropdown">
            <li><a href="resultat.html">Tävlingsresultat</a></li>
            <li><a href="champions.html">Svenska- och Riksmästare</a></li>
          </ul>
        </li>
        <li><a href="nyheter.html">Nyheter</a></li>
        <li><a href="klubbar.html">Klubbar</a></li>
        <li><a href="kontakt.html">Kontakt</a></li>
      </ul>
    </div>
  </nav>
</header>

<section class="hero" style="padding:30px 0 24px;">
  <div class="container">
    <span class="hero-badge">Mästerskap</span>
    <h2>Svenska- och Riksmästare<span class="test-badge">Test Deploy</span></h2>
    <p>SM- och RM-ställningar för svensk offshore-racing, beräknade från SVEMO:s officiella resultat. Poäng enligt SVEMO:s tävlingsreglemente.</p>
  </div>
</section>

<div class="container page-content" id="main">

  <div class="content-block">
    <p class="champ-intro">Nedan visas mästerskapsställningar per klass och år. Klicka på en förare för att se detaljerad poängfördelning per deltävling.</p>
    <p class="champ-intro"><strong>SM</strong> = Svenska Mästerskapet — minst 3 startande ekipage i varje deltävling. <strong>RM</strong> = Riksmästerskapet — färre än 3 i någon deltävling men minst 3 unika ekipage under säsongen (regel 4.4). Startande = alla som ställde upp (inkl. DNF/DSQ). Klasser med färre än 3 unika ekipage saknar mästerskapsstatus.</p>

    <div class="year-tabs">
{year_tabs}    </div>

{year_content}
  </div>

  <div class="points-info">
    <h3>Poängsystem</h3>
    <p>Poäng tilldelas enligt SVEMO:s tävlingsreglemente för Offshore. SM-status ger +2 bonuspoäng (teknisk besiktning + förarmöte) utöver baspoängen. "Startande" räknas som alla ekipage som ställde upp vid tävlingen — inklusive DNF och DSQ.</p>
    <table class="points-table">
      <thead>
        <tr><th>Plac.</th><th>SM (3+ startande)</th><th>RM (&lt;3 startande)</th></tr>
      </thead>
      <tbody>
        <tr><td>1:a</td><td>22</td><td>20</td></tr>
        <tr><td>2:a</td><td>19</td><td>17</td></tr>
        <tr><td>3:a</td><td>17</td><td>15</td></tr>
        <tr><td>4:a</td><td>15</td><td>13</td></tr>
        <tr><td>5:a</td><td>13</td><td>11</td></tr>
        <tr><td>6:a</td><td>12</td><td>10</td></tr>
        <tr><td>DNF/DSQ</td><td>2</td><td>0</td></tr>
      </tbody>
    </table>
    <p style="font-size:.78rem;color:var(--text-light);margin-top:12px;">SM-status: 3+ startande (inkl. DNF/DSQ) vid varje deltävling. RM: &lt;3 vid någon deltävling men 3+ unika ekipage under säsongen. Tiebreaker: flest 1:a-platser. Källa: SVEMO:s Tävlingsreglemente, kapitel 4.4.</p>
  </div>

  <div class="wip-notice" style="margin-top:24px;padding:18px 22px;background:#fff8e1;border:1px solid #ffe082;border-left:4px solid #ffc107;border-radius:var(--radius);font-size:.85rem;line-height:1.7;color:#5d4037;">
    <strong>OBS — Work in progress.</strong> Ta inte denna sida för given. Ställningarna hämtas automatiskt från SVEMO:s officiella resultat och borde stämma, men logiken för att avgöra SM- respektive RM-status är inte perfekt. Hittar du fel? <a href="kontakt.html" style="color:#e65100;font-weight:600;">Hör av dig!</a>
  </div>

</div>

<footer class="site-footer">
  <div class="container">
    <div class="footer-grid">
      <div class="footer-col">
        <h3>SVERA</h3>
        <p>Svenska Evenemang &amp; Racerbåtsarkivet</p>
        <p>Oberoende informationsresurs för svensk racerbåtssport.</p>
        <p style="margin-top:10px;"><a href="policy.html" style="display:inline-block;background:rgba(255,255,255,0.08);color:#fde506;padding:6px 14px;border-radius:4px;font-size:0.76rem;font-weight:600;text-decoration:none;border:1px solid rgba(253,229,6,0.25);transition:all 0.2s;">Data &amp; Integritet &rarr;</a></p>
      </div>
      <div class="footer-col">
        <h3>Utforska</h3>
        <ul>
          <li><a href="om.html">Om SVERA</a></li>
          <li><a href="arkivet.html">Arkivet</a></li>
          <li><a href="klasser.html">Klasser &amp; Regler</a></li>
          <li><a href="kalender.html">Kalender</a></li>
          <li><a href="resultat.html">Resultat</a></li>
          <li><a href="champions.html">Svenska- och Riksmästare</a></li>
          <li><a href="nyheter.html">Nyheter</a></li>
          <li><a href="klubbar.html">Klubbar</a></li>
        </ul>
      </div>
      <div class="footer-col">
        <h3>Kontakt</h3>
        <p>Har du material, bilder eller kunskap att bidra med?</p>
        <p><a href="kontakt.html">Kontakta oss &rarr;</a></p>
      </div>
    </div>

    <div class="footer-bottom">
      <div style="margin-bottom:10px;">
        <a href="https://buymeacoffee.com/theralley" target="_blank" rel="noopener" style="display:inline-flex;align-items:center;gap:6px;background:#FFDD00;color:#333;padding:8px 18px;border-radius:6px;font-size:0.82rem;font-weight:700;text-decoration:none;transition:all 0.2s;">&#9749; Bjud oss på en kaffe</a>
      </div>
      <p style="margin-bottom:6px;font-size:0.8rem;color:#8899aa;">Vi samlar och automatiserar informationen kring svensk båtracing — för att göra den tillgänglig för alla. Hjälp oss göra det ännu bättre.</p>
      &copy; 2026 SVERA — Svenska Evenemang &amp; Racerbåtsarkivet. Senast uppdaterad {today}.
    </div>
  </div>
</footer>

<script src="assets/js/main.js"></script>
<script>
// Year tab switching
document.querySelectorAll('.year-tab').forEach(function(tab) {{
  tab.addEventListener('click', function() {{
    document.querySelectorAll('.year-tab').forEach(function(t) {{ t.classList.remove('active'); }});
    document.querySelectorAll('.year-content').forEach(function(c) {{ c.style.display = 'none'; }});
    tab.classList.add('active');
    var year = tab.getAttribute('data-year');
    var el = document.getElementById('year-' + year);
    if (el) el.style.display = 'block';
  }});
}});

// Expandable race details
document.querySelectorAll('.driver-row').forEach(function(row) {{
  row.addEventListener('click', function() {{
    var detailId = row.getAttribute('data-detail');
    var detail = document.getElementById(detailId);
    if (detail) {{
      detail.classList.toggle('open');
      row.classList.toggle('expanded');
    }}
  }});
}});
</script>
</body>
</html>"""

    return html


def build():
    standings = build_standings()
    if not standings:
        print("[build_champions] No standings data")
        return False

    html = generate_html(standings)
    out_path = os.path.join(PROJECT_DIR, "champions.html")
    with open(out_path, "w") as f:
        f.write(html)

    # Print summary
    for year in sorted(standings.keys(), reverse=True):
        classes = standings[year]
        print(f"\n  {year}: {len(classes)} classes")
        for cls in sorted(classes.keys()):
            data = classes[cls]
            top = data["drivers"][0] if data["drivers"] else None
            if top:
                print(f"    {cls} ({data['status']}): {top['driver']} — {top['total_points']}p "
                      f"({top['race_count']} races, {top['first_places']} wins)")

    print(f"\n[build_champions] Generated {out_path}")
    return True


if __name__ == "__main__":
    build()
