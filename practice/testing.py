"""Test helpers: answer any interactive step right or wrong from the server-side content,
and play a whole scenario through the JSON API."""

import json

from django.core.management import call_command
from django.urls import reverse

from .models import Scenario


def convert_all():
    """Courses plus every original scenario converted to the interactive engine."""
    from io import StringIO
    call_command("sync_curriculum", stdout=StringIO())
    call_command("convert_scenarios", stdout=StringIO())
    call_command("load_scenarios", stdout=StringIO())


def answer_for(step, right=True):
    kind = step["type"]
    if kind == "concept_cards":
        return {"flipped": len(step["cards"])}
    if kind == "hotspot":
        correct = list(step["correct"])
        if right:
            return correct
        others = [i for i in range(len(step["items"])) if i not in correct]
        return (others + correct)[:len(correct)]
    if kind == "configure":
        return {s["key"]: (s["secure"] if right else (s["secure"] + 1) % len(s["options"])) for s in step["settings"]}
    if kind in ("mcq", "triage"):
        correct = step["correct"] if isinstance(step["correct"], list) else [step["correct"]]
        size = len(step["options"] if kind == "mcq" else step["levels"])
        return correct[0] if right else next(i for i in range(size) if i not in correct)
    if kind == "order":
        return list(step["correct"]) if right else list(reversed(step["correct"]))
    if kind == "match":
        pairs = [list(p) for p in step["correct"]]
        if right:
            return pairs
        rights = [p[1] for p in pairs]
        return [[p[0], rights[(i + 1) % len(rights)]] for i, p in enumerate(pairs)]
    raise ValueError(kind)


def play_through(client, slug, right=True):
    """Start, answer every step and complete. Returns the completion JSON."""
    def post(name, body=None, *args):
        res = client.post(reverse(name, args=args), json.dumps(body or {}), content_type="application/json")
        assert res.status_code in (200, 201), (slug, name, res.status_code, res.content[:200])
        return res.json()

    attempt = post("practice:api_start", {"scenario": slug})["attempt_id"]
    steps = Scenario.objects.get(slug=slug).content["steps"]
    for index, step in enumerate(steps):
        if step["type"] == "story":
            continue
        if step["type"] == "branch":
            for scene_no, scene in enumerate(step["scenes"]):
                want = "good" if right else "bad"
                choice = next(i for i, c in enumerate(scene["choices"]) if c["effects"]["kind"] == want)
                post("practice:api_answer", {"step": index, "answer": {"scene": scene_no, "choice": choice}}, attempt)
            continue
        post("practice:api_answer", {"step": index, "answer": answer_for(step, right)}, attempt)
    return post("practice:api_complete", None, attempt)
