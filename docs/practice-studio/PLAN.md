# Practice Studio: implementation plan

Status: **signed off**; implementation in progress (see §7).

---

## 0. Decisions (signed off)

| # | Topic | Decision |
|---|---|---|
| D1 | Validation / stripping | `practice/graders.py` (`validate_content`, `validate_step`, `public_content`) is the **only** validation and answer-stripping logic. The studio calls it; no second copy. "Generate from Topic Kit" is a disabled card labelled **Coming soon** (no `practice/generation/` package exists). |
| D2 | Fields the player can't render | The player and the JSON format are unchanged. Forms show **only fields the player renders**. Hotspot layout is a dropdown: **Workflow diagram** (`flow`) / **Detail list** (`fields`). The per-clue "why", the artifact styles and the branch "channel" are dropped from the forms (see §9 Future player enhancements). |
| D3 | Incident time limit | Left out. The no-timers rule stands; `time_limit_sec` stays null. |
| D4 | Templates | Built from the two crypto design samples and "The urgent CEO request". Stored as versioned JSON files in `practice/studio/starter_templates/` (not in the database). A test asserts each passes `validate_content()`. |
| D5 | Staff area | Inside the Admin Command Center, using `ops.css`. Content Editor / Content Publisher users reach **only** Studio pages; every other Command Center view stays superuser-only. Tests: an editor gets 403 on non-Studio Command Center URLs, and the nav shows them only Studio. |
| D6 | Commits | Full suite on `fix/audit-phase2`, `git status` reviewed by folder, no secrets / `.env` / `db.sqlite3` / media. One baseline commit "chore: baseline practice engine and audit fixes" on `fix/audit-phase2`, then branch `feat/practice-studio` with one commit per phase. |
| D7 | Deploys overwriting edits | `Scenario.source` (`seed` / `studio`) plus `content_hash`. `convert_scenarios` and `load_scenarios`: create missing sessions; update a seed session only while `source="seed"`; **never** touch `source="studio"` or a session with published studio versions; log every skip; `--force` only with an explicit slug list. The first studio save sets `source="studio"`. Tests include "running the build twice changes nothing". |
| D8 | `meta` block | `content["meta"] = {badge, description}`. `public_content()` passes it through (it holds no answer keys; a test checks that). A test checks the player ignores unknown top-level keys. |
| D9 | Database | **MySQL** (8.0.11+) in production, SQLite locally and in tests, chosen by `DATABASE_URL`. Only portable `JSONField` use (no database-specific JSON lookups). JSON is compared and fingerprinted as canonical JSON, because MySQL's JSON type reorders keys. No deployment for now. |

## 1. Step types: the exact format the studio reads and writes

Taken from the 3 sample files, `conversion.py`, `graders.py` and `static/practice/js/steps/*.js`. Keys marked **answer** are stripped by `public_content` before reaching the browser (`correct, effects, secure, points, feedback, endings, explanations`).

| Type | Fields | Form (admin view) |
|---|---|---|
| `story` | `desc`, `intro`, `labels[]` (step names on the intro card), `end_expression` (Hana face: neutral, smile, talk, think, happy, surprised, wrong, correct) | Message (`intro`), short description (`desc`), Hana's mood dropdown with a live face. `labels` are **generated** from the step list. |
| `concept_cards` | `title`, `cards[{icon, title, back}]`, `tips{start, progress, done}` | Exactly 3 cards: title, explanation (`back`), icon picker (icons in `engine.js`'s icon set). Heading. Optional tips. |
| `hotspot` | `layout` (flow/fields), `title`, `banner?`, `select`, `items[{icon?, label, value}]`, **`correct`** [indexes], `context?[{title, rows[{label, value, flag}]}]`, `tips{…}`, **`feedback{good,bad}`** | Items: label, detail (`value`), icon, "This is a clue" checkbox. `correct` and `select` (the spec's "need") are **calculated** from the ticks. Layout dropdown: Workflow diagram / Detail list. Optional context panels (editable rows; required to round-trip converted scenarios). Good/bad feedback. |
| `configure` | `title`, `console_title`, `check_label`, `settings[{key, label, hint, options[], **secure**, **points[]**}]`, `threats[{label, settings[keys]}]`, `tips`, **`feedback`** | Rows: setting name, hint, threat name, 3 options weakest → strongest, radio for the secure one. `key` is generated. `points` default to `[0, 10, 30]` from the weakest → strongest order (the samples' scale), so no numbers are typed. Each row's threat becomes one `threats` entry. Sample threats covering 2 settings are kept on round-trip but can't be edited in the form. |
| `mcq` | `eyebrow?`, `title?`, `options[]`, **`correct`** (index or list), **`explanations?[{title, text}]`**, `tips`, **`feedback{good, bad}`** | Question, 3–4 options, radio (or checkboxes, "more than one right answer") for the correct one. "Explanation if right" = `feedback.good`; "if wrong" = `feedback.bad`. Optional explanation per option. |
| `triage` | `title`, `live_tag`, `alerts[{ini, bg, from, time, msg}]`, `levels[{label, desc, dot}]`, **`correct`**, `tips`, **`feedback`** | Alerts: from, time, message. `ini` and `bg` are **generated** (initials, palette). Severity radio over the fixed 4 levels (low / medium / high / critical, `conversion.SEVERITY`). Reason becomes the feedback text. |
| `order` | `title`, `items[{id, text}]` (stored **shuffled**; the player doesn't shuffle), **`correct`** [ids in order], `tips`, **`feedback`** | Steps entered **in the correct order**. The serializer creates ids, stores `correct` in that order and `items` in a stable shuffle (seeded by slug + step, so saving twice gives the same JSON). |
| `match` | `eyebrow`, `left_label`, `right_label`, `left[{id, text}]`, `right[{id, text}]` (stored shuffled), **`correct`** [[left, right]], `tips`, **`feedback`** | Problem → fix pairs. Ids are generated. The right column is shifted by one (as `conversion._match` does), so pairs never line up. |
| `branch` | `meter_labels?{sec, trust}`, `scenes[{title, time, tip, msgs[{ini, bg, from, addr, text}], choices[{text, **effects{sec, trust, kind, out}**}]}]`, **`endings{best, mid, bad: {tag, title, text, face}}`** | Exactly 3 scenes: scene heading (`title`, e.g. "Inbox"), time, tip, sender, address, message. Exactly 3 choices each: text, quality Good / Risky / Bad (`kind` good / meh / bad), outcome. `effects.sec` and `.trust` are **derived from quality**: Good +20/+10, Risky −10/0, Bad −30/−10 (the phish-01-choice scale). Plus the 3 endings. |
| *(debrief)* | `headline?`, `sub`, `learned[]` | The "Results screen" card. |

**Round-trip rule.** Every serializer is `from_json(step) → form initial data` and `to_json(cleaned_data) → step`. Generated or derived values (`labels`, `ini`/`bg`, `select`, `key`, `points`, effects) are recomputed identically. Any key the form doesn't cover (`tips.*`, multi-setting threats, `icon`, `source`) goes through a hidden `extra` blob. So **JSON → form → JSON gives the same value for every existing row**, which is what the round-trip tests assert.

Converted rows carry hand-tuned values that a derived rule wouldn't reproduce (e.g. `points`, triage colours). When a stored value differs from the derived one, the serializer keeps the stored value until the admin changes that field.

---

## 2. Data changes (phase 1)

`practice.Scenario`: add
- `status`: draft / published / archived (default `published`, so all 34 current rows stay live)
- `draft_content` (JSON, null): edits not yet published
- `draft_meta` (JSON, null): pending title, difficulty, minutes, XP, badge and description
- `created_by`, `updated_by` (FK user, null), `created_at`, `updated_at`
- `source`: `seed` (made by `convert_scenarios` / `load_scenarios`) or `studio` (first studio save switches it)
- `content_hash`: sha256 of the canonical JSON of the seed content last written, so the commands can tell "unchanged" without diffing

`content` stays **the published content**. It's the only thing students receive (through `public_content`) and the only thing graded. Editing a published row writes `draft_content`; publishing copies it into `content`, bumps `version`, and snapshots it.

New `ScenarioVersion`: scenario FK, `version`, `origin` (seed / studio), `content`, `meta`, `published_by`, `published_at`; unique per (scenario, version). Written by the seed commands whenever they write new content (origin seed) and by the studio on every publish (origin studio). Only studio snapshots stop the seed commands. **Restore** copies a version into `draft_content` (it still has to be published, and still goes through the checks).

**Grading during a publish.** `Attempt.state["version"]` is already recorded at start. Answers and completion grade against `ScenarioVersion(version=attempt version)` when it differs from the live one. That way a learner mid-attempt isn't graded against new answers.

New `Attempt.is_preview` (bool), with `Attempt.objects.real()` for learner-only queries. Preview runs are deleted after 7 days by `purge_expired_data` (listed in the Privacy Policy retention table). A preview attempt: awards **no XP**, writes **no** mirror `PracticeSession` (so no stats, DNA, history or badges), runs **no** badge check, and is hidden from history.

New `StudioAuditLog`: user, scenario (null), action (create / edit / duplicate / import / publish / unpublish / archive / restore), version, summary, at. Append-only; read-only in Django admin.

**Badge name and short description.** Stored in `content["meta"]` (`badge`, `description`) per D8. Ignored by the player and graders; passed through by `public_content()`.

**Permissions** (`Scenario.Meta.permissions`): `use_studio`, `publish_scenario` (covers publish, unpublish, archive and restore). A data migration creates the groups:
- **Content Editor**: `use_studio`, `add_scenario`, `change_scenario`
- **Content Publisher**: the editor permissions plus `publish_scenario`

Superusers have everything.

**Student-side filter.** `status="published"` is added to every student query of `Scenario`: the center catalog, `session_page`, `api_start` and the rotation in `start_practice`. Staff preview goes through the preview URL only.

---

## 3. URLs, views and forms

Under `/admin-dashboard/studio/` (namespace `studio`, module `practice/studio/`):

| URL | View | Permission |
|---|---|---|
| `studio/` | list: filters (topic, kind, status), search, quick actions | `use_studio` |
| `studio/new/` | start screen: 4 cards | `add_scenario` |
| `studio/new/duplicate/` | searchable picker, then POST creates the copy | `add_scenario` |
| `studio/new/template/<kind>/` | POST creates a draft from the template | `add_scenario` |
| `studio/new/import/` | upload `.json`, validate, create draft | `add_scenario` |
| `studio/<slug>/basics/` | wizard step 1 | `change_scenario` |
| `studio/<slug>/steps/` | wizard step 2 (all step cards) | `change_scenario` |
| `studio/<slug>/autosave/` | POST JSON every 30 s, writes `draft_content` | `change_scenario` |
| `studio/<slug>/preview/` | wizard step 3: iframe + desktop/mobile toggle | `use_studio` |
| `studio/<slug>/play/` | the **real** `session.html` against the draft, preview mode | `use_studio` |
| `studio/<slug>/check/` | wizard step 4: checklist + Publish | `use_studio` (publish button needs `publish_scenario`) |
| `studio/<slug>/publish/`, `unpublish/`, `archive/` | POST | `publish_scenario` |
| `studio/<slug>/versions/`, `versions/<n>/restore/` | history + restore | view: `use_studio`; restore: `publish_scenario` |
| `studio/<slug>/export/` | download `.json` | `use_studio` |

Every view is wrapped by a `studio_required(perm)` decorator: login → staff → perm, otherwise **403**. All writes are POST with CSRF. Autosave sends the CSRF header.

**Preview API.** The existing `api_start`, `api_answer` and `api_complete` take `{"preview": true}`. That's honoured only for staff with `use_studio`, and grades against `draft_content` if present.

**Forms.** One Django `Form` per step type (`practice/studio/forms.py`) plus formsets for repeated rows. Each field has a label, help text, `max_length` and a recommended max (`data-recommend`) for the counter, plus an example (`data-example`) for "Insert example". Server-side `clean()` produces the inline messages. All text is stored as plain text and rendered with Django or `textContent`, so it's escaped both ways.

**Serializers** (`practice/studio/serializers.py`): `StorySerializer`, `ConceptCardsSerializer` … `BranchSerializer`, `DebriefSerializer` and `SessionSerializer` (whole content ↔ list of step forms). There are no Django REST framework dependencies.

**Checks** (`practice/studio/checks.py`): runs `graders.validate_content` (reused, not copied) step by step and turns each failure into a plain-English line with a `#field-id` link. It adds studio-only rules that aren't format rules: no empty text, no example text left unchanged, 3 concept cards, 3×3 branch, unique title, topic chosen. **Publish is disabled until every line passes**, and the publish view re-runs the checks on the server.

---

## 4. Templates and JS

- `templates/practice/studio/`: `list.html`, `start.html`, `duplicate.html`, `wizard_base.html` (progress bar 1–4, Back/Next), `basics.html`, `steps.html` (one `<section>` per step from `_step_<type>.html` partials), `preview.html`, `check.html`, `versions.html`, `import.html`. All extend the Command Center `ops/base.html`.
- `static/practice/studio/studio.js` (vanilla, matching the repo):
  - character counters
  - Insert example
  - add/remove rows
  - drag-and-drop with keyboard fallback (Move up/down buttons): only optional steps move, and only within the order the flow allows
  - autosave every 30 s plus on Next, with a "Saved 12:04" status
  - `beforeunload` "unsaved changes" warning
  - confirm dialogs for delete and archive
  - preview width toggle (1280 / 768 / 390)
- `studio.css` on top of `ops.css`, readable at 1280 px and on a tablet.
- Links:
  - "Studio" in the Command Center sidebar and on the staff dashboard
  - "Practice Studio" via an override of `admin/index.html` (the Django admin has no sidebar app for this)
- The existing Command Center "Practice scenarios" page still lists the old `scenarios.py` data. It gets a link to the studio and is otherwise left alone.

---

## 5. Templates (start screen)

`practice/studio/templates/{simulation,incident,choice}.json`. These are copies of the two crypto samples and phish-01-choice with text replaced by clearly marked example text ("Example: …"). The checks fail on unchanged example text, so a template can't be published as-is.

Recipes match the spec:
- **Simulation:** story → concept_cards → hotspot → configure → match → results
- **Incident:** story → triage → hotspot → mcq → order → results
- **Choice:** story → branch (3×3) → results

The **template test** fills every field with its "Insert example" text and asserts `validate_content` passes.

---

## 6. Tests (all in `practice/tests_studio*.py`)

- Round-trip for each step type: for every step of every DB row plus the samples, `to_json(from_json(step)) == step`.
- Duplicate every existing scenario: a valid draft with a new slug, `status=draft` and identical content.
- Each template, filled with its examples, passes `validate_content` and the studio checks.
- Publish is blocked (400 + message) when checks fail and allowed when they pass. Publishing bumps `version` and writes a `ScenarioVersion`.
- Editing a published row leaves `content` (what students get) unchanged until publish.
- Restore brings back the exact earlier content (`==`).
- Permissions:
  - an editor gets 403 on publish, archive and restore
  - non-staff and anonymous users get 403 or a redirect on **every** studio URL (loop over the URLconf)
  - staff without a group get 403
- Preview: a full play-through with `preview=true` gives user XP unchanged, no `PracticeSession`, no badge, and the attempt flagged.
- The student API never returns answer keys, including for a freshly published studio scenario.
- Drafts are invisible to students (catalog, `/practice/<slug>/`, `api_start`).
- `convert_scenarios` / `load_scenarios`: create missing, update seed rows, never touch studio rows or rows with published versions, log skips, `--force` needs slugs, running twice changes nothing.
- Editor gets 403 on every non-Studio Command Center URL; the nav shows editors only Studio.
- `public_content()` keeps `meta` and unknown keys (phase 1). The player ignoring unknown keys needs a real DOM (the repo has no jsdom), so it is tested in phase 5 by running the real player in headless Edge against content with `meta` and an unknown key.
- Import: an invalid file is rejected with the reasons; a valid one becomes a draft.
- An audit row is written for create, edit, publish and restore.
- The existing 444 tests stay green.

---

## 7. Phases

0. Baseline commit on `fix/audit-phase2`, then branch `feat/practice-studio` (D6).
1. Models, migrations, permissions, groups, the audit log, preview flag, student-side status filter, `source` + `content_hash` and the convert/load rules (D7).
2. Serializers + round-trip tests.
3. List page + start screen (duplicate, template, import; kit card disabled).
4. Wizard steps 1–2 + all step forms, autosave, reorder.
5. Preview (real player, draft content, no XP or stats).
6. Checks, publish, versions, restore, audit.
7. `docs/practice-studio/ADMIN_GUIDE.md` (simple English, screenshot placeholders, 5-minute walkthrough), sidebar/dashboard links, polish, a screenshot pass at 1280 px and tablet width.

Tests run after every phase; one commit per phase on `feat/practice-studio`.

**Commit notes**
- The HANDOFF.md "MySQL" correction (D9) landed in the baseline commit `14daaf5`, not in the phase 1 commit `b26ffc3` whose message mentions it.
- Phase 1 fixes (review): canonical-JSON fingerprint test (database JSON types reorder keys); `ScenarioVersion.origin` (seed / studio) with a seed snapshot of every existing version (migration 0008) and on every seed write, so attempts started before a deploy grade on their own content and seed snapshots never block seed updates; wider preview isolation tests; preview runs purged after 7 days by `purge_expired_data`.

**Before first deploy: run the full suite against MySQL** (`DATABASE_URL=mysql://... python manage.py test`; see DEPLOYMENT.md section 6). Not done yet: there is no MySQL server here and no deployment is planned for now.

## 8. Definition of done (as I'll verify it)

As a Content Publisher, in the browser and without JSON:
1. Duplicate `crypto-…` (the DB Cryptography simulation).
2. Retarget it to another topic and rewrite its text.
3. Preview it in the real player at desktop and mobile width.
4. Pass every check and publish.
5. Then, as a student, it appears on that topic's card list and plays exactly like the other sessions.

## 9. Future player enhancements (not in this build)

Dropped from the studio forms because the player doesn't render them (D2). Each needs player and format work before it can be offered:

| Enhancement | Where | What it would need |
|---|---|---|
| Artifact styles for evidence (list, certificate, email, log, chat, settings page) | hotspot | New `artifact` key + one renderer per style in `steps/hotspot.js` and `session.css` |
| Per-clue "why" explanation | hotspot | New `why` per item, revealed after checking (answer key, so add to `ANSWER_KEYS`) |
| Branch scene channel (email, SMS, chat, call) with its own chrome | branch | New `channel` key + per-channel scene styling in `steps/branch.js` |
| Badge name shown in the player | results | Read `content.meta.badge` in `engine.js` instead of the topic-derived badge |
| Topic Kit generator | studio start screen | A `practice/generation/` package (kits per topic, assembler) that outputs content passing `validate_content` |
