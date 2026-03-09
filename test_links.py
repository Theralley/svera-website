#!/usr/bin/env python3
"""
SVERA Website Link Tester
Tests all internal navigation links, sub-links (dropdowns), and anchor targets.
"""

import os
import sys
from html.parser import HTMLParser

SITE_DIR = os.path.dirname(os.path.abspath(__file__))

# All pages that should exist
EXPECTED_PAGES = [
    'index.html',
    'om.html',
    'arkivet.html',
    'klasser.html',
    'kalender.html',
    'resultat.html',
    'nyheter.html',
    'klubbar.html',
    'kontakt.html',
    'champions.html',
    'policy.html',
    'team.html',
]


class IDCollector(HTMLParser):
    """Collect all id attributes from an HTML file."""
    def __init__(self):
        super().__init__()
        self.ids = set()

    def handle_starttag(self, tag, attrs):
        for name, value in attrs:
            if name == 'id' and value:
                self.ids.add(value)


class NavLinkCollector(HTMLParser):
    """Collect all links from the main nav."""
    def __init__(self):
        super().__init__()
        self.in_nav = False
        self.in_dropdown = False
        self.nav_links = []
        self.dropdown_links = []
        self.current_href = None
        self.current_text = ''

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        if tag == 'nav' and 'main-nav' in attrs_dict.get('class', ''):
            self.in_nav = True
        if self.in_nav and tag == 'ul' and 'dropdown' in attrs_dict.get('class', ''):
            self.in_dropdown = True
        if tag == 'a':
            self.current_href = attrs_dict.get('href', '')
            self.current_text = ''

    def handle_data(self, data):
        if self.current_href is not None:
            self.current_text += data.strip()

    def handle_endtag(self, tag):
        if tag == 'a' and self.current_href is not None:
            if self.in_nav:
                if self.in_dropdown:
                    self.dropdown_links.append((self.current_href, self.current_text))
                else:
                    self.nav_links.append((self.current_href, self.current_text))
            self.current_href = None
            self.current_text = ''
        if tag == 'ul' and self.in_dropdown:
            self.in_dropdown = False
        if tag == 'nav' and self.in_nav:
            self.in_nav = False


def load_ids(filepath):
    parser = IDCollector()
    with open(filepath, 'r', encoding='utf-8') as f:
        parser.feed(f.read())
    return parser.ids


def load_nav(filepath):
    parser = NavLinkCollector()
    with open(filepath, 'r', encoding='utf-8') as f:
        parser.feed(f.read())
    return parser.nav_links, parser.dropdown_links


def resolve_href(href):
    if href == '/':
        return 'index.html', None
    if '#' in href:
        page, anchor = href.split('#', 1)
        if not page:
            return None, anchor
        return page, anchor
    return href, None


def main():
    errors = []
    warnings = []
    passed = 0
    total = 0

    # Pre-load all ids
    page_ids = {}
    for page in EXPECTED_PAGES:
        filepath = os.path.join(SITE_DIR, page)
        if os.path.exists(filepath):
            page_ids[page] = load_ids(filepath)
        else:
            page_ids[page] = set()

    print("=" * 60)
    print("SVERA Website Link Test Report")
    print("=" * 60)

    # Test 1: All expected pages exist
    print("\n--- Test 1: Page existence ---")
    for page in EXPECTED_PAGES:
        total += 1
        filepath = os.path.join(SITE_DIR, page)
        if os.path.exists(filepath):
            print(f"  [PASS] {page} exists")
            passed += 1
        else:
            print(f"  [FAIL] {page} MISSING")
            errors.append(f"Missing page: {page}")

    # Test 2: Klubbar dropdown exists on all pages with correct items
    print("\n--- Test 2: Klubbar dropdown on all pages ---")
    expected_klubbar_dropdown = [
        ('klubbar.html', 'Klubbar'),
        ('team.html', 'Aktiva Team'),
    ]
    for page in EXPECTED_PAGES:
        total += 1
        filepath = os.path.join(SITE_DIR, page)
        if not os.path.exists(filepath):
            continue
        _, dropdown_links = load_nav(filepath)
        # Get dropdown items that are klubbar.html or team.html
        klubbar_drops = [(h, t) for h, t in dropdown_links if h in ('klubbar.html', 'team.html')]
        if klubbar_drops == expected_klubbar_dropdown:
            print(f"  [PASS] {page} has correct Klubbar dropdown (Klubbar + Aktiva Team)")
            passed += 1
        elif klubbar_drops:
            print(f"  [FAIL] {page} has Klubbar dropdown but wrong items: {klubbar_drops}")
            errors.append(f"{page}: Klubbar dropdown has wrong items")
        else:
            print(f"  [FAIL] {page} MISSING Klubbar dropdown")
            errors.append(f"{page}: Missing Klubbar dropdown")

    # Test 3: All dropdown anchor targets exist
    print("\n--- Test 3: All dropdown targets resolve ---")
    ref_path = os.path.join(SITE_DIR, 'index.html')
    _, ref_dropdowns = load_nav(ref_path)

    for href, text in ref_dropdowns:
        total += 1
        page, anchor = resolve_href(href)
        if page and anchor:
            if page not in page_ids:
                filepath = os.path.join(SITE_DIR, page)
                if os.path.exists(filepath):
                    page_ids[page] = load_ids(filepath)
                else:
                    print(f"  [FAIL] {href} -> page '{page}' not found")
                    errors.append(f"Broken link: {href} (page not found)")
                    continue
            if anchor in page_ids[page]:
                print(f"  [PASS] {href} -> #{anchor} exists in {page}")
                passed += 1
            else:
                print(f"  [FAIL] {href} -> #{anchor} NOT FOUND in {page}")
                errors.append(f"Broken anchor: {href} (#{anchor} missing in {page})")
        elif page:
            filepath = os.path.join(SITE_DIR, page)
            if os.path.exists(filepath):
                print(f"  [PASS] {href} -> page exists")
                passed += 1
            else:
                print(f"  [FAIL] {href} -> page NOT FOUND")
                errors.append(f"Broken link: {href}")

    # Test 4: team.html exists and has proper content
    print("\n--- Test 4: team.html page ---")
    total += 1
    team_path = os.path.join(SITE_DIR, 'team.html')
    if os.path.exists(team_path):
        print(f"  [PASS] team.html exists")
        passed += 1
    else:
        print(f"  [FAIL] team.html MISSING")
        errors.append("team.html: Page missing")

    total += 1
    if 'main' in page_ids.get('team.html', set()):
        print(f"  [PASS] team.html has #main")
        passed += 1
    else:
        print(f"  [FAIL] team.html missing #main")
        errors.append("team.html: Missing #main")

    # Test 5: klubbar.html should NOT have aktiva-team section anymore
    print("\n--- Test 5: klubbar.html clean (no aktiva-team) ---")
    total += 1
    if 'aktiva-team' not in page_ids.get('klubbar.html', set()):
        print(f"  [PASS] klubbar.html does NOT have #aktiva-team (moved to team.html)")
        passed += 1
    else:
        print(f"  [FAIL] klubbar.html still has #aktiva-team (should be on team.html)")
        errors.append("klubbar.html: Still has #aktiva-team, should be removed")

    # Test 6: All main nav page links resolve
    print("\n--- Test 6: Main nav links ---")
    main_nav_hrefs = ['/', 'om.html', 'arkivet.html', 'klasser.html', 'kalender.html',
                       'resultat.html', 'nyheter.html', 'klubbar.html', 'kontakt.html', 'team.html']
    for href in main_nav_hrefs:
        total += 1
        page, _ = resolve_href(href)
        filepath = os.path.join(SITE_DIR, page)
        if os.path.exists(filepath):
            print(f"  [PASS] {href} -> {page} exists")
            passed += 1
        else:
            print(f"  [FAIL] {href} -> {page} NOT FOUND")
            errors.append(f"Nav link broken: {href}")

    # Test 7: Om SVERA dropdown anchors
    print("\n--- Test 7: Om SVERA dropdown anchors ---")
    om_anchors = [('om.html', 'mission'), ('om.html', 'historia'),
                   ('om.html', 'teknik'), ('om.html', 'vision'), ('om.html', 'stod')]
    for page, anchor in om_anchors:
        total += 1
        if anchor in page_ids.get(page, set()):
            print(f"  [PASS] {page}#{anchor}")
            passed += 1
        else:
            print(f"  [FAIL] {page}#{anchor} NOT FOUND")
            errors.append(f"Missing anchor: {page}#{anchor}")

    # Test 8: Arkivet dropdown anchors
    print("\n--- Test 8: Arkivet dropdown anchors ---")
    ark_anchors = [('arkivet.html', 'historia'), ('arkivet.html', 'nyheter'),
                    ('arkivet.html', 'forare'), ('arkivet.html', 'classic')]
    for page, anchor in ark_anchors:
        total += 1
        if anchor in page_ids.get(page, set()):
            print(f"  [PASS] {page}#{anchor}")
            passed += 1
        else:
            print(f"  [FAIL] {page}#{anchor} NOT FOUND")
            errors.append(f"Missing anchor: {page}#{anchor}")

    # Test 9: Klasser dropdown anchors
    print("\n--- Test 9: Klasser & Regler dropdown anchors ---")
    klass_anchors = [('klasser.html', 'rundbana'), ('klasser.html', 'offshore'),
                      ('klasser.html', 'aquabike'), ('klasser.html', 'regler')]
    for page, anchor in klass_anchors:
        total += 1
        if anchor in page_ids.get(page, set()):
            print(f"  [PASS] {page}#{anchor}")
            passed += 1
        else:
            print(f"  [FAIL] {page}#{anchor} NOT FOUND")
            errors.append(f"Missing anchor: {page}#{anchor}")

    # Test 10: Nav consistency — all pages have same Klubbar dropdown
    print("\n--- Test 10: Nav consistency across all pages ---")
    for page in EXPECTED_PAGES:
        total += 1
        filepath = os.path.join(SITE_DIR, page)
        if not os.path.exists(filepath):
            continue
        _, drops = load_nav(filepath)
        klubbar_drops = [(h, t) for h, t in drops if h in ('klubbar.html', 'team.html')]
        if klubbar_drops == expected_klubbar_dropdown:
            print(f"  [PASS] {page} Klubbar dropdown consistent")
            passed += 1
        else:
            print(f"  [FAIL] {page} Klubbar dropdown inconsistent: {klubbar_drops}")
            errors.append(f"{page}: Inconsistent Klubbar dropdown")

    # Summary
    print("\n" + "=" * 60)
    print(f"RESULTS: {passed}/{total} passed")
    if warnings:
        print(f"WARNINGS: {len(warnings)}")
        for w in warnings:
            print(f"  - {w}")
    if errors:
        print(f"ERRORS: {len(errors)}")
        for e in errors:
            print(f"  - {e}")
        sys.exit(1)
    else:
        print("ALL TESTS PASSED!")
        sys.exit(0)


if __name__ == '__main__':
    main()
