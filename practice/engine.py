"""
Reusable simulation engine:
  briefing → investigate (progressive evidence) → decide → consequence → result

Same engine for all five domain consoles (and Incident mode).
"""

from django.utils import timezone

from .scenarios import get_scenario


def session_state(session) -> dict:
    state = session.state or {}
    return {
        "phase": state.get("phase", "briefing"),
        "revealed": list(state.get("revealed") or []),
        "last_reveal": state.get("last_reveal"),
        "decision_key": state.get("decision_key"),
        "consequence": state.get("consequence"),
    }


def _save_state(session, **updates):
    state = dict(session.state or {})
    state.update(updates)
    session.state = state


def open_workspace(session) -> dict:
    """Move from briefing into the interactive console."""
    if session.status != "in_progress":
        raise ValueError("This practice session is already completed.")
    state = session_state(session)
    if state["phase"] != "briefing":
        return {"phase": state["phase"]}
    _save_state(session, phase="investigate")
    session.save(update_fields=["state"])
    return {"phase": "investigate"}


def apply_action(session, action_key: str) -> dict:
    """
    Apply an investigation or decision action.
    Investigation reveals evidence progressively.
    Decision ends the session with consequences + scoring.
    """
    if session.status != "in_progress":
        raise ValueError("This practice session is already completed.")

    scenario = get_scenario(session.scenario_key)
    if not scenario:
        raise ValueError("Unknown scenario.")

    state = session_state(session)
    if state["phase"] == "briefing":
        raise ValueError("Open the console before investigating.")

    investigations = scenario.get("investigations", {})
    decisions = scenario.get("decisions", {})

    if action_key in investigations:
        return _investigate(session, scenario, action_key, investigations[action_key], state)
    if action_key in decisions:
        return _decide(session, scenario, action_key, decisions[action_key], state)

    raise ValueError("Invalid action.")


# Backwards-compatible name used by older tests/views
def apply_decision(session, action_key: str) -> dict:
    return apply_action(session, action_key)


def _investigate(session, scenario, action_key, action, state):
    revealed = list(state["revealed"])
    if action_key in revealed:
        raise ValueError("You already inspected that evidence.")

    score_delta = int(action.get("score", 0))
    reveal = action["reveal"]
    revealed.append(action_key)

    entry = {
        "type": "investigate",
        "action": action_key,
        "label": action["label"],
        "result": reveal["feedback"],
        "consequence": "Evidence added to locker.",
        "score_delta": score_delta,
        "evidence": True,
        "reveal": reveal,
        "at": timezone.now().isoformat(),
    }
    decisions_log = list(session.decisions or [])
    decisions_log.append(entry)
    session.decisions = decisions_log
    session.score = max(0, min(session.max_score, session.score + score_delta))
    _save_state(session, phase="investigate", revealed=revealed, last_reveal=reveal)
    session.save()
    return {
        "decision": entry,
        "ended": False,
        "score": session.score,
        "percent": session.percent,
        "reveal": reveal,
    }


def _decide(session, scenario, action_key, action, state):
    revealed = set(state["revealed"])
    required = list(scenario.get("required_evidence") or [])
    missing = [k for k in required if k not in revealed]
    penalty = int(scenario.get("missing_evidence_penalty", -10)) if missing else 0

    score_delta = int(action.get("score", 0)) + penalty
    quality = action.get("quality", "poor")

    consequence = {
        "title": action["consequence_title"],
        "body": action["consequence"],
        "response": action["response"],
        "quality": quality,
        "missing_evidence": missing,
        "missing_penalty": penalty,
        "decision_label": action["label"],
    }

    entry = {
        "type": "decide",
        "action": action_key,
        "label": action["label"],
        "result": action["consequence"],
        "consequence": action["consequence_title"],
        "score_delta": score_delta,
        "evidence": False,
        "quality": quality,
        "at": timezone.now().isoformat(),
    }
    decisions_log = list(session.decisions or [])
    decisions_log.append(entry)
    session.decisions = decisions_log
    session.score = max(0, min(session.max_score, session.score + score_delta))

    _finalize(session, scenario, action_key, action, revealed, required, consequence)
    _save_state(
        session,
        phase="completed",
        revealed=list(revealed),
        decision_key=action_key,
        consequence=consequence,
    )
    session.save()
    return {
        "decision": entry,
        "ended": True,
        "score": session.score,
        "percent": session.percent,
        "consequence": consequence,
    }


def _finalize(session, scenario, action_key, action, revealed, required, consequence):
    collected = [k for k in required if k in revealed]
    missing = [k for k in required if k not in revealed]
    quality = action.get("quality")

    strengths = []
    improvements = []

    if collected:
        labels = _labels_for(scenario, collected)
        strengths.append("Evidence collected: " + ", ".join(labels) + ".")
    if missing:
        labels = _labels_for(scenario, missing)
        improvements.append("Missed important evidence: " + ", ".join(labels) + ".")

    if quality == "correct":
        strengths.append(f"Decision: {action['label']} — appropriate security response.")
    elif quality == "unsafe":
        improvements.append(f"Decision '{action['label']}' increased risk in this scenario.")
    else:
        improvements.append(f"Decision '{action['label']}' was incomplete for this scenario.")

    if quality == "correct" and not missing:
        summary = "Strong simulation performance — investigated before responding."
    elif quality == "correct":
        summary = "Correct decision, but investigation was incomplete."
    elif quality == "unsafe":
        summary = "Unsafe decision — review evidence handling and response choice."
    else:
        summary = "Partial response — tighten investigation and containment choices."

    # Build narrative feedback from collected reveals
    feedback_bits = []
    for key in collected:
        inv = scenario["investigations"].get(key)
        if inv:
            feedback_bits.append(inv["reveal"]["feedback"])
    if feedback_bits and quality == "correct":
        strengths.append(feedback_bits[0])

    session.status = "completed"
    session.completed_at = timezone.now()
    session.result_summary = summary
    session.strengths = " ".join(strengths) if strengths else "Continue practicing investigation steps."
    session.improvements = (
        " ".join(improvements) if improvements else "Maintain thorough evidence collection."
    )


def _labels_for(scenario, keys):
    inv = scenario.get("investigations", {})
    return [inv[k]["label"] if k in inv else k for k in keys]


def build_console_context(session, scenario) -> dict:
    """Template context for the SOC-style console."""
    state = session_state(session)
    revealed_keys = state["revealed"]
    investigations = scenario.get("investigations", {})
    decisions = scenario.get("decisions", {})

    evidence_cards = []
    for key in revealed_keys:
        if key in investigations:
            evidence_cards.append({"key": key, **investigations[key]["reveal"], "label": investigations[key]["label"]})

    pending_investigations = [
        {"key": k, "label": v["label"]}
        for k, v in investigations.items()
        if k not in revealed_keys
    ]
    decision_actions = [{"key": k, "label": v["label"], "quality": v.get("quality")} for k, v in decisions.items()]

    required = scenario.get("required_evidence") or []
    collected_required = [k for k in required if k in revealed_keys]

    return {
        "phase": state["phase"],
        "revealed_keys": revealed_keys,
        "evidence_cards": evidence_cards,
        "last_reveal": state.get("last_reveal"),
        "pending_investigations": pending_investigations,
        "decision_actions": decision_actions,
        "evidence_count": len(collected_required),
        "evidence_needed": len(required),
        "required_labels": _labels_for(scenario, required),
        "collected_labels": _labels_for(scenario, collected_required),
        "log": session.decisions or [],
        "consequence": state.get("consequence"),
    }
