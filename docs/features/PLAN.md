# Four features: plan

Status: **approved**; feature 1 in progress. Practice Studio phases 4–7 are paused until
these are done (`docs/practice-studio/PLAN.md`).

## Order and Git

`develop` was branched from `feat/practice-studio` (Studio phases 1–3 included). Each
feature is branched from the latest `develop`, committed in small steps, audited, then
merged with `--no-ff`.

| # | Branch | Depends on | Why this order |
|---|---|---|---|
| 1 | `feat/leaderboard` | – | Small and independent. Adds the public profile card (avatar, username, completed courses, XP) that messaging reuses |
| 2 | `feat/messaging` | 1 (profile card) | Biggest piece; moderation needs its models |
| 3 | `feat/moderation` | 2 | Flags, reports and actions act on messages |
| 4 | `feat/blog` | – | Independent; last as specified |

## What exists today (inspected)

- **XP**: `CustomUser.xp` (indexed). Every grant also leaves a timestamped record:
  `GameAttempt.xp_awarded` + `completed_at`, practice `Attempt.xp_awarded` + `finished_at`
  (previews give 0 XP), and the older `PracticeSession.xp_awarded` + `completed_at`.
  On the local database these add up to `user.xp` for 19 of 20 users; one is 60 XP higher,
  probably a manual or legacy adjustment.
- **Completed courses**: one `courses.CourseProgress` row per finished course.
- **Public user fields**: `username` (unique, may be empty for unfinished profiles) and
  `profile_picture`, served only to signed-in members by `accounts:profile_photo`.
  `full_name` and `email` are private.
- **Leaderboard**: a `leaderboard` app at `/leaderboard/` (top 20, own rank; does **not**
  exclude staff) and a dashboard panel (`dashboard.html` "LEADERBOARD", `get_leaderboard`).
- **Server**: WSGI under Gunicorn (`deploy/gunicorn.conf.py`); `asgi.py` is the stock file.
  No Channels. Cache is `DatabaseCache` (shared by workers); rate limits use
  `cyberquest/ratelimit.py` (`is_rate_limited` keys in the cache).
- **Encryption**: `accounts/crypto.py` already uses `MultiFernet` with `FIELD_ENCRYPTION_KEYS`
  (key derived from `SECRET_KEY` when unset). Messaging follows the same pattern.
- **Media**: private storage (local disk or R2), served through permission-checked views
  (`cyberquest/media_access.serve_stored_file`).
- **Staff areas**: Command Center (superuser-only) and the Practice Studio pattern (group +
  custom permission, `studio_required`). Moderation and the blog editor follow that pattern.
- **Public pages** extend `shared/base.html`; site search (`pages:search`) covers courses.
  No sitemap or feed exists.
- `check --deploy` today: one warning, `accounts.W001` (FIELD_ENCRYPTION_KEYS not set
  locally). Expected locally; must be set in production.

## New dependencies

| Package | Feature | Why |
|---|---|---|
| `channels` (BSD) | 2 | WebSocket consumers with Django auth and sessions |
| `daphne` (BSD) | 2 | ASGI server: makes `runserver` serve WebSockets locally; a production option too |
| `markdown` (BSD) | 4 | Markdown to HTML, pure Python |
| `nh3` (MIT) | 4 | Strict allow-list HTML sanitiser (Rust `ammonia`); maintained and fast, while `bleach` is deprecated |

`channels-redis` is **not** added now. It's documented for production (see below).
No paid services. `cryptography` and `Pillow` are already installed.

## Feature notes

**1. Leaderboard.**
- **Dashboard:** the panel is replaced by a small "View leaderboard" link.
- **Page:** `/leaderboard/` (sign-in required, as today) with a podium, pages of 25, the
  user's own rank pinned, and tabs:
  - **All-time** is `user.xp`.
  - **This month** and **This week** add up the timestamped grants listed above. Manual
    adjustments aren't in any record, so they count only in All-time; the page says so.
- **Who is listed:** active users with a username, excluding staff and superusers.
- **Data:** one annotated query per page, cached 60 s. The user's own rank is one `count()`.

**2. Messaging.**
- **Models:** `Conversation` (exactly two users, unique pair), `Message` (body encrypted
  with `MultiFernet` using a new `MESSAGE_ENCRYPTION_KEYS`; falls back to a key derived from
  `SECRET_KEY` locally, with a `check --deploy` warning), plus `MessagingSettings`
  (Everyone / Nobody), `Block` and read markers.
- **Requests:** a first message from someone new goes to Requests until accepted.
- **Rate limits:** per-user cache counters, 20 messages/min and 10 new conversations/day
  (set in settings).
- **Search:** conversations are searched by **username only**. Bodies are encrypted, so
  there's no content search.
- **API:** JSON endpoints for send and poll (`?after=<id>`, every 4 s). The WebSocket only
  pushes "new message" events; the client then fetches through the same API, so every
  check stays in one place.

**3. Moderation.**
- **Word list:** an editable `moderation/wordlists/*.txt` (English, Bangla, Banglish),
  normalised: lower case, repeated letters squashed, common l33t swaps.
- **Detection:** a check endpoint warns before sending, and stored messages get a flag.
  Detection never punishes anyone.
- **Reports:** with a rate limit. A `Moderator` group with `moderation.moderate` uses a panel
  showing the flagged or reported message plus the 3 before and after.
- **Actions:** dismiss, warn, mute 24 h / 7 d, suspend messaging. Each needs a reason and
  writes to an append-only log; the user is told through the existing `notifications` app.

**4. Blog.**
- **Model and pages:** `Post` plus `/blog/` and `/blog/<slug>/`, public and readable while
  signed out.
- **Who can write:** an editor gated by a `Blog Publisher` group / `blog.publish_post`
  permission (superusers pass).
- **Hidden drafts:** one `Post.objects.published()` queryset is used everywhere (list,
  detail, search, any future feed or sitemap).
- **Body:** Markdown through `markdown`, then `nh3` with an explicit tag and attribute
  allow-list. Rendered once on save and stored; re-sanitised on render as well.
- **Cover image:** Pillow `verify()` + reopen, JPEG/PNG/WebP only, at most 5 MB, re-encoded
  without metadata, random file name. Served by a view that 404s unless the post is
  published or the viewer may edit.

## Decisions (sign-off)

**Leaderboard**
- Week and month boundaries use `settings.TIME_ZONE`; weeks start on **Saturday**
  (Bangladesh week). The page shows the range, e.g. "This week: 25–31 Oct".
- Only staff and superusers are excluded. Content Editors, Publishers and Moderators who
  are regular students still appear.
- Ties: the same XP gets the same rank (1, 2, 2, 4); whoever reached it first is listed first.

**Messaging (feature 2)**
- `MESSAGE_ENCRYPTION_KEYS`: a system check errors clearly if messaging is used without a
  key. Tests use their own generated key. `.env.example` and DEPLOYMENT.md get "generate and
  back up the message key" with the exact command.
- Polling: a lightweight endpoint (only messages after the last id). It pauses while the tab
  is hidden and slows to 15 s after 2 minutes without activity. The 4 s interval applies only
  while a conversation is open and active.
- Plain `python manage.py runserver` keeps working with daphne installed, static files
  included. Production stays on Gunicorn/WSGI for now (polling only).
- Account deletion: a deleted user's messages show as "Deleted user" with the text removed.
  Moderation log entries are kept, with the user reference anonymised.
- The Privacy Policy retention entries and data-export changes for messages, blocks and
  moderation records are part of features 2 and 3, not later.

**Dependencies:** channels, daphne, markdown and nh3 are approved. Exact versions are
pinned and listed in the third-party notices.

## WebSockets: local vs production

| | Local development | Production |
|---|---|---|
| Server | `runserver` (with `daphne` in `INSTALLED_APPS`) serves HTTP and WebSockets | `daphne cyberquest.asgi:application` (or Gunicorn with a Uvicorn worker) behind the host's HTTPS proxy, so sockets are `wss://` |
| Channel layer | In-memory (single process) | Redis via `REDIS_URL` + `channels-redis`, added at launch |
| Without that | – | If `REDIS_URL` is unset and there's more than one process, the in-memory layer can't reach other processes, so the client relies on **polling**. Messaging still works; only instant push is lost |
| Plain WSGI (Gunicorn as now) | – | Works: no sockets, polling only |

The polling fallback is always on, so a socket failure never stops messaging.

## Files likely to change

- **Shared (minimal, only in the feature that needs them):**
  - `cyberquest/settings.py`: apps, channel layer, key and rate-limit settings
  - `cyberquest/urls.py`, `cyberquest/asgi.py`
  - `requirements.txt`
  - `templates/shared/_nav.html` and the dashboard sidebar (links)
  - `dashboard/templates/dashboard/dashboard.html` and `dashboard/dashboard_data.py` (feature 1)
  - `DEPLOYMENT.md`, `THIRD_PARTY_NOTICES.md` and `pages/templates/pages/notices.html`
    (new dependencies)
- **New:** `leaderboard/` (rewritten), plus `messaging/`, `moderation/` and `blog/` apps, each
  with its own templates, static files and tests.

## Risks

- **XP periods:** week and month totals miss manual XP adjustments (explained on the page).
- **Lost message key:** losing `MESSAGE_ENCRYPTION_KEYS` makes stored messages unreadable.
  Back it up like `FIELD_ENCRYPTION_KEYS`; rotate by adding a new key first.
- **Server switch:** WebSockets need the production server to change from WSGI to ASGI.
  Until then, polling covers it.
- **Word list:** Bangla and Banglish word lists will have false positives and gaps. That's
  acceptable because detection only flags; moderators decide.
- **Privacy text:** messaging and the blog change what's stored. The Privacy Policy retention
  table (`accounts/retention.py`) and the data export must list messages, blocks and
  moderation records.
- **SQLite locks:** concurrent writes can lock SQLite in local multi-user tests;
  PostgreSQL in production avoids it.

## Audit checklist (per feature)

Run the suite with `python manage.py test --parallel` (about 90–100 s on 16 cores; about 6–8 min
serially). It ran clean four times in a row in parallel, so tests don't share state. The
browser test (`practice/tests_player_browser.py`) runs whenever Edge or Chrome is installed and
FAILS if the browser won't start; it is skipped only when no browser is installed or
`CQ_SKIP_BROWSER_TESTS=1` is set.


The full suite passes, `makemigrations --check` is clean, migrations apply on a fresh
database, and `check` passes (with `check --deploy` warnings listed here). Then:

- **Security:** permissions on every URL and socket, CSRF, escaping, rate limits, no private
  fields.
- **Commit hygiene:** no secrets, databases or media in the commit.
- **Regressions:** dashboard, practice, Practice Studio and login/2FA still work.
- **Admin pages:** new or changed Command Center pages fit at 820 and 390 px without sideways
  scrolling, have labels, visible focus and confirmations for anything students or members
  will notice.
- **Merge:** merge into `develop` with `--no-ff`, re-run the full suite, and report.

## Audit log

### Feature 1: Leaderboard (merged into `develop`)
- Tests: 525 pass (14 new in `leaderboard/tests_board.py`, Command Center leaderboard tests
  updated to the shared rules). `makemigrations --check` clean (no migrations needed);
  fresh-database `migrate` OK; `check` clean.
- `check --deploy` warnings: `accounts.W001` (FIELD_ENCRYPTION_KEYS not set). Expected
  locally; must be set in production.
- Security: `/leaderboard/` needs sign-in; GET only; `period` is allow-listed, `page` is
  parsed as an int and clamped; usernames are escaped; rows carry public fields only (the
  cache holds the same). Avatars use the existing sign-in-only `accounts:profile_photo`
  URL, which contains the user's numeric id (as on the dashboard before).
- Known limitations: period XP leaves out manual XP adjustments. (Follow-up on `develop`:
  `TIME_ZONE = "Asia/Dhaka"`, so weeks, months, streaks and activity days turn over at
  Dhaka midnight; boundary tests in `cyberquest/tests_timezone.py`.)
- Added to the checklist: compare the student and Command Center leaderboards when
  ranking rules change.

### Feature 2: Messaging (merged into `develop`)
- Tests: 566 pass (35 new in `messaging/tests.py`; avatar and storage tests moved to the
  token route). `makemigrations --check` clean; fresh-database `migrate` OK
  (`accounts.0016_avatar_token`, `messaging.0001_initial`); `check` clean with a key, and
  `messaging.E001` without one (intended).
- `check --deploy` warnings: `accounts.W001` (FIELD_ENCRYPTION_KEYS not set locally).
- Verified by hand: plain `runserver` (daphne) serves pages and static files; the socket
  handshake is `101` when signed in, `403` when anonymous or from another origin.
  Screenshots: conversation (desktop and 390 px), request view.
- Security: every messaging URL needs sign-in and is participant-only (404 otherwise);
  POSTs need CSRF; sockets need a session and a matching Origin and re-check membership
  for every event and frame; rate limits per user; text inserted with `textContent`, no
  `|safe`; JSON carries usernames only (no emails or user ids); avatar URLs use random
  tokens, unknown tokens and blocked viewers get the same default image.
- Known limitations: no WebSockets in production while it runs Gunicorn/WSGI (polling
  covers it); in-memory channel layer is single-process (Redis needed for several); no
  attachments, no message search by content (bodies are encrypted), no read receipts.
  Leaderboard rows are cached for everyone, so they show a blocker's avatar URL, but the
  avatar endpoint still returns the default image to the blocked viewer.
- Added to the checklist: new pages must show public cards via `accounts.public` (never
  user ids); any new message path must go through `messaging/policy.py`.

### Feature 3: Abuse detection, reporting, moderation
Decisions applied (they change the earlier spec):
- Moderators read message content only for messages a participant reported: an encrypted
  snapshot of that message and up to 3 before and after, taken at report time. Content is
  shown only after "Show reported message" (POST, `Cache-Control: no-store`), and every
  view writes a `view` entry to the moderation log.
- Keyword detection only warns the sender ("may be offensive, edit or send anyway?") and
  records metadata (`FlagEvent`: warned / sent anyway; no text, no words). The panel shows
  per-user counts only. Detection never punishes.
- Detection: NFC, invisible (Cf) characters removed, case-folded, l33t swaps, repeated
  letters collapsed, whole-word matching in any script. Terms in
  `moderation/wordlists/terms.txt`; must/must-not examples in `examples.txt` (all tested).
  Starter list: English, Bangla and Banglish insults, threats, sexual harassment; hate terms
  are left for the owner to add per community policy.
- Reports: harassment, hate, threats, spam, sexual content, other (+ note, encrypted);
  "Also block"; 10/day (`MODERATION_REPORTS_PER_DAY`); duplicate report = no-op.
- Panel `/admin-dashboard/moderation/`: Moderator group (`moderation.moderate`) sees only
  moderation; reports a moderator filed or that are about them are hidden (404) and can't
  be acted on. Actions need a reason: dismiss, warn, mute 24 h / 7 d (expire by time, no
  job), suspend (until lifted; lifting needs a reason). Members are notified and see their
  notices with a Contact support link.
- Log: append-only (instance save/delete and queryset delete raise). Deleted accounts leave
  entries with the user cleared.
- Retention: resolved reports and their snapshots are deleted 180 days after resolution
  (`purge_expired_data`), and log entries pointing at them lose the reason text and report
  link; warning metadata is deleted after 90 days (a decision made here: the counts only
  need recent weeks). Privacy Policy, retention table and data export updated (reports
  you filed without message text, restrictions on you, warnings; reports about you are
  excluded so reporters stay anonymous).
- Follow-up: disguised spellings are caught for listed words of 4+ letters (symbols between
  letters dropped, or each symbol standing for one letter: "i.d.i.o.t", "f*ck"), only when a
  whole chunk equals the word; "e.g.", "U.S.A.", versions and URLs stay clean (examples.txt).
- Known limitations: words split by spaces ("i d i o t") aren't caught;
  Banglish has many spellings, so the list will need tuning from real reports; a
  determined user can avoid the warning, which is acceptable because it only warns.

### Feature 4: Blog (merged into `develop`)
- Tests: 616 pass with `--parallel` in about 100 s (23 new in `blog/tests.py`).
  `makemigrations --check` clean; fresh-database `migrate` OK (Content Publisher gets
  `blog.publish_post`); `check` clean; `check --deploy`: only `accounts.W001` (local).
- Verified in a browser: list, article (raw `<script>` in a post shows as text), editor
  (publisher nav shows only Practice Studio and Blog).
- Security: every editor URL gated on the server; drafts, their preview links and their
  images are 404 for anyone who can't edit the blog; titles, excerpts and alt text are
  autoescaped; the body goes through the nh3 allow-list on save and on display.
- Known limitations: no scheduled publishing UI (a future `published_at` stays hidden
  until then, which is tested); no sitemap or feed yet (they must use
  `Post.objects.published()` when added); image upload has no drag-and-drop, the editor
  shows a Markdown line to paste. (Later: Studio phase 7 added an **Insert image** button that
  uploads and inserts the line at the cursor.)
