# CyberQuest — Practice Session Redesign: Implementation Handoff

Target stack: **Django + MySQL (production) / SQLite (local and tests)** (existing CQ repo; no Bootstrap, the app has its own stylesheets). No React.
Approach: one Django app `practice`, one session page, a small vanilla-JS step engine,
server-side grading. The files in `design/` are the visual reference (markup, CSS,
animations and interaction logic for every screen). They use a design-tool format
(`<x-dc>`, `{{holes}}`, `<sc-for>`, `<sc-if>`, `class Component extends DCLogic`).
Port the HTML/CSS as-is and rewrite the logic as plain JS. Do not copy the runtime.

## 1. Session types and flows

| kind | flow (design file) |
|---|---|
| simulation | Briefing → Learn → Investigation → Configure → Recap → Debrief → Rewards |
| incident | Briefing(mode=incident) → Triage → Evidence → Decision → Respond → Debrief(mode=incident) → Rewards |
| choice | Briefing(mode=choice) → Branch → Debrief(mode=choice) → Rewards |

The `IntroIncident`, `IntroChoice`, `ResultsIncident` and `ResultsChoice` files are only wrappers that pass `mode` to Briefing and Debrief.

## 2. Step-type library (one JS renderer + one Python grader each)

| type | design file | answer payload | graded by |
|---|---|---|---|
| story | Briefing | — | — |
| concept_cards | Learn | — (all flipped) | — |
| hotspot | Investigation, Evidence | `[indexes]` | exact set match |
| configure | Configure | `{setting: optionIndex}` | every setting == secure option |
| mcq | Decision | `index` | == correct |
| triage | Triage | `severity` | == correct |
| order | Respond | `[ids]` | exact order |
| match | Recap | `[[l, r], ...]` | all pairs correct |
| branch | Branch | `choiceIndex` per scene | returns effects + next scene; ending rule on server |
| results / rewards | Debrief, Rewards | — | computed on complete |

Shell per kind: **incident** adds `IncidentClock` (server `started_at` + `time_limit`),
**choice** adds Security/Trust meters, and no hearts.

## 3. Django app

```
practice/
  models.py      Scenario, Attempt, StepAnswer
  graders.py     GRADERS = {"hotspot": ..., "mcq": ..., ...}
  views.py       session_page, api_start, api_answer, api_complete
  urls.py
  management/commands/load_scenarios.py   # loads practice/scenarios/*.json
  scenarios/crypto-01-simulation.json, crypto-04-incident.json, phish-01-choice.json
  templates/practice/session.html          # shell: top bar, stage, footer/sheet
  templates/practice/_hana.html            # Hana SVG (from any design file)
static/practice/css/session.css            # tokens + btn3d/opt/sheet/Hana keyframes
static/practice/js/engine.js               # loads content, runs steps, calls API
static/practice/js/steps/*.js              # one renderer per step type
static/practice/js/hana.js                 # setExpression(el, name)
```

### Models (portable JSONField: MySQL in production, SQLite in tests)
```python
class Scenario(models.Model):
    KIND = [("simulation","Simulation"),("incident","Incident"),("choice","Choice")]
    slug = models.SlugField(unique=True)
    topic = models.ForeignKey("courses.Module", on_delete=models.CASCADE)  # adapt to CQ's existing model
    kind = models.CharField(max_length=12, choices=KIND)
    title = models.CharField(max_length=160)
    difficulty = models.CharField(max_length=12)
    est_minutes = models.PositiveSmallIntegerField()
    time_limit_sec = models.PositiveIntegerField(null=True, blank=True)  # incident only
    xp_reward = models.PositiveIntegerField()
    content = models.JSONField()          # steps incl. answers; NEVER sent raw
    version = models.PositiveIntegerField(default=1)

class Attempt(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    scenario = models.ForeignKey(Scenario, on_delete=models.CASCADE)
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    hearts = models.PositiveSmallIntegerField(default=3)
    score = models.IntegerField(default=0)
    state = models.JSONField(default=dict)   # branch meters, current scene, etc.
    outcome = models.CharField(max_length=20, blank=True)

class StepAnswer(models.Model):
    attempt = models.ForeignKey(Attempt, on_delete=models.CASCADE, related_name="answers")
    step_index = models.PositiveSmallIntegerField()
    answer = models.JSONField()
    correct = models.BooleanField(null=True)
    time_ms = models.PositiveIntegerField(default=0)
    confidence = models.CharField(max_length=12, blank=True)
```

### API (JSON, CSRF via `X-CSRFToken` header, `@login_required`)
- `POST /practice/api/attempts/` `{scenario}` → `{attempt_id, content}`, where `content` has all
  `correct` / `effects` / `secure` keys **stripped** (security platform: no answers in DevTools)
- `POST /practice/api/attempts/<id>/answer/` `{step, answer, time_ms}` → `{correct, title, text, hearts}`
  (branch: `{effects, outcome_text, next_scene}`)
- `POST /practice/api/attempts/<id>/complete/` → `{xp, accuracy, time, badges, competency}`
  This is where you call CQ's **existing XP/badge/leaderboard functions**.
- `GET /practice/<slug>/` → renders `session.html` with the scenario slug and kind.

## 4. Front-end rules
- Scope everything under `.cq-session` so Bootstrap styles don't leak in.
  Don't use Bootstrap `.btn` inside the session; use `.btn3d`.
- Fonts: Nunito 600–900 (Google Fonts). Colours: brand `#7C4DFF` / shadow `#5B2FE0`,
  ink `#1F1440`, muted `#5B5277`, line `#E5DEFF`, good `#0B8A5F`/`#DDF7EC`,
  bad `#D9480F`/`#FFE9DC`, XP `#FFB020`.
- Flow per step: render → user interacts → **Check** posts the answer → feedback sheet slides up →
  **Continue** goes to the next step (no page reloads).
- Hana: one inline SVG; `hana.js` sets the class (`hana smile|talk|think|correct|wrong|happy|surprised`)
  and swaps the `d` of brows and mouth (values are in `EXP` inside any design file's script).
- Keep the `@media (prefers-reduced-motion: reduce)` block.

## 5. Build order (one commit each)
1. Models + migrations + `load_scenarios` with the 3 sample scenarios
2. `session.html` shell + `session.css` + Hana partial (static Intro screen working)
3. engine.js + API start/answer/complete + graders
4. Step renderers: mcq → hotspot → match → concept_cards → configure → triage → order → branch
5. Results/Rewards wired to existing XP + badges; Practice Center links to `/practice/<slug>/`
6. Tests: one grader test per step type, plus "content sent to client has no answers"
