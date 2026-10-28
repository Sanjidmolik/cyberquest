# Deploying CyberQuest

> **Status:** there is no deployment for now. Development uses SQLite or MySQL; the
> production database at launch will be **PostgreSQL**. No hosting provider has been
> chosen: the Render-specific steps below (service settings, R2 media, health check,
> rollback) describe the earlier Render plan and need adapting to the chosen host.
> **Before the first deploy, run the full test suite against PostgreSQL** (see section 6).

CyberQuest runs as a Python web service (Gunicorn) with a **PostgreSQL** database and private
storage for uploads. This guide covers configuration, the upgrade to this release,
backups, rollback, and checks after a deploy. `deploy/render.yaml.example` shows the
earlier Render setup as a Blueprint.

## 1. How the pieces fit

| Piece | Where | Notes |
|---|---|---|
| Web app | Render web service, Gunicorn | `gunicorn cyberquest.wsgi:application -c deploy/gunicorn.conf.py` |
| Database | PostgreSQL via `DATABASE_URL` (`psycopg2` driver) at launch | Also holds sessions and the rate-limit cache table. Locally: SQLite (unset) or MySQL (`mysqlclient`) |
| Static files | WhiteNoise, collected at build | Hashed, compressed, served by the app |
| Uploads and issued certificates | Private Cloudflare R2 bucket on Render Free (`MEDIA_STORAGE=r2`, section 2a), or a persistent disk at `MEDIA_ROOT` on paid plans | Served only through permission-checked views |
| Email | Brevo HTTPS API (`BREVO_API_KEY`), SMTP fallback | Render's free tier blocks outbound SMTP |
| Health check | `GET /healthz/` | 200 when the database answers, 503 otherwise |

## 2. Environment variables

Set these in Render → service → Environment. Never commit real values; `.env.example`
lists every variable with blank placeholders.

| Variable | Required | Purpose |
|---|---|---|
| `DEBUG` | yes | `False` in production |
| `SECRET_KEY` | yes | Long random value. Signs sessions and keys the verification-code hashes |
| `FIELD_ENCRYPTION_KEYS` | yes | Fernet key that encrypts authenticator secrets. **Back it up**: if it is lost, users with an authenticator app must re-enrol |
| `DATABASE_URL` | yes | `postgres://USER:PASSWORD@HOST:5432/DBNAME`. (A local `mysql://` URL also works; the app adds `utf8mb4` and strict mode for MySQL itself.) |
| `MEDIA_ROOT` | yes | Mount path of the persistent disk, e.g. `/var/data/media` |
| `ALLOWED_HOSTS` | custom domain | Comma-separated. The `*.onrender.com` host is added automatically |
| `CSRF_TRUSTED_ORIGINS` | custom domain | e.g. `https://learn.example.org` |
| `PUBLIC_BASE_URL` | recommended | Origin used in certificate QR codes, no trailing slash |
| `DEFAULT_FROM_EMAIL_ADDRESS` | yes | Verified Brevo sender |
| `BREVO_API_KEY` | yes on Render free | Sends mail over HTTPS |
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` | for Google sign-in | Add `https://<host>/accounts/google/callback/` as an authorised redirect URI |
| `GEMINI_API_KEY` | optional | Admin question generation |
| `SOURCE_CODE_URL` | yes | Public repository, for the AGPL source offer on `/legal/notices/` (see `THIRD_PARTY_NOTICES.md`) |
| `LEGAL_OPERATOR_NAME`, `LEGAL_CONTACT_EMAIL` | recommended | Shown on the Privacy Policy and Terms |
| `PYTHON_VERSION` | recommended | `3.14.6`, matching `.python-version` and CI |
| `LOG_LEVEL`, `WEB_CONCURRENCY`, `GUNICORN_TIMEOUT` | optional | Defaults: `INFO`, `2`, `60` |

Generate the two secrets locally:

```bash
python -c "import secrets; print(secrets.token_urlsafe(64))"                               # SECRET_KEY
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"  # FIELD_ENCRYPTION_KEYS
```

## 2a. Media storage on Render Free: Cloudflare R2

Render Free has no persistent disk, so uploads and issued certificate PDFs must
live outside the service. With `MEDIA_STORAGE=r2` they are stored in a
**private** Cloudflare R2 bucket and still served only through CyberQuest's
permission-checked pages. Local development keeps `MEDIA_STORAGE=filesystem`.

**Bucket setup (in the Cloudflare dashboard):**
1. Create one bucket for CyberQuest media. Leave **public access disabled**
   (no r2.dev subdomain, no custom domain). The app never needs public URLs.
2. Create an R2 API token with **Object Read & Write** on **that bucket only**.
   Copy the Access Key ID and Secret Access Key once; Cloudflare will not show
   the secret again.
3. Note the account ID (or the S3 endpoint `https://<account-id>.r2.cloudflarestorage.com`).

**Render environment variables:**

| Variable | Value |
|---|---|
| `MEDIA_STORAGE` | `r2` |
| `R2_ACCESS_KEY_ID` / `R2_SECRET_ACCESS_KEY` | From the API token (secret) |
| `R2_BUCKET_NAME` | The bucket name |
| `R2_ACCOUNT_ID` or `R2_ENDPOINT_URL` | Account ID, or the full https endpoint |
| `R2_MEDIA_PREFIX` | Optional, default `media` (object keys look like `media/issued_certificates/CQ-….pdf`) |
| `R2_SIGNED_URL_SECONDS` | Optional, default `300` |

If `MEDIA_STORAGE=r2` is set but any required value is missing, the app
refuses to start and names the missing variables (never their values).

**Do not switch production to `r2` before the Phase 2 file migration.**
Existing database rows point at file names; until those files are copied into
the bucket, their downloads return "not found". Issued certificates are never
rebuilt automatically.

Verify Cloudflare's current R2 free-tier limits (storage, Class A/B operations)
and whether a payment method is required before relying on it.

## 3. Commands

| Step | Command | Where |
|---|---|---|
| Build | `./build.sh` (install, `npm install`, `collectstatic`, `check --deploy`, `migrate`, `sync_curriculum`, `load_scenarios`, `convert_scenarios`) | Render build command |
| Start | `gunicorn cyberquest.wsgi:application -c deploy/gunicorn.conf.py` | Render start command |
| Health check | `/healthz/` | Render → Settings → Health Check Path |
| Retention cleanup | `python manage.py purge_expired_data` (daily) | Render cron job, or the service shell |
| Key rotation | `python manage.py rotate_field_encryption` | Service shell, after changing `FIELD_ENCRYPTION_KEYS` |

On paid plans you can move `python manage.py migrate --no-input` out of `build.sh` into
Render's **Pre-Deploy Command**, so a failed migration stops the release before traffic
switches.

## 4. Upgrading to this release (do these in order)

This release encrypts authenticator secrets, hashes email verification codes, and
drops the old plaintext code column (migrations `accounts.0012`–`0014`). It also
contains `games.0008_mission_attempt_timing`.

1. **Back up the database** (section 6). Note the current deploy in Render's Events tab.
2. **Add environment variables**: `FIELD_ENCRYPTION_KEYS`, `SOURCE_CODE_URL`, and
   optionally `LEGAL_OPERATOR_NAME`, `LEGAL_CONTACT_EMAIL`. Store a copy of the
   encryption key in your password manager.
3. **Confirm the disk**: `MEDIA_ROOT` must point at the persistent disk. The build log's
   `check --deploy` prints `cyberquest.W002` if it does not.
4. **Change the start command** to the one in section 3 and set the health check path
   to `/healthz/`.
5. **Deploy.** The build runs `migrate`. Existing TOTP secrets are encrypted in place;
   unexpired email codes keep working; nobody is signed out.
6. **Check** everything in section 7.
7. If any deploy ran this release *before* `FIELD_ENCRYPTION_KEYS` was set, run
   `python manage.py rotate_field_encryption` once from the shell to move secrets
   onto the dedicated key.
8. **Schedule** `python manage.py purge_expired_data` daily.

## 5. Behaviour changes to know about

- `/admin/login/` now redirects to `/admin-login/`, which asks for the account's
  authenticator or email code. Previously both admin sign-in pages skipped two-factor
  checks. Staff without superuser rights can still reach `/admin/` through it.
- A resend requested within 45 seconds of the previous code now says "please wait"
  instead of re-sending the same code, because only a hash of the code is stored.
- Enabling or disabling two-factor sign-in signs out the account's other sessions.
- New certificate IDs use 12 hex characters (`CQ-2026-1A2B3C4D5E6F`). Existing IDs are
  unchanged and still verify.

## 6. Database: local setup, tests, backups and restore

**Local development** uses SQLite (leave `DATABASE_URL` unset) or MySQL 8.0.11+
(`DATABASE_URL=mysql://USER:PASSWORD@HOST:3306/DBNAME`; create the database with
`CHARACTER SET utf8mb4`). **Production at launch is PostgreSQL**
(`DATABASE_URL=postgres://USER:PASSWORD@HOST:5432/DBNAME`). The code uses only portable
database features, and JSON is compared in a canonical form because database JSON types
reorder keys.

**Before the first deploy, run the full suite against PostgreSQL.** It has only run on
SQLite so far. A local Docker/PostgreSQL setup is planned, not done yet. The test runner
creates and drops its own `test_<DBNAME>` database, so the user needs rights to create it:

```bash
DATABASE_URL=postgres://cyberquest:<password>@127.0.0.1:5432/cyberquest python manage.py test --noinput
```

**Backups.** Use the host's automatic backups if it has them. Before every risky deploy,
also take a manual dump from a machine with PostgreSQL client tools:

```bash
pg_dump --format=custom --no-owner --file=cyberquest-$(date +%Y%m%d-%H%M).dump "$EXTERNAL_DATABASE_URL"
```

Restore into an empty database (or after confirming you intend to overwrite):

```bash
pg_restore --no-owner --clean --if-exists --dbname="$TARGET_DATABASE_URL" cyberquest-YYYYMMDD-HHMM.dump
```

Dumps contain personal data: store them encrypted and delete them on the same schedule
as the Privacy Policy describes.

**Uploads.** Render takes daily snapshots of persistent disks on paid plans (restore
from the disk's settings). To copy files off the disk:

```bash
# in the service shell
tar czf /tmp/media.tgz -C "$MEDIA_ROOT" .
```

then download it with `render ssh` / `scp` as described in Render's docs.
`python manage.py seed_persistent_media` re-copies the tracked built-in certificate
templates and course e-books onto an empty disk without overwriting existing files.

**Encryption key.** A database backup is useless for 2FA users without the matching
`FIELD_ENCRYPTION_KEYS`. Keep the key with the backups' access controls, not inside them.

## 7. After every deploy

- `GET https://<host>/healthz/` returns `{"status": "ok"}`.
- Student sign-up: verification email arrives (Brevo dashboard shows it accepted).
- Password reset email arrives and the code works once.
- A 2FA-enabled account must enter its code at `/accounts/login/` and `/admin-login/`.
- Start a mission, refresh mid-way: the timer continues from the server deadline.
- Download an issued certificate twice: same certificate ID, XP unchanged.
- `/privacy/`, `/terms/`, `/legal/notices/` load, and the notices page links the
  deployed commit.
- Settings → Your data downloads JSON and CSV.

## 8. Rollback

**Code only, no new migrations:** use Render → Events → *Rollback* on the previous deploy.

**Rolling back past this release** needs the database reverted first, because the
previous code cannot read encrypted TOTP secrets and still writes the dropped `code`
column. With *this* release still deployed, open the shell and run:

```bash
python manage.py migrate accounts 0011
```

This decrypts TOTP secrets back to their old format. Pending email codes are lost
(they expire in 10 minutes anyway). Then roll back the deploy in Render. Do **not**
roll back the code first: the reverse migration lives in this release.

If a migration fails mid-deploy, Render keeps the previous deploy serving traffic;
fix forward or restore the backup from step 1 of section 4.

## 9. Monitoring

- Application errors are logged to stdout with tracebacks (`LOGGING` in
  `cyberquest/settings.py`) and appear in Render's Logs tab. Request bodies, cookies and
  headers are not logged; one-time codes and passwords only travel in POST bodies.
- Render restarts the service when `/healthz/` fails.
- No paid error tracker is configured. If you add one (for example Sentry), turn off
  sending of personal data and request bodies.

## 10. Custom domain checklist

Add the domain in Render, then set `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`
(`https://` origin) and `PUBLIC_BASE_URL`, and add the new Google OAuth redirect URI.
HSTS (one year, with preload) is sent in production; only submit the domain to the
browser preload list once every subdomain serves HTTPS.
