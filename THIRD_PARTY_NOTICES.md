# Third-party notices and licence audit

CyberQuest's own code is released under the [MIT License](LICENSE). It depends on
third-party software, fonts and media that keep their own licences, listed here.

This is an engineering audit, not legal advice. Items marked **Needs review** should
be checked by someone qualified before relying on them. Audit date: 13 October 2026,
against the pinned `requirements.txt`, `package-lock.json` and files in the repository.

## 1. Key finding: PyMuPDF is AGPL-3.0

| | |
|---|---|
| Package | `PyMuPDF==1.28.2` (bundles the MuPDF library) |
| Licence | Dual: **GNU AGPL-3.0** or an **Artifex commercial licence** |
| Rights holder | Artifex Software, Inc. |
| Used for | Filling certificate templates and generating certificate PDFs (`certificates/services/generator.py`, `certificates/layout.py`), rendering certificate previews to PNG, counting course PDF pages (`courses/progress.py`) |
| Commercial licence purchased? | **Not verified.** Nothing in the repository shows one. Treat CyberQuest as using PyMuPDF under the AGPL. |

**Why it matters.** CyberQuest is a web application that imports PyMuPDF. AGPL-3.0 §13
requires that users who interact with a modified covered program over a network be
offered its Corresponding Source. Artifex's stated position is that an application
using PyMuPDF under the AGPL must itself be made available under AGPL terms, including
to network users. Whether CyberQuest is a "work based on" PyMuPDF is a legal question
(**Needs review**), so the conservative reading is assumed.

**What the project does today to follow the AGPL route:**

1. The complete CyberQuest source is public at
   `https://github.com/Sanjidmolik/cyberquest` (checked: the repository URL returns
   HTTP 200). MIT is compatible with distribution as part of an AGPL-licensed whole.
2. The public **Licenses & source code** page (`/legal/notices/`, linked from every
   footer) offers the source to every visitor. Set `SOURCE_CODE_URL` in production;
   on Render the deployed commit (`RENDER_GIT_COMMIT`) is linked automatically, so the
   offer points at the exact running version.
3. The AGPL-3.0 text is in [`LICENSES/AGPL-3.0.txt`](LICENSES/AGPL-3.0.txt).
4. PyMuPDF and MuPDF are used unmodified from the PyPI wheel.

**Conditions for this route to stay valid:**

- The deployed code must stay public, including any production-only changes.
  A private fork, private hotfix branch or closed add-on breaks it.
- `SOURCE_CODE_URL` must be set in production and the repository must stay public.
- Any change to PyMuPDF/MuPDF itself must be published too.

**If those conditions cannot be met**, either obtain a commercial licence from
Artifex (https://artifex.com/licensing) or replace PyMuPDF. Replacement is a real
engineering project: candidates are `pypdf` (BSD-3-Clause) with `reportlab`
(BSD) for overlays and `pypdfium2` (Apache-2.0 / BSD-3-Clause) for PNG previews.
Note that the Bengali name support added on 13 October 2026 relies on MuPDF's
HarfBuzz text shaping; a replacement must shape complex scripts too (ReportLab does
not out of the box; WeasyPrint does, but needs Pango on the host).

## 2. Python dependencies (`requirements.txt`)

Licences below are read from each installed package's metadata.

| Package | Version | Licence | Notes |
|---|---|---|---|
| asgiref | 3.12.1 | BSD-3-Clause | |
| boto3 / botocore | 1.43.105 | Apache-2.0 | Added for Cloudflare R2 media storage (S3 API). |
| certifi | 2026.7.22 | MPL-2.0 | File-level copyleft; used unmodified, so no source obligation. |
| cffi | 2.1.1 | MIT-0 (per metadata) | |
| charset-normalizer | 3.5.1 | MIT | |
| colorama | 0.4.6 | BSD | |
| cryptography | 50.0.1 | Apache-2.0 OR BSD-3-Clause | Added for TOTP secret encryption. Wheels bundle OpenSSL (Apache-2.0). |
| django-storages | 1.14.6 | BSD-3-Clause | R2 storage backend (`cyberquest/storage.py`). Metadata lists Django ≤5.1; verified offline against Django 6.0.7 / Python 3.14.6 (save, exists, open, signed URLs). |
| dj-database-url | 3.1.2 | BSD-3-Clause | |
| Django | 6.0.7 | BSD-3-Clause | |
| gunicorn | 26.2.0 | MIT | |
| idna | 3.19 | BSD-3-Clause | |
| jmespath | 1.1.0 | MIT | boto3 dependency. |
| mysqlclient | 2.2.8 | GPL-2.0-or-later | The MySQL driver for local development (`DATABASE_URL=mysql://…`). GPL-2 obligations attach to distribution, not network use, so running it as a web service creates no obligation; keep this notice if you ever distribute the app with it. |
| pillow | 12.1.1 | MIT-CMU | |
| psycopg2-binary | 2.9.13 | LGPL-3.0 with exceptions | PostgreSQL driver for the production database at launch. Wheels bundle libpq (PostgreSQL Licence) and OpenSSL. No obligation for network use; keep notices if you ever distribute the wheel. |
| pycparser | 3.0 | BSD-3-Clause | |
| PyMuPDF | 1.28.2 | AGPL-3.0 or commercial | See section 1. |
| PyMySQL | 1.2.0 | MIT | Unused: installed locally but not in `requirements.txt`; the app uses mysqlclient. |
| pyotp | 2.9.0 | MIT | |
| python-dateutil | 2.9.0.post0 | Apache-2.0 or BSD-3-Clause (dual) | botocore dependency. |
| python-dotenv | 1.2.2 | BSD-3-Clause | |
| qrcode | 8.2 | BSD | |
| requests | 2.32.5 | Apache-2.0 | |
| s3transfer | 0.19.2 | Apache-2.0 | boto3 dependency. |
| six | 1.17.0 | MIT | python-dateutil dependency. |
| sqlparse | 0.5.5 | BSD | |
| tzdata | 2026.3 | Apache-2.0 | |
| urllib3 | 2.7.0 | MIT | |
| whitenoise | 6.12.0 | MIT | |

The local virtualenv also contains `reportlab` and `weasyprint`, which are not in
`requirements.txt` and not imported by the application. They are not deployed.

## 3. JavaScript

| Package | Version | Licence | How it reaches users |
|---|---|---|---|
| page-flip (StPageFlip) | 2.0.7 | MIT, Copyright (c) 2020 Nodlik | Served from our static files (`courses/static/courses/js/vendor/page-flip.browser.js` and via `node_modules`). The minified file has no header, so the licence is shipped next to it as `page-flip.LICENSE.txt` and in [`LICENSES/MIT-page-flip.txt`](LICENSES/MIT-page-flip.txt). |
| GSAP + ScrollTrigger | 3.15.0 | GSAP Standard "No Charge" License (https://gsap.com/standard-license) | Loaded from jsDelivr on the homepage. Free for sites that do not charge end users for access. **Needs review** if CyberQuest ever charges users. Note: GSAP 3.13+ did **not** change to MIT — the licence URL moved from greensock.com to gsap.com but the terms remain the "Standard No Charge" licence. Verified against npm registry metadata 14 Oct 2026. |
| Lenis | 1.1.13 | MIT | Loaded from jsDelivr on the homepage. |
| PDF.js | 3.11.174 | Apache-2.0 (Mozilla) | Loaded from cdnjs in the course reader. |

CDN-loaded scripts are not redistributed by CyberQuest, but they do expose visitors'
IP addresses to the CDN (disclosed in the Privacy Policy).

## 4. Fonts

| Font | Licence | Delivery |
|---|---|---|
| Comic Neue (Regular, Bold) | SIL OFL 1.1, Copyright 2014 The Comic Neue Project Authors | Bundled for PDF embedding; licence in `certificates/static/certificates/fonts/OFL-ComicNeue.txt` and `LICENSES/`. |
| Noto Sans Bengali (Regular, Bold) | SIL OFL 1.1, Copyright The Noto Project Authors | Bundled for Bengali certificate names; licence alongside and in `LICENSES/`. |
| Bangers, Comic Neue, Inter, JetBrains Mono, IBM Plex Sans/Mono, Cinzel, Cormorant Garamond, Great Vibes | SIL OFL 1.1 (Google Fonts) | Loaded from Google Fonts at runtime; not redistributed. |

## 5. Images, illustrations and documents (**Needs review**)

The repository does not record where these came from or under what terms. They
must not be assumed to be CyberQuest's own work until the owner confirms it:

- Mission artwork: `games/static/games/mission-timer/assets/art/{phishing,password,network,crypto,stego}.jpg`
- Certificate designs: `media/certificate_templates/CyberQuest_Certificate_of_Achievement.pdf`, `a.pdf`, `b.pdf`, `bg.jpg`, `design.png`, `new.png`
- Course e-books: `media/course_ebooks/The_Phishing_Detectives_Handbook.pdf`, `course1.pdf`
- Sample avatar: `media/profile_pictures/dragon.png`, `profile_pictures/`
- Homepage comic/illustration assets under `home page/`

For each, record the creator, source, and licence (or that it was made for the
project). If any was generated with an AI image tool, record which tool and check its
terms for commercial or public use. Inline SVG icons in templates appear to be
hand-written for the project; confirm.

Quiz questions drafted with Google Gemini are AI output; check Google's terms for the
plan in use and keep human review in place (the admin review step already exists).

## 6. Open questions for professional review

1. Does CyberQuest, which imports PyMuPDF, have to be offered under AGPL-3.0 as a
   whole, and is the public-repository source offer on `/legal/notices/` sufficient?
2. Is a commercial Artifex licence preferable given how the project will be operated?
3. Provenance and licences of the media listed in section 5.
4. GSAP 3.15.0 licence terms if the service is ever monetised. The licence is "GSAP Standard No Charge" — free for non-commercial use; a paid licence is required if end users are charged for access.
