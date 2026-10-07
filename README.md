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
- SQLite locally; PostgreSQL on Render via `dj-database-url`
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

## Deployment notes

- `build.sh` installs Python deps, runs `npm install`, `collectstatic`, and `migrate` (used on Render).
- Set the same environment variables on the host; do not upload `.env`.
- Production should use a strong `SECRET_KEY`, `DEBUG=False`, and a managed database URL.

## License

This project is licensed under the [MIT License](LICENSE).
