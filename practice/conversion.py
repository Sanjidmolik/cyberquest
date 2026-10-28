"""Convert the original practice scenarios (practice/scenarios.py and friends) into the
interactive step format of HANDOFF.md, using only their own titles, briefings, evidence
and decisions. Used by `manage.py convert_scenarios`.

Mapping, per step of the target flow:
  story          ← briefing summary + objective
  concept_cards  ← the scenario's key takeaways (left out when it has none)
  triage         ← briefing as alerts, graded against the scenario's own severity (incidents)
  hotspot        ← the workspace (email, alert, panels) as context, then every investigation and
                   what it reveals; correct = the required evidence
  configure      ← no settings exist in the old content, so an mcq of the old decisions instead
  mcq            ← the old decisions; correct = the decision(s) rated "correct", each option
                   explained by its own consequence
  match          ← required evidence ↔ what it showed (simulations, as the recap)
  order          ← no ordered steps exist in the old content, so it is left out
"""

# Which course each original practice topic belongs to (Course.code).
COURSE_BY_DOMAIN = {
    "safety": "CQ-SAFETY", "phishing": "MOD-01", "password": "MOD-02", "malware": "CQ-MALWARE",
    "network": "MOD-03", "device": "CQ-DEVICE", "privacy": "CQ-PRIVACY", "response": "CQ-RESPONSE",
    "cryptography": "MOD-04", "steganography": "MOD-05", "osint": "MOD-06",
}
DOMAIN_BY_COURSE = {code: domain for domain, code in COURSE_BY_DOMAIN.items()}
MINUTES = {"beginner": 12, "intermediate": 15, "advanced": 18}
XP_REWARD = 50  # the existing practice XP rule
# The severity scale the old scenarios already use; descriptions are the scale's meaning.
SEVERITY = [
    ("LOW", "Low", "Little or no impact", "#3DD9A4"),
    ("MEDIUM", "Medium", "Limited impact, act soon", "#FFD23F"),
    ("HIGH", "High", "Real harm likely if not handled now", "#FF8A3D"),
    ("CRITICAL", "Critical", "Serious harm already happening", "#D9480F"),
]
STEP_LABEL = {"concept_cards": "Learn", "triage": "Triage", "hotspot": "Investigate", "mcq": "Decide", "match": "Recap"}
ALERT_COLOURS = ["#3F55C9", "#7C4DFF", "#0B8A5F", "#D9480F"]


def slug_for(key):
    return key.replace("_", "-")


def _initials(text):
    words = [w for w in str(text).replace("(", " ").split() if w[:1].isalnum()]
    return ("".join(w[0] for w in words[:2]) or "?").upper()


def _fields_text(reveal):
    return " · ".join(f"{f['label']}: {f['value']}" for f in reveal.get("fields") or [])


def _story(old, steps):
    briefing = old.get("briefing") or {}
    return {
        "type": "story",
        "desc": old.get("objective") or briefing.get("summary", ""),
        "intro": briefing.get("summary") or old.get("objective", ""),
        "labels": [STEP_LABEL[s["type"]] for s in steps],
        "end_expression": "think" if old.get("activity_type") == "incident" else "smile",
    }


def _concept_cards(old):
    takeaways = old.get("takeaways") or []
    if not takeaways:
        return None
    icons = ["shield", "lock", "key", "users", "link"]
    return {
        "type": "concept_cards",
        "title": f"{len(takeaways)} things to know before you start",
        "cards": [
            {"icon": icons[i % len(icons)], "title": f"Key idea {i + 1}", "back": text}
            for i, text in enumerate(takeaways)
        ],
    }


def _triage(old):
    severity = (old.get("severity") or "").upper()
    keys = [row[0] for row in SEVERITY]
    if severity not in keys:
        return None
    briefing = old.get("briefing") or {}
    alerts = []
    if briefing.get("summary"):
        sender = briefing.get("employee") or old.get("environment") or "Report"
        if briefing.get("department"):
            sender = f"{sender} · {briefing['department']}"
        alerts.append({"from": sender, "time": briefing.get("time", ""), "msg": briefing["summary"]})
    if briefing.get("subject"):
        alerts.append({"from": old.get("environment") or "Alert", "time": old.get("incident_code", ""), "msg": briefing["subject"]})
    if not alerts:
        return None
    for i, alert in enumerate(alerts):
        alert["ini"] = _initials(alert["from"])
        alert["bg"] = ALERT_COLOURS[i % len(ALERT_COLOURS)]
    label = SEVERITY[keys.index(severity)][1]
    return {
        "type": "triage",
        "title": "Triage: how serious is this?",
        "live_tag": " · ".join(x for x in (old.get("incident_code"), "INCIDENT") if x),
        "alerts": alerts,
        "levels": [{"label": l, "desc": d, "dot": c} for _, l, d, c in SEVERITY],
        "correct": keys.index(severity),
        "feedback": {
            "good": {"title": f"Good call: {label}", "text": old.get("objective", "")},
            "bad": {"title": f"Not quite: this one is {label}", "text": old.get("objective", "")},
        },
    }


_FIELD_NAMES = {"from_display": "From", "to": "To", "link_display": "Link", "body": "Message"}


def _context(old):
    """The scenario's workspace (email, alert, panels…) as titled rows, shown with the evidence."""
    workspace = old.get("workspace") or {}
    panels = []
    for panel in workspace.get("panels") or []:
        kind = panel.get("kind")
        if kind == "table":
            head = panel.get("head") or []
            flagged = set(panel.get("flagged") or [])
            rows = [{"label": str(r[0]), "value": " · ".join(f"{h}: {c}" for h, c in zip(head[1:], r[1:])) or str(r[0]),
                     "flag": i in flagged} for i, r in enumerate(panel.get("rows") or [])]
        elif kind == "messages":
            rows = [{"label": m.get("from", ""), "value": m.get("text", ""), "flag": bool(m.get("flag"))} for m in panel.get("items") or []]
        else:
            rows = [{"label": r.get("label", ""), "value": r.get("value", ""), "flag": bool(r.get("flag"))} for r in panel.get("rows") or []]
        if rows:
            panels.append({"title": panel.get("title", ""), "rows": rows})
    if not panels:
        rows = [{"label": _FIELD_NAMES.get(k, k.replace("_", " ").capitalize()), "value": str(v), "flag": False}
                for k, v in workspace.items() if isinstance(v, (str, int, float)) and str(v).strip()]
        if rows:
            panels.append({"title": old.get("environment") or "Workspace", "rows": rows})
    return panels


def _hotspot(old, incident):
    inv = old.get("investigations") or {}
    keys = list(inv)
    required = [k for k in old.get("required_evidence") or [] if k in inv]
    if not keys or not required:
        return None
    labels = ", ".join(inv[k]["label"] for k in required)
    notes = " ".join(inv[k]["reveal"].get("feedback", "") for k in required).strip()
    workspace = old.get("workspace") or {}
    banner = " · ".join(x for x in (old.get("environment"), workspace.get("subject") or (old.get("briefing") or {}).get("subject")) if x)
    step = {
        "type": "hotspot",
        "layout": "fields",
        "title": f"Which {len(required)} findings matter most here?",
        "banner": banner,
        "select": len(required),
        "context": _context(old),
        "items": [{"label": inv[k]["label"].upper(), "value": _fields_text(inv[k]["reveal"]) or inv[k]["reveal"].get("title", "")} for k in keys],
        "labels": {"pick": "Selected", "right": "Key evidence", "wrong": "Not key", "missed": "Missed"},
        "correct": [keys.index(k) for k in required],
        "feedback": {
            "good": {"title": "Key evidence found", "text": notes},
            "bad": {"title": "Not quite", "text": f"The key evidence was {labels}. {notes}".strip()},
        },
    }
    if old.get("hint"):
        step["tips"] = {"start": old["hint"]}
    return step


def _mcq(old):
    decisions = list((old.get("decisions") or {}).values())
    correct = [i for i, d in enumerate(decisions) if d.get("quality") == "correct"]
    if not decisions or not correct:
        return None
    best = decisions[correct[0]]
    return {
        "type": "mcq",
        "eyebrow": "DECIDE · ONE CHOICE",
        "options": [d["label"] for d in decisions],
        "correct": correct[0] if len(correct) == 1 else correct,
        "explanations": [{"title": d.get("consequence_title", ""), "text": d.get("consequence", "")} for d in decisions],
        "tips": {"start": old.get("objective", "")},
        "feedback": {
            "good": {"title": best.get("consequence_title", "Correct!"), "text": best.get("consequence", "")},
            "bad": {"title": "Not quite", "text": f"Best response: {best['label']}. {best.get('consequence', '')}".strip()},
        },
    }


def _match(old):
    inv = old.get("investigations") or {}
    required = [k for k in old.get("required_evidence") or [] if k in inv and inv[k]["reveal"].get("feedback")]
    if len(required) < 2:
        return None
    left = [{"id": k, "text": inv[k]["label"]} for k in required]
    right = [{"id": f"{k}-note", "text": inv[k]["reveal"]["feedback"]} for k in required]
    right = right[1:] + right[:1]  # a fixed shift, so the answers never line up and output stays stable
    return {
        "type": "match",
        "eyebrow": "RECAP · MATCH THE PAIRS",
        "left_label": "CHECK",
        "right_label": "WHAT IT SHOWED",
        "left": left,
        "right": right,
        "correct": [[k, f"{k}-note"] for k in required],
        "feedback": {
            "good": {"title": "Perfect match!", "text": "You know what each check revealed."},
            "bad": {"title": "Not quite", "text": " ".join(f"{inv[k]['label']}: {inv[k]['reveal']['feedback']}" for k in required)},
        },
    }


def convert(old):
    """One original scenario dict → the fields of a Scenario row (content included)."""
    kind = "incident" if old.get("activity_type") == "incident" else "simulation"
    hotspot = _hotspot(old, kind == "incident")
    decide = _mcq(old)
    if kind == "simulation":
        steps = [_concept_cards(old), hotspot, decide, _match(old)]
    else:
        steps = [_triage(old), hotspot, decide]
    steps = [s for s in steps if s]
    inv = old.get("investigations") or {}
    learned = [inv[k]["label"] for k in old.get("required_evidence") or [] if k in inv]
    content = {
        "source": {"key": old["key"], "domain": old["domain"]},
        "steps": [_story(old, steps)] + steps,
        "debrief": {"sub": old.get("objective", ""), "learned": learned},
    }
    difficulty = old.get("difficulty") or "beginner"
    return {
        "slug": slug_for(old["key"]),
        "topic": COURSE_BY_DOMAIN[old["domain"]],
        "kind": kind,
        "title": old["title"],
        "difficulty": difficulty,
        "est_minutes": MINUTES.get(difficulty, 15),
        "time_limit_sec": None,
        "xp_reward": XP_REWARD,
        "content": content,
    }
