# CyberQuest

Comic-style cybersecurity learning platform built with Django. Learn defensive skills through courses, interactive games, adaptive practice, and earn a verifiable completion certificate.

Public site branding also appears as **CyberShield Academy**.

## Features

- **Courses** — Book-style flip reader with plain-text lessons or uploaded PDF e-books
- **Games** — Phishing simulator, password security, cryptography, OSINT, steganography, and network defense quizzes
- **Adaptive practice** — Scenario practice with history and a “Cyber DNA” progress view
- **AI question bank** — Optional Gemini-powered question generation (server-side API key only)
- **Accounts** — Email signup/login, Google OAuth, email 2FA, and TOTP authenticator support
- **Dashboard, badges, leaderboard, notifications**
- **Certificates** — Eligibility after all 5 core games at ≥80% overall; PyMuPDF PDF generation, admin templates, QR verification

## Tech stack

- Python 3 / **Django 6**
- SQLite or MySQL locally; PostgreSQL in production at launch, chosen by `DATABASE_URL` (`dj-database-url`)
- Frontend templates + shared theme CSS/JS
- PyMuPDF + qrcode for certificate PDFs
- WhiteNoise for static files in production

## Quick start

### 1. Clone and create a virtual environment

```bash
git clone https://github.com/Sanjidmolik/cyberquest.git
cd cyberquest
python -m venv venv
```

Activate it:

- Windows (Git Bash): `source venv/Scripts/activate`
- Windows (PowerShell): `.\venv\Scripts\Activate.ps1`
- macOS / Linux: `source venv/bin/activate`

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure environment variables

Copy the example file and fill in real values locally (never commit `.env`):

```bash
cp .env.example .env
```

Useful keys in `.env`:

| Variable | Purpose |
|---|---|
| `SECRET_KEY` | Django secret (required in production) |
| `DEBUG` | `True` for local dev |
| `EMAIL_HOST_USER` / `EMAIL_HOST_PASSWORD` | Gmail app password for mail |
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` | Google sign-in |
| `GEMINI_API_KEY` | AI question bank (optional) |
| `PUBLIC_BASE_URL` | Public site origin for certificate QR links (e.g. `https://your-app.onrender.com`) |
| `FIELD_ENCRYPTION_KEYS` | Fernet key for encrypting authenticator secrets (required in production) |

### 4. Migrate and run

```bash
python manage.py migrate
python manage.py runserver
```

Open [http://127.0.0.1:8000/](http://127.0.0.1:8000/).

## Project layout

| App | Role |
|---|---|
| `accounts` | Auth, profile, 2FA, OAuth |
| `courses` | Lessons and learning reader |
| `games` | Interactive security quizzes |
| `practice` | Adaptive practice scenarios |
| `question_bank` | AI / question generation API |
| `certificates` | Issue, download, verify certificates |
| `dashboard` | Learner home |
| `achievements` | Badges |
| `leaderboard` | Rankings |
| `notifications` | In-app alerts |
| `pages` | Marketing / about / contact / home |
| `messaging` | One-to-one messages (encrypted at rest) |
| `moderation` | Offensive-message warnings, reports, moderation panel |

## Running the tests

```bash
python manage.py test --parallel
```

Runs the whole suite on all CPU cores (about 1.5 minutes on a 16-core machine, against
about 6–8 minutes without `--parallel`). Each worker gets its own copy of the test database
and cache, and the tests never use live keys from `.env` or the network. Add an app name
(`python manage.py test messaging`) to run one part.

`practice/tests_player_browser.py` runs the real practice player in headless Edge or Chrome.
It is skipped only when no such browser is installed, or when `CQ_SKIP_BROWSER_TESTS=1` is
set (for CI images without a browser). If a browser is installed but can't start, the test
fails with a message saying so.

## Deployment notes

- See **[DEPLOYMENT.md](DEPLOYMENT.md)** for Render configuration, the upgrade order, backups, and rollback.
- `build.sh` installs Python deps, runs `npm install`, `collectstatic`, `check --deploy`, and `migrate` (used on Render).
- Set the same environment variables on the host; do not upload `.env`.
- Production needs a strong `SECRET_KEY`, `FIELD_ENCRYPTION_KEYS`, `DEBUG=False`, a managed database URL, and `MEDIA_ROOT` on a persistent disk.
- `python manage.py purge_expired_data` applies the retention periods in the Privacy Policy; schedule it daily.

## License

CyberQuest's own code is licensed under the [MIT License](LICENSE). It uses PyMuPDF, which is
licensed under the AGPL-3.0 (or an Artifex commercial licence); see
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) for what that means for deployments and for
all other third-party licences.
