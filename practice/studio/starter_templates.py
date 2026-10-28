"""The three starter templates (practice/studio/starter_templates/*.json), versioned in the repo.

Each is a complete, valid session with the full recipe for its kind and realistic example
text the admin overwrites:
  simulation  story -> concept_cards -> hotspot -> configure -> match
  incident    story -> triage -> hotspot -> mcq -> order
  choice      story -> branch (3 scenes x 3 choices)
"""

import json
from pathlib import Path

TEMPLATE_DIR = Path(__file__).resolve().parent / "starter_templates"
KINDS = ("simulation", "incident", "choice")


def load_template(kind):
    if kind not in KINDS:
        raise KeyError(kind)
    return json.loads((TEMPLATE_DIR / f"{kind}.json").read_text(encoding="utf-8"))


def all_templates():
    return {kind: load_template(kind) for kind in KINDS}
