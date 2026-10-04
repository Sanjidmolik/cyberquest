"""Language target tests. Gemini is never called."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.test import TestCase

from question_bank.models import QuestionBank
from question_bank.services.difficulty_blueprint import build_set_plans
from question_bank.services.generator import generate_question_bank
from question_bank.services.language_check import classify_text, language_errors_for_question
from question_bank.services.prompts import (
    build_generation_prompt,
    build_repair_prompt,
    build_retry_correction_prompt,
)
from question_bank.services.validator import filter_payload_against_plans, merge_replacements
from question_bank.tests import RICH_SOURCE, _make_question

BANGLA_SOURCE = (
    "ফিশিং একটি সামাজিক প্রকৌশল আক্রমণ যা ব্যবহারকারীদের প্রতারিত করে। "
    "আক্রমণকারীরা জরুরি ইমেল পাঠায় এবং সন্দেহজনক লিংক যোগ করে। "
    "ব্যবহারকারীদের অপ্রত্যাশিত লিংকে ক্লিক করা উচিত নয়। "
) * 4

EVIDENCE = "ফিশিং একটি সামাজিক প্রকৌশল আক্রমণ যা ব্যবহারকারীদের প্রতারিত করে"


def _english_question(n=1, difficulty="beginner"):
    prompts = {
        1: "What does ফিশিং mean according to the source material?",
        2: "Why should a user avoid clicking an unexpected link from the source?",
    }
    q = _make_question(n, difficulty=difficulty, source_material="ফিশিং")
    q["source_evidence"] = EVIDENCE
    q["question"] = prompts.get(n, f"Which source precaution applies in situation {n}?")
    q["explanation"] = "The source says users should not click unexpected links."
    return q


def _hindi_question(n=1, difficulty="beginner"):
    q = _english_question(n, difficulty=difficulty)
    q["question"] = "फ़िशिंग क्या है और उपयोगकर्ता को क्या करना चाहिए?"
    q["explanation"] = "स्रोत के अनुसार अप्रत्याशित लिंक पर क्लिक नहीं करना चाहिए।"
    q["options"] = [
        "लिंक पर क्लिक करें",
        "पासवर्ड भेजें",
        "आधिकारिक साइट खोलें",
        "संदेश अनदेखा न करें",
    ]
    q["correct_answer"] = "आधिकारिक साइट खोलें"
    return q


def _bangla_question(n=1, difficulty="beginner"):
    q = _english_question(n, difficulty=difficulty)
    q["question"] = "উৎস অনুসারে ফিশিং কী এবং ব্যবহারকারীর কী করা উচিত?"
    q["explanation"] = "উৎস বলে অপ্রত্যাশিত লিংকে ক্লিক না করে অফিসিয়াল ওয়েবসাইট খুলতে।"
    q["options"] = [
        "লিংকে ক্লিক করুন",
        "পাসওয়ার্ড পাঠান",
        "অফিসিয়াল ওয়েবসাইট খুলুন",
        "বার্তা উপেক্ষা করুন",
    ]
    q["correct_answer"] = "অফিসিয়াল ওয়েবসাইট খুলুন"
    return q


def _plans():
    return build_set_plans(
        total_sets=1,
        normal_sets=1,
        simulation_sets=0,
        questions_per_set=2,
        difficulty_mode="beginner",
    )


class TargetLanguagePromptTests(TestCase):
    def test_english_target_policy_on_generation_and_repair(self):
        gen = build_generation_prompt(
            source_content=BANGLA_SOURCE,
            domain="phishing_simulator",
            language="en",
            target_language="en",
            source_language="bn",
            difficulty="mixed",
            total_sets=1,
            normal_sets=1,
            simulation_sets=0,
            questions_per_set=5,
        )
        repair = build_repair_prompt(
            source_content=BANGLA_SOURCE,
            domain="phishing_simulator",
            language="en",
            target_language="en",
            source_language="bn",
            missing_slots=[{
                "set_number": 1,
                "set_type": "normal",
                "question_number": 2,
                "difficulty": "beginner",
                "question_type": "mcq",
            }],
            existing_questions=[],
        )
        retry = build_retry_correction_prompt(
            "language mismatch",
            target_language="en",
            source_language="bn",
        )
        for text in (gen, repair, retry):
            self.assertIn("LANGUAGE POLICY", text)
            self.assertIn("requested output language is English", text)
            self.assertIn("Never generate Hindi", text)
            self.assertIn("TARGET LANGUAGE: English", text)

    def test_bangla_target_policy(self):
        gen = build_generation_prompt(
            source_content=RICH_SOURCE,
            domain="phishing_simulator",
            language="bn",
            target_language="bn",
            source_language="en",
            difficulty="mixed",
            total_sets=1,
            normal_sets=1,
            simulation_sets=0,
            questions_per_set=1,
        )
        self.assertIn("TARGET LANGUAGE: বাংলা (Bangla)", gen)
        self.assertIn("Never generate Hindi", gen)


class LanguageValidationTests(TestCase):
    def test_bangla_source_english_target_accepts_english(self):
        self.assertEqual(
            classify_text(_english_question()["question"], "en"),
            "ok",
        )
        payload = {
            "sets": [{
                "set_number": 1,
                "set_type": "normal",
                "title": "Set",
                "questions": [_english_question(1), _english_question(2)],
            }],
        }
        filtered = filter_payload_against_plans(
            payload,
            set_plans=_plans(),
            source_content=BANGLA_SOURCE,
            target_language="en",
        )
        self.assertEqual(len(filtered.accepted_questions), 2)
        self.assertEqual(filtered.missing_slots, [])

    def test_hindi_rejected_when_english_requested(self):
        errors = language_errors_for_question(
            _hindi_question(),
            target_language="en",
            tag="Set 1 Q1",
        )
        self.assertTrue(errors)
        self.assertTrue(any("mismatch" in e for e in errors))
        self.assertEqual(
            classify_text("Kya aapka password strong hai ya nahi for this account?", "en"),
            "mismatch",
        )
        payload = {
            "sets": [{
                "set_number": 1,
                "set_type": "normal",
                "questions": [_hindi_question(1), _english_question(2)],
            }],
        }
        filtered = filter_payload_against_plans(
            payload,
            set_plans=_plans(),
            source_content=BANGLA_SOURCE,
            target_language="en",
        )
        self.assertEqual(len(filtered.accepted_questions), 1)
        self.assertEqual(filtered.accepted_questions[0]["question_number"], 2)
        self.assertEqual(filtered.missing_slots[0]["question_number"], 1)
        self.assertTrue(any("mismatch" in e for e in filtered.rejected_errors))

    def test_bengali_term_and_acronym_not_rejected(self):
        text = "Which indicator shows a ফিশিং email when the SPF record fails?"
        self.assertEqual(classify_text(text, "en"), "ok")
        q = _english_question()
        q["question"] = text
        q["explanation"] = "The source describes phishing as a social engineering attack."
        errors = language_errors_for_question(q, target_language="en", tag="Set 1 Q1")
        self.assertEqual(errors, [])

    def test_simulation_feedback_must_match_target(self):
        q = _make_question(1, simulation=True, difficulty="beginner")
        q["source_evidence"] = (
            "Users should never click unexpected links. Instead, open the official website manually"
        )
        q["scenario"]["instructions"] = "আপনার কী করা উচিত তা সিদ্ধান্ত নিন।"
        q["scenario"]["feedback"] = "The safe action is to open the official website."
        en_errors = language_errors_for_question(q, target_language="en", tag="Set 1 Q1")
        self.assertTrue(any("instructions" in e for e in en_errors))

        q["scenario"]["instructions"] = "Decide which action protects the account."
        q["scenario"]["feedback"] = "The safe action is to open the official website."
        self.assertEqual(
            language_errors_for_question(q, target_language="en", tag="Set 1 Q1"),
            [],
        )

    def test_explicit_bangla_target_accepts_bangla_and_rejects_english(self):
        self.assertEqual(classify_text(_bangla_question()["question"], "bn"), "ok")
        plans = build_set_plans(
            total_sets=1, normal_sets=1, simulation_sets=0,
            questions_per_set=1, difficulty_mode="beginner",
        )
        accepted = filter_payload_against_plans(
            {"sets": [{"set_number": 1, "set_type": "normal", "questions": [_bangla_question()]}]},
            set_plans=plans,
            source_content=BANGLA_SOURCE,
            target_language="bn",
        )
        self.assertEqual(len(accepted.accepted_questions), 1)

        rejected = filter_payload_against_plans(
            {"sets": [{"set_number": 1, "set_type": "normal", "questions": [_english_question()]}]},
            set_plans=plans,
            source_content=BANGLA_SOURCE,
            target_language="bn",
        )
        self.assertEqual(rejected.accepted_questions, [])
        self.assertEqual(len(rejected.missing_slots), 1)

    def test_valid_question_kept_when_only_one_fails_language(self):
        plans = _plans()
        first = filter_payload_against_plans(
            {"sets": [{"set_number": 1, "set_type": "normal", "questions": [
                _english_question(1),
                _hindi_question(2),
            ]}]},
            set_plans=plans,
            source_content=BANGLA_SOURCE,
            target_language="en",
        )
        self.assertEqual(len(first.accepted_questions), 1)
        repaired = merge_replacements(
            first,
            [{**_english_question(2), "set_number": 1}],
            set_plans=plans,
            source_content=BANGLA_SOURCE,
            target_language="en",
        )
        self.assertEqual(len(repaired.accepted_questions), 2)
        self.assertEqual(repaired.missing_slots, [])


class GenerationLanguageWiringTests(TestCase):
    def test_english_selection_is_passed_to_initial_and_repair(self):
        bank = QuestionBank.objects.create(
            title="Lang",
            domain="phishing_simulator",
            source_content=BANGLA_SOURCE,
            source_language=QuestionBank.LANG_BN,
            output_language=QuestionBank.LANG_EN,
            difficulty=QuestionBank.DIFF_BEGINNER,
            total_sets=1,
            normal_sets=1,
            simulation_sets=0,
            questions_per_set=2,
        )
        self.assertEqual(bank.resolve_output_language(), "en")

        hindi_then_english = {
            "insufficient_source_content": False,
            "sets": [{
                "set_number": 1,
                "set_type": "normal",
                "title": "Set",
                "questions": [_english_question(1), _hindi_question(2)],
            }],
        }
        provider = MagicMock()
        provider.model = "gemini-test"
        provider.generate_question_bank.return_value = hindi_then_english
        provider.generate_replacements.return_value = {
            "insufficient_source_content": False,
            "replacements": [{**_english_question(2), "set_number": 1}],
        }
        with patch("question_bank.services.generator.get_ai_provider", return_value=provider):
            result = generate_question_bank(bank.pk)

        gen_kwargs = provider.generate_question_bank.call_args.kwargs
        repair_kwargs = provider.generate_replacements.call_args.kwargs
        self.assertEqual(gen_kwargs["target_language"], "en")
        self.assertEqual(repair_kwargs["target_language"], "en")
        self.assertEqual(repair_kwargs["source_language"], QuestionBank.LANG_BN)
        self.assertEqual(result.status, QuestionBank.STATUS_REVIEW)
        prompts = [q.prompt for q in result.question_sets.get().ordered_questions()]
        self.assertEqual(len(prompts), 2)
        self.assertTrue(all("फ़िशिंग" not in p for p in prompts))
