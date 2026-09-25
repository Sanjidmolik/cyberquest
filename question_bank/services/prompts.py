"""Prompt builder for CyberQuest AI question generation."""

from __future__ import annotations

from typing import Any

SYSTEM_INSTRUCTION = """You are the CyberQuest Question Generation Engine.

Your job is to READ the supplied educational source content, identify distinct
learning materials/concepts inside it, then generate questions ONLY from those materials.

STRICT RULES:
1. Use ONLY the supplied source content as the factual knowledge base.
2. Do not use outside knowledge as factual evidence. Do not invent facts.
3. Do not browse the internet or use web search / grounding tools.
4. BEFORE writing each question: identify a relevant source_material (concept/section)
   from the supplied content, then write the question from that material.
5. Prefer covering DIFFERENT source materials across questions when the content supports it.
6. Every question MUST include:
   - difficulty (exactly as assigned in the CyberQuest blueprint)
   - source_material (short label for the concept used)
   - source_evidence (quote or close paraphrase from the source)
7. CyberQuest assigns difficulties. You MUST match each question_number to the assigned difficulty.
8. Difficulty does NOT unlock outside knowledge:
   - beginner / intermediate / advanced → ALL must be source-only.
9. DIFFICULTY DEFINITIONS (apply to BOTH mcq and simulation — type ≠ difficulty):
   - beginner: one basic concept OR recognize an obvious indicator / basic precaution.
   - intermediate: apply/distinguish concepts OR analyze multiple indicators in a scenario.
   - advanced: multi-concept reasoning OR complex incident response from the SOURCE.
   A simulation is NOT automatically advanced.
10. correct_answer must exactly match one of the options strings.
11. Return ONLY structured JSON. No markdown fences.
12. If you cannot produce a valid source-supported question for a slot without inventing,
    omit that slot rather than inventing. CyberQuest will repair missing slots.
13. Simulation scenarios must be derived from the source. Do not invent real company names,
    breach statistics, or policies absent from the source.
"""

DIFFICULTY_DEFINITIONS = """
DIFFICULTY DEFINITIONS (source-only for all levels).
question_type and difficulty are INDEPENDENT — a simulation is NOT automatically advanced.

For MCQ / knowledge questions:
- beginner: answer directly identifiable from one basic concept in the material
  (definition, term, type, basic precaution, stated fact).
- intermediate: understand/apply a concept (distinguish related ideas, choose an action,
  apply a precaution, connect two pieces of info from the content).
- advanced: reason across multiple concepts/materials from the source (analyze a situation,
  choose best action using several concepts, distinguish similar attack types using
  source characteristics). Advanced ≠ obscure or outside knowledge.

For SIMULATION questions (classify by reasoning/practical skill required):
- beginner simulation: recognize a suspicious email/link; identify an obvious phishing
  indicator; choose a basic security precaution.
- intermediate simulation: compare legitimate vs suspicious messages; analyze multiple
  indicators; select an appropriate action in a realistic situation.
- advanced simulation: analyze a more complex incident; combine multiple cybersecurity
  concepts from the source; choose an appropriate sequence of response actions;
  explain the reasoning. Must still be fully supported by the supplied source content.
"""


def _language_label(language: str) -> str:
    return {
        "en": "English",
        "bn": "বাংলা (Bangla)",
        "same_as_source": "Same as source content",
    }.get(language, language)


def _format_set_plans(set_plans: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for plan in set_plans:
        bp = plan.get("blueprint") or []
        slot_lines = ", ".join(
            f"Q{i}={diff}" for i, diff in enumerate(bp, start=1)
        )
        lines.append(
            f"- Set {plan['set_number']} ({plan['set_type']}, type={plan.get('question_type', 'mcq')}): "
            f"{slot_lines}"
        )
    return "\n".join(lines)


def build_generation_prompt(
    *,
    source_content: str,
    domain: str,
    language: str,
    difficulty: str,
    total_sets: int,
    normal_sets: int,
    simulation_sets: int,
    questions_per_set: int,
    set_plans: list[dict[str, Any]] | None = None,
) -> str:
    language_label = _language_label(language)
    plans = set_plans or []
    blueprint_block = _format_set_plans(plans) if plans else (
        f"- Sets 1..{normal_sets}: normal/mcq\n"
        f"- Sets {normal_sets + 1}..{total_sets}: simulation"
    )

    return f"""Generate a CyberQuest question bank from the SOURCE CONTENT below.

PROCESS (required):
1. Read the entire source content.
2. Identify distinct learning materials/concepts present in the content.
3. For each required question slot, select a relevant material (prefer unused ones).
4. Generate the question from that material only.
5. Match the assigned difficulty for that slot exactly.
6. Provide source_material + source_evidence for every question.

CONFIGURATION:
- DOMAIN / TOPIC: {domain}
- BANK DIFFICULTY MODE: {difficulty}
- OUTPUT LANGUAGE: {language_label}
- TOTAL SETS: {total_sets}
- NORMAL SETS: {normal_sets}
- SIMULATION SETS: {simulation_sets}
- QUESTIONS PER SET: {questions_per_set}
- EXPECTED TOTAL QUESTIONS: {total_sets * questions_per_set}

{DIFFICULTY_DEFINITIONS}

CYBERQUEST DIFFICULTY BLUEPRINT (mandatory — do not change distribution):
{blueprint_block}

OUTPUT JSON SHAPE:
{{
  "insufficient_source_content": false,
  "message": "",
  "sets": [
    {{
      "set_number": 1,
      "set_type": "normal",
      "title": "...",
      "description": "...",
      "questions": [
        {{
          "question_number": 1,
          "question_type": "mcq",
          "question": "...",
          "options": ["A", "B", "C", "D"],
          "correct_answer": "A",
          "explanation": "...",
          "difficulty": "beginner",
          "source_material": "Phishing definition",
          "source_evidence": "...",
          "source_excerpt": "...",
          "source_section": ""
        }}
      ]
    }}
  ]
}}

For simulation questions include a "scenario" object with fields appropriate to the domain
(phishing: sender/subject/body/url; network: log_entry/alert/ip_information; etc.).

SOURCE CONTENT (sole knowledge base):
---
{source_content}
---
"""


def build_repair_prompt(
    *,
    source_content: str,
    domain: str,
    language: str,
    missing_slots: list[dict[str, Any]],
    existing_questions: list[dict[str, Any]],
) -> str:
    """
    missing_slots items:
      {set_number, set_type, question_number, difficulty, question_type}
    existing_questions items:
      {set_number, question_number, question, difficulty, source_material}
    """
    language_label = _language_label(language)
    used_materials = sorted({
        (q.get("source_material") or q.get("source_section") or "").strip()
        for q in existing_questions
        if (q.get("source_material") or q.get("source_section") or "").strip()
    })
    existing_block = "\n".join(
        f"- Set {q.get('set_number')} Q{q.get('question_number')} "
        f"[{q.get('difficulty')}] material={q.get('source_material') or q.get('source_section') or '—'}: "
        f"{(q.get('question') or '')[:160]}"
        for q in existing_questions
    ) or "(none yet)"
    missing_block = "\n".join(
        f"- Set {s['set_number']} ({s['set_type']}) Q{s['question_number']}: "
        f"difficulty={s['difficulty']}, type={s.get('question_type', 'mcq')}"
        for s in missing_slots
    )
    materials_block = ", ".join(used_materials) if used_materials else "(none recorded)"

    return f"""Generate ONLY the missing CyberQuest replacement questions listed below.

PROCESS:
1. Read the SOURCE CONTENT.
2. Prefer source materials NOT already covered by existing questions.
3. Generate exactly the missing slots — match difficulty and type for each.
4. Avoid semantic duplicates of existing questions.
5. Provide source_material + source_evidence for each.

DOMAIN / TOPIC: {domain}
OUTPUT LANGUAGE: {language_label}

{DIFFICULTY_DEFINITIONS}

ALREADY USED SOURCE MATERIALS:
{materials_block}

EXISTING VALID QUESTIONS (do not duplicate):
{existing_block}

MISSING SLOTS TO GENERATE (return exactly these):
{missing_block}

OUTPUT JSON SHAPE:
{{
  "insufficient_source_content": false,
  "message": "",
  "replacements": [
    {{
      "set_number": 1,
      "question_number": 2,
      "question_type": "mcq",
      "question": "...",
      "options": ["A", "B", "C", "D"],
      "correct_answer": "A",
      "explanation": "...",
      "difficulty": "beginner",
      "source_material": "...",
      "source_evidence": "...",
      "source_excerpt": "...",
      "scenario": {{}}
    }}
  ]
}}

SOURCE CONTENT (sole knowledge base):
---
{source_content}
---
"""


def build_retry_correction_prompt(previous_error: str) -> str:
    return (
        "Your previous response failed validation.\n"
        f"Error: {previous_error}\n"
        "Return corrected structured JSON only. Obey all STRICT RULES. "
        "Match the CyberQuest difficulty blueprint exactly. "
        "Do not invent facts. Prefer omitting a slot over inventing."
    )
