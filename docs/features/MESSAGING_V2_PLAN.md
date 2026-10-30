# Messaging v2: plan

Branch `feat/messaging-v2` from the latest `develop` (`ddbfda1`). This extends features 2
(messaging) and 3 (moderation). Nothing is rebuilt, no model is replaced, and every existing
URL, test and behaviour keeps working.

> **Missing references.** `docs/messaging-design/messages-prototype.dc.html` and
> `docs/messaging-design/hero.png` are not in the repository or anywhere else on this machine.
> Until they are added, the screenshot in the request is the visual reference. The hero image
> must be the original file: I won't redraw it.

---

## 0. What exists today (inspected)

| Area | Today |
|---|---|
| Models | `Conversation` (exactly two people; `state` pending/accepted/declined; `a_read_upto` / `b_read_upto` = the last message id each side has seen), `Message` (Fernet `body`, `removed` flag), `MessagingPreference` (`who_can_message`), `Block`. One migration (`0001`). |
| Encryption | `messaging/crypto.py`: MultiFernet with `MESSAGE_ENCRYPTION_KEYS` (newest first), `rotate_message_keys` command, and a system check that refuses to start without a key. |
| Transport | HTTP JSON API (`api/inbox`, `send`, `poll?after=`, `read`). Polling always runs. The WebSocket (`/ws/messages/`, Channels) only says "conversation X changed", then the browser polls. **Production runs Gunicorn (WSGI), so production has no WebSocket today**; `REDIS_URL` is optional. |
| Rules | `policy.py`: requests, "who can message me", blocks either way, moderation restrictions, and rate limits (`MESSAGING_MESSAGES_PER_MINUTE`, `MESSAGING_NEW_CONVERSATIONS_PER_DAY`) on the database-cache limiter. |
| Moderation | `Report.snapshot` = encrypted JSON of the reported message plus up to three either side, taken when the report is made. A moderator reads it only by pressing "Show", and every view is logged. Resolved reports are deleted after 180 days (`purge_old`). |
| Retention | `accounts/retention.py`: the `RETENTION` table shown in the Privacy Policy, plus `run_all()` behind `purge_expired_data` (scheduled daily). |
| Export | `accounts/privacy.py` → `messaging.services.export_for` and `moderation.services.export_for`. |
| Files | No public `/media/` route. Private files are streamed through permission-checked views (`cyberquest/media_access.py`); in production they live in a private R2 bucket (`MEDIA_STORAGE=r2`). |
| Wording | The inbox and the Privacy Policy currently say "**Not** end-to-end". There is no top-bar search on the student layout (`base_command.html`); the inbox's list search says "Search by username". |

---

## 1. Model changes (one migration per app; additive only)

**`messaging.Conversation`**
- `disappear_after`: `CharField` choices `off` / `view` / `1h` / `24h` / `7d`, default `off`.
  New conversations take the starter's default timer.
- `a_delivered_upto`, `b_delivered_upto`: `PositiveBigIntegerField(default=0)`, next to the
  existing `*_read_upto`.

**Delivery and read status** works with these pointers, not per-message rows (cheap, and it
matches what already exists):
- **sent:** the message exists.
- **delivered:** the recipient's `delivered_upto` ≥ id. This is set when the recipient's client
  fetches it through poll or inbox.
- **read:** the recipient's `read_upto` ≥ id. This is set by `api_read`, which the client calls
  only while the conversation is open and the tab is visible.

**`messaging.Message`**
- `kind`: `text` (default) / `system` / `photo`.
- `timer`: the conversation's timer when the message was sent (for the badge and for "after
  viewing").
- `expires_at`: `DateTimeField(null=True, db_index=True)`.
  - **Time-based timers:** `created_at` plus the duration.
  - **"After viewing":** set when the recipient's read pointer passes the message, to now + 30 s.
  - **System messages and messages sent while the timer is Off:** null, so they never expire.
- **Photo fields:**
  - `photo`: `FileField` on a private storage, null.
  - `photo_opened_at`.
  - `photo_purged`: bool.
- **Managers:** the default manager becomes `VisibleMessageManager`, which always adds
  `Q(expires_at__isnull=True) | Q(expires_at__gt=now())`. `Message.all_objects` is the plain
  manager, used only by the cleanup job and the admin. Related managers
  (`conversation.messages`), the inbox subqueries, polling, export and the moderation snapshot
  all go through the default manager, so **expired content can't be served even if cleanup is
  late**. A test walks every endpoint to prove it.

**`messaging.MessagingPreference`** (it already has one row per user):
- `read_receipts`: default `True`.
- `show_online`: default `True`.
- `default_timer`: default `off`.
- `last_seen_at`: null. This is the presence heartbeat, updated at most once every 60 s per
  user through a cache throttle.

**`moderation.Report`**
- `photo`: a private `FileField`, null. When a photo message is reported, this holds an
  encrypted copy, so the report keeps it after the message expires. It is deleted together with
  the report after the existing 180-day retention.

No changes to `Block`, `ModerationLog`, `Restriction` or the accounts models.

---

## 2. Feature by feature

### 2.1 Delivery status and read receipts
- `serialize()` adds `status` (`sent` / `delivered` / `read`) to the sender's own messages only.
- **Receipts are reciprocal:** "read" is shown only if **both** people have read receipts on.
  Otherwise the sender sees at most "delivered". If you turn receipts off, you also stop seeing
  other people's.
- **Ticks:** one tick = sent, two ticks = delivered, two coloured ticks = read. Each has an
  `aria-label` ("Sent", "Delivered", "Read").
- **Typing indicator:** WebSocket only. The client sends `{"type":"typing"}` at most once every
  3 s, and the consumer checks membership, an accepted conversation and no block before
  forwarding it. It doesn't exist in polling mode. **Because production is WSGI, typing
  indicators won't appear in production until the ASGI + Redis switch in `DEPLOYMENT.md`**;
  everything else works over polling.

### 2.2 Disappearing messages
- **Changing the timer:** a timer menu in the chat header calls
  `POST api/c/<id>/timer/`. It requires a participant and an accepted conversation, is rate
  limited (10 per hour per user), and writes a system message: "X set disappearing messages
  to 24 hours" / "X turned off disappearing messages".
- **Scope:** the timer applies only to messages sent after the change.
- **Default for new chats:** set in the new Privacy panel.
- **Cleanup command:** `python manage.py purge_expired_messages` hard-deletes expired rows
  (`all_objects`) and their photo files.
  - It is idempotent, processes 500 rows per batch, logs counts only (never text, ids or
    usernames), and has a `--dry-run` option.
  - `purge_expired_data` (daily) calls it too.
- **Scheduling, with no paid service:**
  - **Locally:** Windows Task Scheduler (exact `schtasks` line in `DEPLOYMENT.md`).
  - **Production:** cron, or the host's scheduler where available. Render's cron jobs are a
    paid product, so I also propose a **lazy sweep**: messaging requests run the purge at most
    once a minute, behind a cache lock. Confidentiality doesn't depend on the job, because
    queries already hide expired rows; the job only frees storage.
- **Reports:** the existing encrypted snapshot keeps the reported content for the moderation
  retention (180 days after resolution) even after the message expires. The report dialog and
  the Privacy Policy will say so.
- **Honest limits, stated in the UI help, the Privacy Policy and the docs:**
  - Deleted data can remain in database backups until those backups rotate.
  - The other person may already have seen, copied or photographed a message.

### 2.3 View-once photos
- **Upload:** a photo button in the composer sends `POST api/c/<id>/photo/` (multipart).
  - JPEG, PNG or WebP, at most 5 MB, checked with Pillow (`verify`, a pixel limit), turned
    upright and re-encoded so EXIF is stripped. This reuses the checks from `blog/images.py`,
    moved into a small shared helper, with no behaviour change for the blog.
  - Then encrypted with the message Fernet keys and saved under a random name in
    **private storage**:
    - **Locally:** `PRIVATE_MEDIA_ROOT`, default `BASE_DIR/private_media`, which is outside
      `MEDIA_ROOT` and git-ignored.
    - **With `MEDIA_STORAGE=r2`:** the private bucket under the `msg-photos/` prefix.
  - The same send rules apply (blocks, requests, restrictions).
  - Rate limit: `MESSAGING_PHOTOS_PER_DAY` (default 20).
- **Opening:** `POST api/c/<id>/photo/<msg>/open/`.
  - Recipient only (404 for everyone else).
  - It refuses if the photo is expired or already opened (410), and runs atomically
    (`select_for_update`), so two clicks can't both succeed.
  - It sets `photo_opened_at`, returns the decrypted bytes with `Cache-Control: no-store`, and
    **deletes the file in the same request**.
  - The 10-second window is the viewer's countdown on the client. Deleting at once is stricter
    than deleting after 10 s and needs no timer on the server (see decision D3).
- **What the sender sees:** "Photo · view once", then "Photo · opened". The sender can't
  reopen it (D4).
- **Viewer:**
  - A full-screen dialog with a 10-second countdown and a watermark of the viewer's username
    and the time.
  - The photo blurs when the window loses focus or the tab is hidden.
  - No right-click, drag or download link. The image is drawn from a blob URL that is revoked
    when the dialog closes.
- **Reports:** reporting a photo that hasn't been opened copies the encrypted file into
  `Report.photo`. If it was already opened, the snapshot says "Photo (already opened and
  deleted)". The moderator view shows the photo only after "Show", like text, and the view is
  logged.

### 2.4 Screenshot and copy protection (deterrents only)
- No "screenshot taken" notifications: browsers can't detect screenshots.
- **Chats with a timer on:**
  - `user-select: none` on the bubbles.
  - A composer note: "Copying is turned off in this chat".
  - Screen readers still read everything; no `aria-hidden` on content.
- **Where this is stated plainly:** the Privacy panel, the docs and the Privacy Policy say these
  are deterrents only. Native protections (Android `FLAG_SECURE`, iOS capture notifications) go
  under Future.

### 2.5 Privacy controls
- `/messages/settings/` gains a **Privacy** panel:
  - Read receipts.
  - Show when I'm online.
  - Default disappearing timer.
  - The existing "Who can message me" and the blocked list.
- **Presence:**
  - Shown only to **accepted contacts**, and only if that person has "Show when I'm online"
    on.
  - "Online" means a heartbeat in the last 2 minutes. The heartbeat comes from poll and inbox
    requests, at most once a minute.
- **Blocks in either direction:** no presence, receipts, typing indicator or photos. Avatars
  already follow this rule.

### 2.6 Encryption wording
- No change to the encryption model: TLS in transit, Fernet at rest, and no end-to-end
  encryption (moderation needs to read reports).
- **New copy everywhere in messaging:** "Encrypted in transit and at rest. Moderators can review
  messages only if they're reported." The templates and JS of `messaging/` and `moderation/`
  will contain neither "end-to-end" nor "only you can see" (a test checks this). The course and
  game content that **teaches** what end-to-end encryption is stays untouched.
- **Search placeholders:** the conversation-list search becomes "Search by username…". The
  top-bar "Search users…" is a new element on the Messages page only (see D1).

### 2.7 UI (ported from the prototype once it's added)
- **Inbox:** avatar, online dot, preview ("Photo · view once" / "Photo · opened"), time, unread
  badge and timer label, Conversations / Requests tabs with a count, username search and New
  message.
- **Empty state:** hero image, "Pick a conversation", and four info cards with the corrected
  copy.
- **Chat:**
  - **Header:** presence, timer menu, Report and Block.
  - **Messages:** system messages, and bubbles with the time, a timer badge and ticks.
  - **Typing:** the indicator.
  - **Composer:** a 2000-character counter (`MESSAGING_MAX_LENGTH` is already 2000), Enter to
    send, Shift+Enter for a new line, and the photo button.
- **Layout:** side by side on desktop. On phones, opening a conversation fills the screen with a
  Back button.
- **Motion and safety:** `prefers-reduced-motion` is respected, and all text is inserted with
  `textContent` or template autoescaping.
- **Existing behaviour stays:**
  - **Requests:** accept and decline.
  - **Offensive-message warning:** the "edit or send anyway" check.
  - **Moderation notices:** warnings and restrictions shown to the member.
  - **Live updates:** the polling fallback.
  - **Account deletion:** the "Deleted user" handling.

### 2.8 Security (applies to all of the above)
- **Access:** participant-only lookups (404 otherwise) for messages, receipts, presence, photos,
  the timer and socket events.
- **POSTs:** CSRF on every one.
- **Validation:** input is validated, including the choices, image checks and sizes.
- **Rate limits:** send (existing), photos, timer changes and reports (existing).
- **Settings:** session and cookie settings are unchanged.

---

## 3. New environment variables (all optional, all with defaults)

| Variable | Default | Purpose |
|---|---|---|
| `PRIVATE_MEDIA_ROOT` | `BASE_DIR/private_media` | Local folder for encrypted view-once photos (not served by any URL). Ignored when `MEDIA_STORAGE=r2`. |
| `MESSAGING_PHOTOS_PER_DAY` | `20` | Photo uploads per user per day |
| `MESSAGING_TIMER_CHANGES_PER_HOUR` | `10` | Disappearing-timer changes per user per hour |

`MESSAGE_ENCRYPTION_KEYS` is reused for photos too. `rotate_message_keys` will also re-encrypt
stored photo files.

## 4. Background jobs

| Job | Schedule | What it does |
|---|---|---|
| `purge_expired_messages` (new) | every minute | Deletes expired message rows and their photo files, plus the files of photos opened more than 10 s ago that are still on disk (a safety net). Logs counts only. Idempotent. |
| `purge_expired_data` (existing) | daily | Also calls the above. |
| Lazy sweep (proposed, D2) | at most once a minute, in-app | The same purge, so production needs no paid scheduler |

## 5. Files to change

- **messaging:**
  - Changed: `models.py`, `services.py`, `policy.py`, `views.py`, `urls.py`, `consumers.py`,
    `events.py`, `crypto.py` (bytes helpers), `admin.py`, `signals.py` (delete photo files on
    account deletion), `templates/messaging/{inbox,settings,new}.html`, `static/messaging/*`.
  - New: `migrations/0002_*`, `photos.py`, `management/commands/purge_expired_messages.py`,
    and the tests `tests_v2.py` and `tests_photos.py`.
  - Updated command: `management/commands/rotate_message_keys.py` (also re-encrypts photos).
- **moderation:**
  - Changed: `models.py` (+ migration), `services.py` (photo snapshot, purge), the report view
    and template (photo after Show), and the report-dialog copy.
  - New: tests.
- **Shared helper:** `cyberquest/images.py`, the shared image checker. `blog/images.py` will use
  it with no behaviour change, and the blog tests stay as they are.
- **accounts:** `retention.py` (table rows: disappearing messages, view-once photos, presence,
  reported photos; the backups note), `privacy.py` (export: the new settings and the timers;
  photos are listed as metadata only, never their content).
- **pages:** `templates/pages/privacy.html` (disappearing messages, view-once photos, the honest
  limits, deterrents rather than protection).
- **Settings and docs:**
  - `cyberquest/settings.py` (the 3 variables above).
  - `.env.example`, `.gitignore` (`private_media/`).
  - `DEPLOYMENT.md`: the cleanup schedule (Windows Task Scheduler, cron), private storage, and
    why typing needs ASGI + Redis.
  - `README.md`.
  - `docs/features/PLAN.md`: audit log entry, Future section.
- **Assets:** `docs/messaging-design/` (yours: the prototype and `hero.png`), with the hero copied
  to `messaging/static/messaging/img/hero.png`.

**No new dependencies:** Pillow, cryptography and Channels are already installed.

## 6. Order of work (one commit per step, the full audit after each)

1. **Expiry foundation:** models, migration, the visible-only manager, the timer API and
   system messages, `purge_expired_messages`, and the expiry tests.
2. **Delivery, read receipts, presence and the Privacy panel:** status ticks, the typing
   indicator over the socket, and the reciprocal and block rules.
3. **View-once photos:** private storage, the opening flow, the viewer and moderation copies.
4. **Wording and deterrents:** copy-off in timed chats, the policy and retention text, and the
   export.
5. **UI port to the prototype:** desktop, 390 px, reduced motion. Browser checks with
   screenshots after each UI step.
6. **Docs:** `DEPLOYMENT.md`, `.env.example`, `PLAN.md`. Then merge into `develop` and stop.

## 7. Risks

- **Default-manager change:** any code that used `Message.objects` for bookkeeping now skips
  expired rows. I'll audit each use. Only cleanup and admin need `all_objects`. Report FKs read
  through `_base_manager`, which is unaffected.
- **Clock and expiry races:** a message can expire between being listed and being opened. The
  open endpoint re-checks expiry.
- **Typing in production:** none until ASGI + Redis. Delivery and read updates arrive at the
  polling interval, which is the same as today.
- **Photos and storage:** encrypting a 5 MB photo in memory is fine at this size. In R2 mode,
  deletion is an API call, so a failure is retried by the cleanup safety net.
- **"Delivered" accuracy:** "delivered" means the client fetched the message, not that it
  appeared on screen. That matches the requested definition.
- **Backups:** expired or opened data can survive in database and storage backups until they
  rotate. This is documented, not solved.
- **Screenshots:** they can't be prevented on the web. The UI must never suggest otherwise.

## 8. Decisions I need from you

- **D1. "Search users…" top bar.** The student layout has no top-bar search today.
  - **(a)** Add it on the Messages page only. It searches members to start a chat, using the
    existing `search_people`, which hides people who blocked you.
  - **(b)** Add it to the shared student layout on every page.
  - I recommend (a), because it keeps shared files untouched.
- **D2. Cleanup scheduling in production.** Render cron jobs are a paid product.
  - **(a)** In-app lazy sweep plus an optional host scheduler.
  - **(b)** A paid or external scheduler only.
  - I recommend (a). Expired content is hidden by the queries either way.
- **D3. View-once photos.** Delete the file on the server in the same request that serves it,
  with the 10 s countdown on the client (recommended, stricter). The alternative keeps it
  10 s and deletes it with the job.
- **D4. The sender's own photo.** The sender can't reopen it, as in Snapchat (recommended).
  The alternative lets the sender view it until the recipient opens it.
- **D5. Privacy Policy wording.** Keep one sentence saying "This is not end-to-end encryption"
  in the Privacy Policy only, so the legal text is unambiguous, and use your wording everywhere
  in the app UI (recommended). The alternative removes the phrase from the policy too.
- **D6. Reciprocal "online".** Should turning off "Show when I'm online" also hide other
  people's online status from you, like read receipts? I recommend yes, for consistency.
- **D7. The reference files.** Please add `docs/messaging-design/messages-prototype.dc.html` and
  `hero.png`. I can do steps 1–4 (the server side) before they arrive. Step 5 needs them.

---

## 9. Progress (steps 1–4, server side, on `feat/messaging-v2`)

Decisions applied: D1 Messages-page "Search users…"; D2 in-app sweep (cache lock, 200 rows, at
most once a minute, messaging/polling endpoints only) + optional host job + daily backstop;
D3 single conditional UPDATE decides the one open, which reads, deletes and serves the file;
D4 sender sees "Photo · sent" / "Photo · opened"; D5 the exact "not end-to-end" sentence only
in the Privacy Policy; D6 reciprocal "online". Each step: full suite, `makemigrations --check`,
`check --deploy`, browser check at desktop and 390 px.

- **Step 1:** disappearing messages, visible-only default manager, timer API + system notices,
  `purge_expired_messages`, sweep. Migration `messaging/0002`.
- **Step 2:** delivered/read markers and ticks (reciprocal, none across blocks), presence
  heartbeat, WebSocket-only typing, Privacy panel.
- **Step 3:** view-once photos (shared `cyberquest/images.py`, encrypted private storage,
  race-safe open, viewer deterrents, report copies). Migration `moderation/0003`.
- **Step 4:** wording ("Encrypted in transit and at rest…"), copy-off in timed chats, Privacy
  Policy, retention table, export, `.env.example`, `DEPLOYMENT.md` (cleanup schedule), launch
  checklist in `docs/features/PLAN.md`.

Open point for sign-off: an opened view-once photo can't be copied into a later report (it is
deleted when opened, per D3), so only photos reported before opening reach moderators.
Next: step 5, the UI port to `docs/messaging-design/messages-prototype.dc.html`.

## 10. Report copy and UI port

- **Report copy (approved rule):** an opened view-once photo stays reportable for 1 hour as an
  encrypted copy in `report_copy` (migration `messaging/0003`). No view, URL or admin page reads
  it; the recipient's report moves it into the report; the sweep and daily purge delete it
  after the hour. Disclosed in the viewer, report dialog, Privacy Policy and retention table.
- **Step 5, UI port** to `docs/messaging-design/messages-prototype.dc.html` (hero image as
  provided, served from `messaging/static/messaging/img/hero.png`): inbox list with online dot,
  preview, time, unread badge and timer label; Conversations/Requests tabs with count and
  inline Accept/Decline/Block; empty state with the 4 cards; chat header with presence, timer
  menu, Report and Block; system pills; bubbles with timer badge and SVG ticks (aria-labels);
  typing dots; composer with photo button, counter, Enter/Shift+Enter; full-screen viewer with
  tiled watermark and countdown ring. Night and day token sets, all text pairs AA. Phones:
  list, then a full-screen chat with Back. Reduced motion respected.
- **Copy deviation from the prototype (by D5):** the "Encrypted & stored safely" card and the
  in-chat banner use "Encrypted in transit and at rest. Moderators can review messages only if
  they're reported." instead of the prototype's "Not end-to-end…" wording.
