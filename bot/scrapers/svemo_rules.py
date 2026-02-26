#!/usr/bin/env python3
"""Scrape rule book links from regler.svemo.se and uim.sport."""
import urllib.request
import json
import os
import re

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")

URLS = {
    "vattensport": "https://regler.svemo.se/regelbocker/vattensport",
    "stadgar": "https://regler.svemo.se/stadgar-och-spar",
    "uim": "https://www.uim.sport/RuleBookReleaseList.aspx",
}


def fetch_html(url):
    req = urllib.request.Request(url, headers={"User-Agent": "SVERA-Bot/1.0"})
    resp = urllib.request.urlopen(req, timeout=20)
    return resp.read().decode()


def scrape_svemo_pdfs():
    """Extract PDF links from Svemo rules page."""
    print("[rules] Fetching Svemo rules...")
    html = fetch_html(URLS["vattensport"])
    pdfs = []
    for m in re.finditer(r'href="(https?://[^"]+\.pdf)"', html):
        url = m.group(1)
        # Get filename as title
        name = url.split("/")[-1].replace(".pdf", "").replace("-", " ").replace("_", " ")
        pdfs.append({"title": name, "url": url, "source": "Svemo"})
    print(f"[rules] Found {len(pdfs)} Svemo PDFs")
    return pdfs


def scrape_uim_rules():
    """Extract rule books from UIM."""
    print("[rules] Fetching UIM rules...")
    html = fetch_html(URLS["uim"])
    entries = []

    # Parse article blocks
    for block in re.finditer(r'<article[^>]*>(.*?)</article>', html, re.DOTALL):
        content = block.group(1)
        title_match = re.search(r'<h5[^>]*>(.*?)</h5>', content, re.DOTALL)
        pdf_match = re.search(r'href="(/Documents/[^"]+\.pdf)"', content)
        if not pdf_match:
            pdf_match = re.search(r'href="([^"]+\.pdf)"', content)

        if title_match:
            title = re.sub(r'<[^>]+>', '', title_match.group(1)).strip()
            pdf_url = ""
            if pdf_match:
                pdf_path = pdf_match.group(1)
                if pdf_path.startswith("/"):
                    pdf_url = "https://www.uim.sport" + pdf_path
                else:
                    pdf_url = pdf_path
                pdf_url = pdf_url.replace(" ", "%20")

            # Determine category
            tl = title.lower()
            category = "General"
            if "offshore" in tl:
                category = "Offshore"
            elif "circuit" in tl:
                category = "Circuit"
            elif "aquabike" in tl:
                category = "Aquabike"
            elif "pleasure" in tl:
                category = "Pleasure Navigation"
            elif "e1" in tl:
                category = "E1"
            elif "ethic" in tl or "doping" in tl or "environment" in tl:
                category = "Ethics & Governance"

            # Extract year
            year_match = re.match(r'^(\d{4})', title)
            year = year_match.group(1) if year_match else ""

            entries.append({
                "title": title,
                "year": year,
                "category": category,
                "pdf_url": pdf_url,
                "source": "UIM",
            })

    print(f"[rules] Found {len(entries)} UIM rule books")
    return entries


def save(svemo_pdfs, uim_rules):
    os.makedirs(DATA_DIR, exist_ok=True)
    out = os.path.join(DATA_DIR, "rules.json")
    data = {"svemo": svemo_pdfs, "uim": uim_rules}
    with open(out, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"[rules] Saved to {out}")
    return out


if __name__ == "__main__":
    import sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
    from scrape_tracker import should_scrape, mark_scraped

    if not should_scrape("svemo_rules") and "--force" not in sys.argv:
        print("[svemo_rules] Skipping — scraped recently")
    else:
        svemo = scrape_svemo_pdfs()
        uim = scrape_uim_rules()
        save(svemo, uim)
        mark_scraped("svemo_rules", count=len(svemo) + len(uim))
