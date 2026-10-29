"""The Studio wizard's editor: what each step's form shows, and saving drafts safely.

- Forms are generated in the browser from SCHEMA (labels, help text, recommended lengths,
  examples). The data they edit is exactly what serializers.SessionSerializer.from_json gives,
  so saving merges into the stored step and keeps every key the forms don't show.
- Drafting is lenient: empty fields, unusual step orders and missing answers are allowed and
  saved. Only the structure is checked (types, sizes, step kinds, required steps). The full
  graders.validate_content() runs at publish.
- Optimistic locking: every save names the draft revision it started from. If someone else
  saved in between, nothing is written and the editor is told who and when.
- XP is not editable: every Studio session is worth the practice rule (50 XP).
- Autosave writes the draft only, with no audit entry; a manual save is audited.
"""

from django.db import transaction
from django.utils import timezone

from ..conversion import XP_REWARD
from ..graders import FLOWS, STEP_TYPES
from ..models import Scenario, StudioAuditLog
from .serializers import (
    LAYOUT_CHOICES, MOODS, QUALITY_CHOICES, SERIALIZERS, STEP_NAMES, MetaSerializer, SessionSerializer,
)
from .services import DIFFICULTIES, working_content

MAX_BODY_BYTES = 256 * 1024
MAX_TEXT = 4000
MAX_ITEMS = 60
MAX_DEPTH = 8
MAX_STEPS = 20
ICONS = ["shield", "lock", "key", "users", "user", "link", "building", "clock", "target", "warn", "check", "x"]
FACES = ["neutral", "smile", "think", "happy", "surprised", "wrong"]


class Conflict(Exception):
    def __init__(self, by, at):
        super().__init__("Someone else saved this session.")
        self.by, self.at = by, at


class EditorError(ValueError):
    """The submitted editor data can't be saved; the message says why in plain words."""


# ---------- form schema (sent to the browser) ----------

def text(key, label, help="", max=120, example="", required=False):
    return {"kind": "text", "key": key, "label": label, "help": help, "max": max, "example": example, "required": required}


def area(key, label, help="", max=400, example="", required=False, rows=3):
    return {**text(key, label, help, max, example, required), "kind": "textarea", "rows": rows}


def select(key, label, options, help=""):
    return {"kind": "select", "key": key, "label": label, "options": options, "help": help}


def flag(key, label, help=""):
    return {"kind": "bool", "key": key, "label": label, "help": help}


def group(key, label, fields, open=False):
    return {"kind": "group", "key": key, "label": label, "fields": fields, "open": open}


def rows(key, label, row, *, min=0, max=MAX_ITEMS, add="Add", new=None, help="", reorder=True):
    return {"kind": "rows", "key": key, "label": label, "row": row, "min": min, "max": max, "add": add,
            "new": new or {}, "help": help, "reorder": reorder}


def feedback():
    return group("feedback", "Feedback after checking", [
        group("good", "When the answer is right", [text("title", "Heading", max=60, example="Nice catch!"),
                                                   area("text", "Message", max=240,
                                                        example="You spotted the signs a real attacker would hope you miss.")], open=True),
        group("bad", "When the answer is wrong", [text("title", "Heading", max=60, example="Not quite"),
                                                  area("text", "Message", max=240,
                                                       example="Look again at the sender's address and the link.")], open=True),
    ], open=True)


def tips(keys):
    names = {"start": "When the step opens", "progress": "While working", "ready": "When ready to check",
             "good": "After a right answer", "bad": "After a wrong answer", "done": "When finished",
             "all_in": "When every alert has been read"}
    return group("tips", "What Hana says (optional)", [area(k, names[k], max=160, rows=2) for k in keys])


MOOD_OPTIONS = [[m, label] for m, label in zip(MOODS, ["😐 Neutral", "🙂 Smile", "💬 Talking", "🤔 Thinking",
                                                       "😄 Happy", "😮 Surprised", "✅ Correct", "😕 Wrong"])]
SEVERITY_FROM = "levels"

SCHEMA = {
    "story": [
        area("intro", "What Hana says to open the session", max=280, required=True,
             example="A colleague just forwarded a message that looks off. Let's work out what's going on before anyone clicks."),
        area("desc", "Short description under the title", max=200,
             example="Investigate a suspicious message and decide what to do."),
        select("mood", "Hana's mood on the briefing", MOOD_OPTIONS),
    ],
    "concept_cards": [
        text("title", "Heading", max=80, required=True, example="3 things to know before you start"),
        rows("cards", "Cards (exactly 3)", [
            select("icon", "Icon", [[i, i.title()] for i in ICONS]),
            text("title", "Card title", max=40, required=True, example="Check the sender"),
            area("back", "Explanation", max=220, required=True,
                 example="The display name can say anything. The address after @ tells you who really sent it."),
        ], min=3, max=3, add="Add card", new={"icon": "shield", "title": "", "back": ""}),
        tips(("start", "progress", "done")),
    ],
    "hotspot": [
        text("title", "Instruction", max=100, required=True, example="Which 3 details give it away?"),
        text("banner", "Banner above the items (optional)", max=100, example="Inbox · Payroll update"),
        select("layout", "Layout", [list(c) for c in LAYOUT_CHOICES]),
        rows("items", "Items to inspect", [
            text("label", "Label", max=40, required=True, example="SENDER"),
            text("value", "Detail", max=160, required=True, example="payroll@company-hr-support.co"),
            select("icon", "Icon (workflow layout)", [["", "None"]] + [[i, i.title()] for i in ICONS]),
            flag("clue", "This is a clue / weak spot"),
        ], min=2, max=12, add="Add item", new={"label": "", "value": "", "icon": "", "clue": False},
            help="Tick the items students must find. The number to find is worked out from your ticks."),
        rows("context", "Context panels shown beside the items (optional)", [
            text("title", "Panel title", max=60),
            rows("rows", "Rows", [text("label", "Label", max=40), text("value", "Value", max=160),
                                  flag("flag", "Highlight")], max=12, add="Add row",
                 new={"label": "", "value": "", "flag": False}),
        ], max=4, add="Add panel", new={"title": "", "rows": []}),
        group("labels", "Item badge words (optional)", [text("pick", "Selected", max=20), text("right", "Right", max=20),
                                                        text("wrong", "Wrong", max=20), text("missed", "Missed", max=20)]),
        tips(("start", "progress", "ready", "good", "bad")),
        feedback(),
    ],
    "configure": [
        text("title", "Instruction", max=100, required=True, example="Lock down the file share"),
        text("console_title", "Console title", max=60, example="Share settings"),
        text("check_label", "Check button text", max=30, example="Run attack"),
        rows("settings", "Settings", [
            text("label", "Setting name", max=40, required=True, example="Encryption"),
            text("hint", "Hint", max=80, example="How the file is locked"),
            text("threat", "Threat it defends against", max=60, example="Brute-force cracking"),
            {"kind": "choice", "key": "options", "secure_key": "secure", "label": "Options, weakest to strongest",
             "count": 3, "max": 40, "help": "Choose the secure option with the radio button."},
        ], min=1, max=6, add="Add setting",
            new={"label": "", "hint": "", "threat": "", "options": ["", "", ""], "secure": 2}),
        tips(("start", "progress", "good", "bad")),
        feedback(),
    ],
    "mcq": [
        text("eyebrow", "Small label above the question", max=40, example="DECIDE · ONE CHOICE"),
        area("question", "Question (Hana asks it)", max=200, required=True,
             example="The email asks you to log in within 10 minutes. What do you do first?"),
        rows("options", "Answers (3 or 4)", [
            text("text", "Answer", max=120, required=True, example="Open the site yourself, not through the link"),
            flag("correct", "This is a right answer"),
            text("explanation_title", "Explanation heading (optional)", max=60),
            area("explanation_text", "Explanation (optional)", max=200, rows=2),
        ], min=3, max=4, add="Add answer",
            new={"text": "", "correct": False, "explanation_title": "", "explanation_text": ""}),
        tips(("ready", "good", "bad")),
        feedback(),
    ],
    "triage": [
        text("title", "Instruction", max=100, required=True, example="Triage: how serious is this?"),
        text("live_tag", "Tag", max=40, example="LIVE · INCIDENT"),
        rows("alerts", "Alerts", [
            text("from", "From", max=60, required=True, example="IT Helpdesk"),
            text("time", "Time", max=20, example="09:14"),
            area("msg", "Message", max=240, required=True, rows=2,
                 example="Three staff report a login page asking for their password again."),
        ], min=1, max=6, add="Add alert", new={"from": "", "time": "", "msg": ""}),
        {"kind": "level", "key": "severity", "label": "Right severity", "options_from": SEVERITY_FROM,
         "help": "Choose the level students should pick."},
        tips(("start", "all_in", "ready", "good", "bad")),
        feedback(),
    ],
    "order": [
        text("title", "Instruction", max=100, required=True, example="Put the response in order"),
        rows("steps", "Steps, in the CORRECT order", [
            text("text", "Step", max=120, required=True, example="Disconnect the laptop from the network"),
        ], min=2, max=8, add="Add step", new={"text": ""},
            help="Enter them in the right order. Students see them shuffled."),
        tips(("start", "progress", "ready", "good", "bad")),
        feedback(),
    ],
    "match": [
        text("eyebrow", "Small label", max=40, example="RECAP · MATCH THE PAIRS"),
        text("left_label", "Left column heading", max=30, example="PROBLEM"),
        text("right_label", "Right column heading", max=30, example="FIX"),
        rows("pairs", "Pairs", [
            text("left", "Problem", max=100, required=True, example="Weak cipher"),
            text("right", "Matching fix", max=100, required=True, example="Use AES-256"),
        ], min=2, max=6, add="Add pair", new={"left": "", "right": "", "right_uid": None},
            help="Write each pair side by side. Students see the right column shuffled."),
        tips(("start", "progress", "ready", "good", "bad")),
        feedback(),
    ],
    "branch": [
        group("meter_labels", "Meter names (optional)", [text("sec", "First meter", max=20, example="Security"),
                                                          text("trust", "Second meter", max=20, example="Team trust")]),
        rows("scenes", "Scenes (exactly 3)", [
            text("title", "Scene heading", max=40, required=True, example="Inbox"),
            text("time", "Time", max=30, example="Monday · 09:12"),
            area("tip", "What Hana says", max=160, rows=2, example="An urgent email from the CEO. What do you do?"),
            rows("messages", "Message(s)", [
                text("from", "Sender", max=60, required=True, example="Daniel Ahmed (CEO)"),
                text("addr", "Address", max=80, example="ceo@cyberquest-corp.co"),
                area("text", "Message", max=300, required=True, rows=2,
                     example="Buy 5 gift cards and send me the codes within 10 minutes."),
            ], min=1, max=3, add="Add message", new={"from": "", "addr": "", "text": ""}),
            rows("choices", "Choices (exactly 3)", [
                text("text", "Choice", max=120, required=True, example="Call the CEO on their known number"),
                select("quality", "Quality", [list(c) for c in QUALITY_CHOICES]),
                area("outcome", "What happens next", max=200, rows=2, required=True,
                     example="The real CEO never sent it. You stopped a scam."),
            ], min=3, max=3, add="Add choice", new={"text": "", "quality": "meh", "outcome": ""}),
        ], min=3, max=3, add="Add scene",
            new={"title": "", "time": "", "tip": "", "messages": [], "choices": []}),
        group("endings", "Endings", [
            group(key, label, [text("tag", "Tag", max=30), text("title", "Heading", max=60, required=True),
                               area("text", "Text", max=240, rows=2, required=True),
                               select("face", "Hana's face", [[f, f.title()] for f in FACES])], open=True)
            for key, label in (("best", "Best ending"), ("mid", "Middle ending"), ("bad", "Bad ending"))
        ], open=True),
    ],
}
DEBRIEF_SCHEMA = [
    text("headline", "Results heading (optional)", max=60, example="Mission complete!"),
    area("sub", "One-line summary", max=200, example="You spotted the scam and stopped the payment."),
    {"kind": "strings", "key": "learned", "label": "What students practised", "max": 80, "max_items": 6,
     "example": "Check the sender's real address"},
]


def required_types(kind):
    """Steps that can't be removed or moved: the briefing always; the branch for choice sessions."""
    return {"story", "branch"} if kind == "choice" else {"story"}


def allowed_types(kind):
    return [t for t in FLOWS[kind] if t != "story"] + (["mcq"] if "mcq" not in FLOWS[kind] else [])


def editor_config(scenario):
    content = working_content(scenario)
    return {
        "kind": scenario.kind,
        "data": SessionSerializer.from_json(content),
        "schema": SCHEMA, "debrief_schema": DEBRIEF_SCHEMA,
        "names": STEP_NAMES,
        "required": sorted(required_types(scenario.kind)),
        "allowed": allowed_types(scenario.kind),
        "blanks": {t: SERIALIZERS[t].from_json(SERIALIZERS[t].blank()) for t in allowed_types(scenario.kind)},
        "revision": scenario.draft_revision,
    }


# ---------- lenient structure checks ----------

def _check_value(value, where, depth=0):
    if depth > MAX_DEPTH:
        raise EditorError(f"{where}: too deeply nested.")
    if value is None or isinstance(value, (bool, int, float)):
        return
    if isinstance(value, str):
        if len(value) > MAX_TEXT:
            raise EditorError(f"{where}: text is longer than {MAX_TEXT} characters.")
        return
    if isinstance(value, list):
        if len(value) > MAX_ITEMS:
            raise EditorError(f"{where}: too many items.")
        for item in value:
            _check_value(item, where, depth + 1)
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str) or len(key) > 40:
                raise EditorError(f"{where}: unexpected field.")
            _check_value(item, where, depth + 1)
        return
    raise EditorError(f"{where}: unexpected value.")


def check_session(kind, data, original):
    if not isinstance(data, dict) or not isinstance(data.get("steps"), list):
        raise EditorError("The steps are missing.")
    steps = data["steps"]
    if not steps or len(steps) > MAX_STEPS:
        raise EditorError(f"A session has 1 to {MAX_STEPS} steps.")
    old_types = {i: s["type"] for i, s in enumerate(original.get("steps") or [])}
    allowed = set(allowed_types(kind)) | {"story"}
    for number, step in enumerate(steps, start=1):
        if not isinstance(step, dict) or not isinstance(step.get("data"), dict):
            raise EditorError(f"Step {number} is damaged. Reload the page.")
        kind_of = step.get("type")
        if kind_of not in STEP_TYPES or kind_of not in allowed:
            raise EditorError(f"Step {number}: a {kind} session can't have that kind of step.")
        uid = step.get("uid")
        if uid is not None and (isinstance(uid, bool) or not isinstance(uid, int) or old_types.get(uid) != kind_of):
            raise EditorError(f"Step {number} doesn't match the saved session. Reload the page.")
        _check_value(step["data"], f"Step {number}")
    if steps[0]["type"] != "story":
        raise EditorError("The briefing must stay the first step.")
    for required in required_types(kind):
        if [s["type"] for s in steps].count(required) != 1:
            raise EditorError(f"The {STEP_NAMES[required].lower()} step can't be removed or duplicated.")
    for key in ("debrief", "meta"):
        if key in data and not isinstance(data[key], dict):
            raise EditorError("The results screen is damaged. Reload the page.")
        _check_value(data.get(key) or {}, "Results screen")


def check_basics(basics, topics):
    if not isinstance(basics, dict):
        raise EditorError("The basics are missing.")
    title = basics.get("title")
    if not isinstance(title, str) or len(title.strip()) > 160:
        raise EditorError("The title can be at most 160 characters.")
    if basics.get("difficulty") not in DIFFICULTIES:
        raise EditorError("Choose a difficulty.")
    minutes = basics.get("est_minutes")
    if isinstance(minutes, str) and minutes.strip().isdigit():
        minutes = int(minutes)
    if isinstance(minutes, bool) or not isinstance(minutes, int) or not 1 <= minutes <= 120:
        raise EditorError("Estimated minutes must be a whole number from 1 to 120.")
    topic = str(basics.get("topic") or "")
    if topic not in topics:
        raise EditorError("Choose a topic.")
    for key, limit in (("badge", 60), ("description", 200)):
        if not isinstance(basics.get(key, ""), str) or len(basics.get(key, "")) > limit:
            raise EditorError(f"The {key} can be at most {limit} characters.")
    return {"title": title.strip(), "difficulty": basics["difficulty"], "est_minutes": minutes, "topic": int(topic),
            "badge": basics.get("badge", "").strip(), "description": basics.get("description", "").strip()}


# ---------- reading and saving ----------

def working_meta(scenario):
    meta = scenario.draft_meta or {}
    content_meta = working_content(scenario).get("meta") or {}
    return {
        "title": meta.get("title", scenario.title),
        "difficulty": meta.get("difficulty", scenario.difficulty),
        "est_minutes": meta.get("est_minutes", scenario.est_minutes),
        "topic": meta.get("topic", scenario.topic_id),
        "badge": content_meta.get("badge", ""),
        "description": content_meta.get("description", ""),
    }


def save(scenario_pk, user, *, revision, basics=None, session=None, autosave=False):
    """Save the draft. Raises Conflict if someone saved since `revision`, EditorError if the data
    can't be saved. Students keep seeing the published content until publish."""
    from courses.models import Course
    with transaction.atomic():
        row = Scenario.objects.select_for_update().select_related("draft_saved_by").get(pk=scenario_pk)
        if revision != row.draft_revision:
            raise Conflict(row.draft_saved_by.username if row.draft_saved_by else "another editor", row.draft_saved_at)
        content = working_content(row)
        meta = dict(row.draft_meta or {})
        if session is not None:
            if isinstance(session, dict) and "meta" not in session:
                # The steps page doesn't edit badge/description (Basics does): keep the stored ones.
                session = {**session, "meta": MetaSerializer.from_json(content.get("meta"))}
            check_session(row.kind, session, content)
            try:
                content = SessionSerializer.to_json(session, content)
            except (KeyError, TypeError, ValueError, AttributeError, IndexError):
                raise EditorError("Part of a step couldn't be read. Reload the page and try again.")
        if basics is not None:
            topics = {str(pk) for pk in Course.objects.values_list("pk", flat=True)}
            clean = check_basics(basics, topics)
            meta.update({k: clean[k] for k in ("title", "difficulty", "est_minutes", "topic")})
            new_meta = MetaSerializer.to_json({"badge": clean["badge"], "description": clean["description"]},
                                              content.get("meta"))
            content = {**content, "meta": new_meta} if new_meta else {k: v for k, v in content.items() if k != "meta"}
        now = timezone.now()
        row.draft_content, row.draft_meta = content, meta
        row.draft_revision += 1
        row.draft_saved_by, row.draft_saved_at = user, now
        row.source, row.updated_by, row.xp_reward = Scenario.STUDIO, user, XP_REWARD
        if row.status == Scenario.DRAFT and meta:
            # Never published: the row's own fields are what the Studio list shows.
            row.title, row.difficulty, row.est_minutes = meta["title"] or row.title, meta["difficulty"], meta["est_minutes"]
            row.topic_id = meta["topic"]
        row.save()
        if not autosave:
            StudioAuditLog.objects.create(user=user, scenario=row, slug=row.slug, action="edit", version=row.version,
                                          summary=f"Saved draft (revision {row.draft_revision})")
    return row
