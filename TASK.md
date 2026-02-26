# SVERA Website Project — Task Documentation

## Project Overview

**SVERA — Svenska Evenemang & Racerbåtsarkivet**

Rebuild svera.nu as a modern, static website that preserves the spirit and layout of the original Swedish Racerbåtförbundet site (archived at web.archive.org/web/20210310000057/https://www.svera.org/) while updating the identity and content for SVERA's new mission as an independent information platform.

**Note:** The design reference is the OLD svera.org site. The NEW site lives at svera.nu.

---

## Design Reference

### Original Site (2021 archive) — Key Elements to Preserve

The original svera.nu was built on IdrottOnline (Swedish sports federation CMS) and featured:

**Layout:**
- Full-width header with SVERA logo banner
- Horizontal top navigation with dropdown menus
- Main content area: wide left column + narrow right sidebar
- News feed with large featured image + list of articles
- Footer with partner logos, contact info, and social links

**Navigation Structure (7 top-level items):**
1. HUR BÖRJAR JAG? — Getting started, classes, what is boat racing
2. FÖR AKTIVA — Licenses, rules, results, race calendar, anti-doping
3. FÖR KLUBBAR — Club resources, templates, grants
4. SVERA — About, history, bylaws, partners, board protocols
5. UTBILDNING — Education, certification, digital courses
6. BLANKETTER & POLICIES — Forms and policy documents
7. KONTAKT — Office, board, committees, class coaches

**Visual Style:**
- Dark/black primary color (#000000)
- Dark grey secondary (#353535)
- Neutral grey background (#888888 theme)
- Helvetica font family
- Clean, institutional Scandinavian design
- Responsive (mobile menu with hamburger)
- News-driven homepage with dates and "Läs mer" links
- Partner/sponsor logos in sidebar and footer
- UIM (international federation) logo presence
- Riksidrottsförbundet membership badge

---

## New Identity & Content

### Name
**SVERA — Svenska Evenemang & Racerbåtsarkivet**

### Tagline (248 chars)
> SVERA — Sveriges Racerbåtsresurs & Arkiv. Sveriges samlade informationsplattform för båtracing. Resultat, historia, klasser, klubbar och evenemang — allt på ett ställe. Från första tävlingen 1904 till dagens racing. För aktiva, nyfikna och veteraner.

### About Text

**Intro:**
SVERA är Sveriges samlade informationsplattform för racerbåtsporten. Vi dokumenterar, bevarar och tillgängliggör allt som rör svensk båtracing — från historiska milstolpar sedan den första motorbåtstävlingen i Marstrand 1904, till dagens aktiva klasser, förare och evenemang.

**Vad vi gör:**
SVERA samlar information som tidigare varit utspridd och svårtillgänglig på ett och samma ställe. Här hittar du resultat, tävlingskalendrar, klassreglementen, klubbinformation, båt- och förarregister samt reportage och dokumentation från svensk racerbåtshistoria. Oavsett om du är aktiv tävlingsförare, nyfiken nybörjare, funktionär eller nostalgisk veteran — SVERA är din ingång till svensk båtracing.

**Vår bakgrund:**
Namnet SVERA har varit synonymt med svensk racerbåtsport sedan Svenska Racerbåtförbundet grundades 1948. Vi för den traditionen vidare som en oberoende informationsresurs — öppen, tillgänglig och driven av passionen för racing på vatten.

**För alla på vattnet:**
Från rundbana och offshore till aquabike — SVERA täcker alla grenar inom svensk båtracing. Vi vill göra sporten synlig, lättillgänglig och levande för nästa generation.

---

## Updated Navigation Structure

Adapt the original 7-section nav to SVERA's archive/information mission:

| # | Section | Slug | Content |
|---|---------|------|---------|
| 1 | HEM | / | Homepage with news, featured content, intro |
| 2 | OM SVERA | /om | About, history, background, mission |
| 3 | ARKIVET | /arkivet | Historical records, results, race archives |
| 4 | KLASSER & REGLER | /klasser | Class info, regulations, boat/driver registry |
| 5 | KALENDER | /kalender | Upcoming events, race calendar |
| 6 | KLUBBAR | /klubbar | Club directory, regional info |
| 7 | KONTAKT | /kontakt | Contact info, contribute to the archive |

---

## Technical Requirements

### Hosting
- **one.com** free website builder plan
- Static HTML/CSS/JS (no server-side)
- FTP/SFTP deployment
- Credentials stored in `config.json` (KEEP SECRET — .gitignore)

### Stack
- Pure HTML5 + CSS3 + vanilla JS (no frameworks — keeps it simple for one.com free)
- Responsive design (mobile-first)
- Swedish language (`lang="sv"`)
- Open Graph meta tags for social sharing
- SEO-optimized

### Design Guidelines
- Preserve the **clean Scandinavian institutional feel** of the original
- Dark header/nav, light content area
- Font: system fonts stack (Helvetica, Arial, sans-serif)
- Color scheme:
  - Primary: `#1a1a2e` (deep navy/black)
  - Secondary: `#16213e` (dark blue)
  - Accent: `#e94560` (racing red)
  - Background: `#f5f5f5` (light grey)
  - Text: `#333333`
- News/article cards on homepage
- Partner/sponsor area in footer
- Mobile hamburger menu

---

## Bot Automation (OpenClaw)

The SVERA Claw Bot will:

1. **Validate HTML** — Check all pages for W3C compliance
2. **Check broken links** — Scan internal and external links
3. **Update content** — Push content changes via FTP
4. **Optimize images** — Compress before deployment
5. **Auto-deploy** — Upload changed files to one.com via FTP/SFTP

### Bot Config
See `config.json` for API keys and FTP credentials.

### OpenRouter Integration
The bot uses OpenRouter API for AI-assisted content generation and fixes:
- Model: `anthropic/claude-sonnet-4`
- Used for: generating news summaries, fixing HTML issues, suggesting SEO improvements

---

## File Structure

```
svera-website/
├── config.json          # Credentials & config (GITIGNORED)
├── TASK.md              # This file — project documentation
├── CLAUDE.md            # Agent instructions for this project
├── index.html           # Homepage
├── om.html              # About SVERA
├── arkivet.html         # Archive section
├── klasser.html         # Classes & rules
├── kalender.html        # Event calendar
├── klubbar.html         # Club directory
├── kontakt.html         # Contact page
├── assets/
│   ├── css/
│   │   └── style.css    # Main stylesheet
│   ├── js/
│   │   └── main.js      # Navigation, mobile menu, interactions
│   └── images/
│       ├── svera-logo.svg
│       ├── svera-og.png
│       └── hero/
├── bot/
│   ├── deploy.sh        # FTP deployment script
│   ├── validate.sh      # HTML validation
│   └── check-links.sh   # Link checker
└── .gitignore
```

---

## Milestones

- [ ] **M1**: Project scaffolding — folders, config, documentation (THIS STEP)
- [ ] **M2**: HTML templates — header, nav, footer components
- [ ] **M3**: Homepage build — hero, news section, sidebar
- [ ] **M4**: Inner pages — om, arkivet, klasser, kalender, klubbar, kontakt
- [ ] **M5**: Styling — full CSS matching design guidelines
- [ ] **M6**: Mobile responsive — hamburger menu, breakpoints
- [ ] **M7**: Bot setup — OpenClaw integration, FTP deploy script
- [ ] **M8**: Content population — real text, images, links
- [ ] **M9**: SEO & meta — Open Graph, structured data, sitemap
- [ ] **M10**: Deploy to one.com — go live

---

## Notes

- The original site was on IdrottOnline (RF/Riksidrottsförbundet platform). The new SVERA is **independent** — no federation CMS dependency.
- First motorboat race in Sweden: **Marstrand 1904** — key historical anchor.
- SVERA name origin: Svenska Racerbåtförbundet founded **1948**.
- Covers all disciplines: **rundbana** (circuit), **offshore**, **aquabike**.
