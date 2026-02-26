#!/usr/bin/env python3
"""Build resultat.html from scraped webtracking + SVEMO data."""
import json
import os
import re

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")


def load_json(filename):
    path = os.path.join(DATA_DIR, filename)
    if not os.path.exists(path):
        return None
    with open(path) as f:
        return json.load(f)


def sanitize_str(s):
    """Remove control characters that break embedded JS."""
    if not isinstance(s, str):
        return s
    return s.replace("\n", " ").replace("\r", "").replace("\t", " ").strip()


def sanitize_data(obj):
    """Recursively sanitize all strings in a data structure."""
    if isinstance(obj, str):
        return sanitize_str(obj)
    if isinstance(obj, dict):
        return {k: sanitize_data(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [sanitize_data(item) for item in obj]
    return obj


def build():
    races = load_json("webtracking_races.json")
    results = load_json("webtracking_results.json")

    if not races:
        print("[build_resultat] No race data found, run scrapers first")
        return False

    result_path = os.path.join(PROJECT_DIR, "resultat.html")
    if not os.path.exists(result_path):
        print("[build_resultat] resultat.html not found")
        return False

    with open(result_path) as f:
        html = f.read()

    # Sanitize all string data before embedding in HTML
    races = sanitize_data(races)
    if results:
        results = sanitize_data(results)

    # Replace RACES data
    races_compact = json.dumps(races, ensure_ascii=False, separators=(",", ":"))
    html = re.sub(
        r"var RACES=\[.*?\];",
        f"var RACES={races_compact};",
        html,
        count=1,
        flags=re.DOTALL,
    )

    # Replace ENTS/RESULTS data
    if results:
        results_compact = json.dumps(results, ensure_ascii=False, separators=(",", ":"))
        # Replace old ENTS or RESULTS variable
        if "var ENTS=" in html:
            html = re.sub(
                r"var ENTS=\{.*?\};",
                f"var RESULTS={results_compact};",
                html,
                count=1,
                flags=re.DOTALL,
            )
        elif "var RESULTS=" in html:
            html = re.sub(
                r"var RESULTS=\{.*?\};",
                f"var RESULTS={results_compact};",
                html,
                count=1,
                flags=re.DOTALL,
            )

    # Embed SVEMO results data
    svemo = load_json("svemo_results.json")
    if svemo and svemo.get("competitions"):
        svemo_data = sanitize_data(svemo["competitions"])
        svemo_compact = json.dumps(svemo_data, ensure_ascii=False, separators=(",", ":"))
        if "var SVEMO=" in html:
            html = re.sub(
                r"var SVEMO=\[.*?\];",
                f"var SVEMO={svemo_compact};",
                html,
                count=1,
                flags=re.DOTALL,
            )
        print(f"[build_resultat] Embedded SVEMO results: {len(svemo_data)} competitions")

    with open(result_path, "w") as f:
        f.write(html)

    print(f"[build_resultat] Updated resultat.html: {len(races)} races")
    if results:
        print(f"[build_resultat] Embedded results for {len(results)} races")
    return True


if __name__ == "__main__":
    build()
