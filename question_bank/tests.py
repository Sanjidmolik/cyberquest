"""Tests for the AI Question Bank system (provider mocked — no live Gemini calls)."""

from __future__ import annotations

import json
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from certificates.eligibility import is_eligible_for_certificate
from games.models import GameAttempt, Question, QuestionSet
from games.question_sets import pick_set_for_user, usable_sets
from question_bank.models import QuestionBank
from question_bank.services.difficulty_blueprint import (
    create_difficulty_blueprint,
    build_set_plans,
)
from question_bank.services.duplicate_detector import find_duplicates, normalize_question_text
from question_bank.services.generator import generate_question_bank
from question_bank.services.providers.gemini import GeminiProviderError, GeminiQuestionProvider
from question_bank.services.source_validator import estimate_source_capacity
from question_bank.services.validator import (
    filter_payload_against_plans,
    merge_replacements,
    validate_bank_configuration,
    validate_generation_payload,
)

User = get_user_model()


RICH_SOURCE = (
    "Phishing is a social engineering attack that tricks users into revealing sensitive information "
    "such as passwords or banking details. Attackers often send urgent emails that impersonate trusted "
    "organizations and include suspicious links. Users should never click unexpected links. Instead, "
    "open the official website manually by typing the known address. Phishing messages may contain "
    "generic greetings, spelling mistakes, mismatched sender domains, and requests for credentials. "
    "A legitimate security team will not ask for your password by email. Attachment-based phishing "
    "may deliver malware. Reporting suspicious messages to the security team helps protect others. "
    "Multi-factor authentication reduces damage when credentials are stolen. Hovering over links can "
    "reveal the real destination URL before clicking. Always verify the sender domain carefully."
) * 3


def _make_question(
    n: int,
    *,
    qtype: str = "mcq",
    simulation: bool = False,
    prompt: str | None = None,
    difficulty: str = "beginner",
    source_material: str = "Phishing definition",
) -> dict:
    prompts = [
        "According to the source, what is phishing?",
        "Which sender behavior is described as a phishing warning sign?",
        "What should a user do instead of clicking an unexpected email link?",
        "Why does the material say MFA helps after credential theft?",
        "Which greeting style may appear in phishing messages per the source?",
        "What should users do when they spot a suspicious message?",
        "How can hovering over a link help according to the source?",
        "Will a legitimate security team ask for passwords by email?",
    ]
    q = {
        "question_number": n,
        "question_type": "simulation" if simulation else qtype,
        "question": prompt or prompts[(n - 1) % len(prompts)] + f" (case {n})",
        "options": [
            f"Option A for case {n}",
            f"Option B for case {n}",
            "Open the official website manually",
            f"Option D for case {n}",
        ],
        "correct_answer": "Open the official website manually",
        "explanation": "The source says open the official website manually.",
        "difficulty": difficulty,
        "source_material": source_material,
        "source_evidence": "Users should never click unexpected links. Instead, open the official website manually",
        "source_excerpt": "open the official website manually by typing the known address",
    }
    if simulation:
        q["options"] = [
            "Click the urgent link immediately",
            "Reply with your password",
            "Open the official website manually",
            "Forward the message to strangers",
        ]
        q["scenario"] = {
            "title": f"Suspicious Account Warning {n}",
            "context": "You receive an urgent account-security email.",
            "sender": f"security-alert-{n}@example.com",
            "subject": "Your account will be suspended",
            "body": "Click the link to verify your identity.",
            "url": f"http://example-security-login-{n}.com",
        }
    return q


def build_valid_payload(
    *,
    total_sets: int = 2,
    normal_sets: int = 1,
    simulation_sets: int = 1,
    questions_per_set: int = 2,
    difficulty_mode: str = "mixed",
) -> dict:
    distinct_prompts = [
        "According to the supplied material, what is phishing?",
        "Which action does the source recommend instead of clicking unexpected links?",
        "What attachment-related risk does the source describe for phishing?",
        "Why should users verify the sender domain carefully?",
        "How does multi-factor authentication reduce damage per the source?",
        "What role does reporting suspicious messages play in the material?",
        "Which URL inspection tip is described in the source content?",
        "What password request behavior does the source say is illegitimate?",
    ]
    materials = [
        "Phishing definition",
        "Official website guidance",
        "Attachment phishing",
        "Sender domain verification",
        "Multi-factor authentication",
        "Reporting suspicious messages",
        "URL hovering tip",
        "Password request illegitimacy",
    ]
    sets = []
    qnum_global = 0
    for set_number in range(1, total_sets + 1):
        is_sim = set_number > normal_sets
        blueprint = create_difficulty_blueprint(questions_per_set, difficulty_mode)
        questions = []
        for i in range(1, questions_per_set + 1):
            qnum_global += 1
            prompt = distinct_prompts[(qnum_global - 1) % len(distinct_prompts)]
            prompt = f"{prompt} [set {set_number} q {i} id {qnum_global}]"
            questions.append(
                _make_question(
                    i,  # per-set question_number
                    simulation=is_sim,
                    prompt=prompt,
                    difficulty=blueprint[i - 1],
                    source_material=materials[(qnum_global - 1) % len(materials)],
                )
            )
        sets.append({
            "set_number": set_number,
            "set_type": "simulation" if is_sim else "normal",
            "title": f"Set {set_number}",
            "description": "Test set",
            "questions": questions,
        })
    return {"insufficient_source_content": False, "message": "", "sets": sets}


class ConfigurationValidationTests(TestCase):
    def test_normal_plus_simulation_equals_total(self):
        ok = validate_bank_configuration(
            total_sets=10, normal_sets=7, simulation_sets=3, questions_per_set=10,
        )
        self.assertTrue(ok.ok)

    def test_mismatch_rejected(self):
        bad = validate_bank_configuration(
            total_sets=10, normal_sets=6, simulation_sets=3, questions_per_set=10,
        )
        self.assertFalse(bad.ok)

    def test_questions_per_set_minimum(self):
        bad = validate_bank_configuration(
            total_sets=2, normal_sets=1, simulation_sets=1, questions_per_set=0,
        )
        self.assertFalse(bad.ok)


class DuplicateDetectionTests(TestCase):
    def test_normalize_and_exact(self):
        self.assertEqual(
            normalize_question_text("  What Is Phishing??? "),
            "what is phishing",
        )
        findings = find_duplicates([
            "What is phishing?",
            "what is phishing!!!",
        ])
        self.assertEqual(findings[0]["kind"], "exact")

    def test_near_duplicate(self):
        findings = find_duplicates([
            "Which action should you take when you receive an urgent phishing email?",
            "Which action should you take when you receive an urgent phishing e-mail?",
        ], near_threshold=0.88)
        self.assertTrue(findings)
        self.assertEqual(findings[0]["kind"], "near")


class PayloadValidationTests(TestCase):
    def test_valid_payload(self):
        payload = build_valid_payload()
        result = validate_generation_payload(
            payload,
            source_content=RICH_SOURCE,
            total_sets=2,
            normal_sets=1,
            simulation_sets=1,
            questions_per_set=2,
        )
        self.assertTrue(result.ok, result.errors)

    def test_missing_source_evidence_rejected(self):
        payload = build_valid_payload()
        payload["sets"][0]["questions"][0]["source_evidence"] = ""
        result = validate_generation_payload(
            payload,
            source_content=RICH_SOURCE,
            total_sets=2,
            normal_sets=1,
            simulation_sets=1,
            questions_per_set=2,
        )
        self.assertFalse(result.ok)
        self.assertTrue(any("source_evidence" in e for e in result.errors))

    def test_simulation_requires_scenario(self):
        payload = build_valid_payload()
        payload["sets"][1]["questions"][0].pop("scenario", None)
        result = validate_generation_payload(
            payload,
            source_content=RICH_SOURCE,
            total_sets=2,
            normal_sets=1,
            simulation_sets=1,
            questions_per_set=2,
        )
        self.assertFalse(result.ok)

    def test_duplicate_questions_rejected(self):
        payload = build_valid_payload()
        payload["sets"][1]["questions"][0]["question"] = payload["sets"][0]["questions"][0]["question"]
        result = validate_generation_payload(
            payload,
            source_content=RICH_SOURCE,
            total_sets=2,
            normal_sets=1,
            simulation_sets=1,
            questions_per_set=2,
        )
        self.assertFalse(result.ok)
        self.assertTrue(
            any("duplicate" in e.lower() for e in result.errors),
            result.errors,
        )

    def test_insufficient_flag(self):
        result = validate_generation_payload(
            {"insufficient_source_content": True, "message": "Need more material.", "sets": []},
            source_content="tiny",
            total_sets=2,
            normal_sets=1,
            simulation_sets=1,
            questions_per_set=2,
        )
        self.assertTrue(result.insufficient)
        self.assertFalse(result.ok)


class GenerationServiceTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            email="admin@example.com", password="pass12345", username="adminqb",
            is_staff=True,
        )
        self.bank = QuestionBank.objects.create(
            title="Phishing Awareness Fundamentals",
            description="Test bank",
            domain="phishing_simulator",
            source_content=RICH_SOURCE,
            total_sets=2,
            normal_sets=1,
            simulation_sets=1,
            questions_per_set=2,
            created_by=self.admin,
        )

    @patch("question_bank.services.generator.get_ai_provider")
    def test_successful_generation_stores_sets(self, mock_get):
        provider = mock_get.return_value
        provider.generate_question_bank.return_value = build_valid_payload()

        bank = generate_question_bank(self.bank.pk, created_by=self.admin)
        self.assertEqual(bank.status, QuestionBank.STATUS_REVIEW)
        self.assertEqual(bank.question_sets.count(), 2)
        self.assertEqual(
            Question.objects.filter(generated_by_ai=True, course="phishing_simulator").count(),
            4,
        )
        sim = bank.question_sets.get(set_type=QuestionSet.SET_TYPE_SIMULATION)
        self.assertEqual(sim.question_count, 2)
        self.assertEqual(sim.status, QuestionSet.STATUS_REVIEW)
        q = sim.ordered_questions()[0]
        self.assertEqual(q.question_type, Question.TYPE_SIMULATION)
        self.assertTrue(q.scenario_data)
        self.assertTrue(q.source_evidence)

    @patch("question_bank.services.generator.get_ai_provider")
    def test_retry_clears_previous_sets(self, mock_get):
        provider = mock_get.return_value
        provider.generate_question_bank.return_value = build_valid_payload()
        generate_question_bank(self.bank.pk)
        generate_question_bank(self.bank.pk)
        self.assertEqual(self.bank.question_sets.count(), 2)
        self.assertEqual(
            QuestionSet.objects.filter(question_bank=self.bank).count(),
            2,
        )

    @patch("question_bank.services.generator.get_ai_provider")
    def test_gemini_failure_marks_failed(self, mock_get):
        provider = mock_get.return_value
        provider.generate_question_bank.side_effect = GeminiProviderError(
            "Question generation failed: Gemini returned invalid structured output."
        )
        bank = generate_question_bank(self.bank.pk)
        self.assertEqual(bank.status, QuestionBank.STATUS_FAILED)
        self.assertIn("invalid structured output", bank.last_error)
        self.assertEqual(bank.question_sets.count(), 0)

    @patch("question_bank.services.generator.get_ai_provider")
    def test_invalid_json_path_via_provider_error(self, mock_get):
        provider = mock_get.return_value
        provider.generate_question_bank.side_effect = GeminiProviderError(
            "Question generation failed: Gemini returned invalid JSON."
        )
        bank = generate_question_bank(self.bank.pk)
        self.assertEqual(bank.status, QuestionBank.STATUS_FAILED)

    def test_model_clean_config(self):
        bank = QuestionBank(
            title="Bad",
            domain="osint",
            source_content=RICH_SOURCE,
            total_sets=10,
            normal_sets=5,
            simulation_sets=3,
            questions_per_set=10,
        )
        with self.assertRaises(Exception):
            bank.full_clean()


class ApprovalAndGameplayTests(TestCase):
    def setUp(self):
        self.student = User.objects.create_user(
            email="student@example.com", password="pass12345", username="studentqb",
        )
        self.admin = User.objects.create_user(
            email="admin2@example.com", password="pass12345", username="admin2qb",
            is_staff=True, is_superuser=True,
        )
        self.bank = QuestionBank.objects.create(
            title="Approved Bank",
            domain="phishing_simulator",
            source_content=RICH_SOURCE,
            total_sets=2,
            normal_sets=1,
            simulation_sets=1,
            questions_per_set=2,
            status=QuestionBank.STATUS_REVIEW,
            created_by=self.admin,
        )
        with patch("question_bank.services.generator.get_ai_provider") as mock_get:
            mock_get.return_value.generate_question_bank.return_value = build_valid_payload()
            generate_question_bank(self.bank.pk)

    def test_unapproved_sets_not_playable(self):
        self.assertEqual(usable_sets("phishing_simulator"), [])
        # Even with legacy empty, pick returns None or legacy — ensure bank REVIEW sets excluded
        for qset in QuestionSet.objects.filter(question_bank=self.bank):
            self.assertFalse(qset.is_usable)

    def test_approved_sets_playable_and_gameattempt(self):
        self.bank.status = QuestionBank.STATUS_APPROVED
        self.bank.save(update_fields=["status"])
        QuestionSet.objects.filter(question_bank=self.bank).update(
            status=QuestionSet.STATUS_APPROVED,
        )
        ready = usable_sets("phishing_simulator")
        self.assertTrue(ready)
        chosen = pick_set_for_user(self.student, "phishing_simulator")
        self.assertIsNotNone(chosen)
        self.assertTrue(chosen.is_usable)

        client = Client()
        client.login(email="student@example.com", password="pass12345")
        from unittest.mock import patch as patch_fn
        with patch_fn("games.views.has_completed_all_courses", return_value=True):
            res = client.get(reverse("games:phishing_simulator"))
            self.assertEqual(res.status_code, 200)
            questions = res.context["questions"]
            self.assertEqual(len(questions), 2)
            # Ensure Gemini was not needed at gameplay — no provider call here
            post = {f"question_{q['id']}": str(q["correct_index"]) for q in questions}
            res = client.post(reverse("games:phishing_simulator"), post)
            self.assertEqual(res.status_code, 200)
            attempt = GameAttempt.objects.get(user=self.student)
            self.assertEqual(attempt.total_questions, 2)
            self.assertEqual(attempt.score, 2)
            self.assertIsNotNone(attempt.question_set_id)

    def test_students_cannot_generate_via_api(self):
        client = Client()
        client.login(email="student@example.com", password="pass12345")
        res = client.post(reverse("question_bank:bank_generate", args=[self.bank.pk]))
        # staff_member_required redirects non-staff to login/admin
        self.assertIn(res.status_code, (302, 403))

    def test_admin_can_list_banks(self):
        client = Client()
        client.login(email="admin2@example.com", password="pass12345")
        res = client.get(reverse("question_bank:bank_list_create"))
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(any(b["id"] == self.bank.pk for b in data["results"]))

    def test_certificate_logic_unchanged_for_staff(self):
        self.assertTrue(is_eligible_for_certificate(self.admin))


class GeminiProviderUnitTests(TestCase):
    @override_settings(GEMINI_API_KEY="")
    def test_missing_api_key(self):
        provider = GeminiQuestionProvider(api_key="")
        with self.assertRaises(GeminiProviderError):
            provider.generate_question_bank(
                source_content="x",
                domain="phishing_simulator",
                language="en",
                difficulty="mixed",
                total_sets=1,
                normal_sets=1,
                simulation_sets=0,
                questions_per_set=1,
            )

    @override_settings(
        GEMINI_API_KEY="test-key",
        GEMINI_MODEL="gemini-primary",
        GEMINI_MODEL_FALLBACKS="gemini-fallback",
    )
    @patch("question_bank.services.providers.gemini.requests.post")
    def test_overloaded_model_falls_back(self, mock_post):
        busy = type("R", (), {
            "status_code": 503,
            "json": lambda self: {"error": {"message": "This model is currently experiencing high demand."}},
            "text": "busy",
        })()
        ok_payload = {
            "candidates": [{
                "content": {"parts": [{"text": json.dumps({
                    "insufficient_source_content": False,
                    "message": "",
                    "sets": [],
                })}]},
            }],
        }
        ok = type("R", (), {
            "status_code": 200,
            "json": lambda self: ok_payload,
            "text": "ok",
        })()
        mock_post.side_effect = [busy, ok]

        provider = GeminiQuestionProvider(
            api_key="test-key",
            model="gemini-primary",
            fallback_models=["gemini-fallback"],
            max_attempts=1,
        )
        result = provider.generate_question_bank(
            source_content="x" * 200,
            domain="phishing_simulator",
            language="en",
            difficulty="mixed",
            total_sets=1,
            normal_sets=1,
            simulation_sets=0,
            questions_per_set=1,
        )
        self.assertIn("sets", result)
        self.assertEqual(provider.model, "gemini-fallback")
        self.assertEqual(mock_post.call_count, 2)

    def test_parse_json_rejects_garbage(self):
        with self.assertRaises(GeminiProviderError):
            GeminiQuestionProvider._parse_json("not-json{{{")


class DifficultyBlueprintTests(TestCase):
    def test_five_mixed_is_2_2_1(self):
        bp = create_difficulty_blueprint(5, "mixed")
        self.assertEqual(bp, [
            "beginner", "beginner", "intermediate", "intermediate", "advanced",
        ])

    def test_ten_mixed_is_3_4_3(self):
        bp = create_difficulty_blueprint(10, "mixed")
        self.assertEqual(bp.count("beginner"), 3)
        self.assertEqual(bp.count("intermediate"), 4)
        self.assertEqual(bp.count("advanced"), 3)

    def test_beginner_only_customize(self):
        bp = create_difficulty_blueprint(5, "beginner")
        self.assertEqual(bp, ["beginner"] * 5)

    def test_advanced_only_customize(self):
        bp = create_difficulty_blueprint(5, "advanced")
        self.assertEqual(bp, ["advanced"] * 5)


class RepairPipelineTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            email="repair@example.com", password="pass12345", username="repairqb",
            is_staff=True,
        )
        self.bank = QuestionBank.objects.create(
            title="Repair Bank",
            domain="phishing_simulator",
            source_content=RICH_SOURCE,
            difficulty=QuestionBank.DIFF_MIXED,
            total_sets=1,
            normal_sets=1,
            simulation_sets=0,
            questions_per_set=5,
            created_by=self.admin,
        )

    @patch("question_bank.services.generator.get_ai_provider")
    def test_full_five_ready(self, mock_get):
        provider = mock_get.return_value
        provider.generate_question_bank.return_value = build_valid_payload(
            total_sets=1, normal_sets=1, simulation_sets=0, questions_per_set=5,
        )
        bank = generate_question_bank(self.bank.pk)
        self.assertEqual(bank.status, QuestionBank.STATUS_REVIEW)
        qs = bank.question_sets.get()
        self.assertEqual(qs.question_count, 5)
        diffs = [q.difficulty for q in qs.ordered_questions()]
        self.assertEqual(diffs, [
            "beginner", "beginner", "intermediate", "intermediate", "advanced",
        ])

    @patch("question_bank.services.generator.get_ai_provider")
    def test_returns_one_then_repairs_four(self, mock_get):
        provider = mock_get.return_value
        partial = build_valid_payload(
            total_sets=1, normal_sets=1, simulation_sets=0, questions_per_set=5,
        )
        partial["sets"][0]["questions"] = [partial["sets"][0]["questions"][0]]
        provider.generate_question_bank.return_value = partial

        full = build_valid_payload(
            total_sets=1, normal_sets=1, simulation_sets=0, questions_per_set=5,
        )
        replacements = []
        for q in full["sets"][0]["questions"][1:]:
            item = dict(q)
            item["set_number"] = 1
            item["question"] = f"Repair unique {q['question_number']} " + item["question"]
            replacements.append(item)
        provider.generate_replacements.return_value = {
            "insufficient_source_content": False,
            "message": "",
            "replacements": replacements,
        }

        bank = generate_question_bank(self.bank.pk)
        self.assertEqual(bank.status, QuestionBank.STATUS_REVIEW)
        self.assertEqual(bank.question_sets.get().question_count, 5)
        self.assertTrue(provider.generate_replacements.called)
        call_kw = provider.generate_replacements.call_args.kwargs
        self.assertEqual(len(call_kw["missing_slots"]), 4)
        self.assertEqual(
            [s["difficulty"] for s in call_kw["missing_slots"]],
            ["beginner", "intermediate", "intermediate", "advanced"],
        )

    @patch("question_bank.services.generator.get_ai_provider")
    def test_returns_three_repairs_two(self, mock_get):
        provider = mock_get.return_value
        full = build_valid_payload(
            total_sets=1, normal_sets=1, simulation_sets=0, questions_per_set=5,
        )
        partial = {
            **full,
            "sets": [{
                **full["sets"][0],
                "questions": full["sets"][0]["questions"][:3],
            }],
        }
        provider.generate_question_bank.return_value = partial
        replacements = []
        for q in full["sets"][0]["questions"][3:]:
            item = dict(q)
            item["set_number"] = 1
            item["question"] = f"Repair slot {q['question_number']} {item['question']}"
            replacements.append(item)
        provider.generate_replacements.return_value = {
            "insufficient_source_content": False,
            "replacements": replacements,
        }
        bank = generate_question_bank(self.bank.pk)
        self.assertEqual(bank.status, QuestionBank.STATUS_REVIEW)
        self.assertEqual(bank.question_sets.get().question_count, 5)

    @patch("question_bank.services.generator.get_ai_provider")
    def test_missing_advanced_replacement_must_be_advanced(self, mock_get):
        provider = mock_get.return_value
        full = build_valid_payload(
            total_sets=1, normal_sets=1, simulation_sets=0, questions_per_set=5,
        )
        partial = {
            **full,
            "sets": [{
                **full["sets"][0],
                "questions": full["sets"][0]["questions"][:4],
            }],
        }
        provider.generate_question_bank.return_value = partial
        adv = dict(full["sets"][0]["questions"][4])
        adv["set_number"] = 1
        adv["question"] = "Advanced repair unique scenario from MFA and reporting concepts"
        provider.generate_replacements.return_value = {
            "insufficient_source_content": False,
            "replacements": [adv],
        }
        bank = generate_question_bank(self.bank.pk)
        self.assertEqual(bank.status, QuestionBank.STATUS_REVIEW)
        last = bank.question_sets.get().ordered_questions()[-1]
        self.assertEqual(last.difficulty, "advanced")
        missing = provider.generate_replacements.call_args.kwargs["missing_slots"]
        self.assertEqual(missing, [{
            "set_number": 1,
            "set_type": "normal",
            "question_number": 5,
            "difficulty": "advanced",
            "question_type": "mcq",
        }])

    @patch("question_bank.services.generator.get_ai_provider")
    def test_partial_not_student_visible(self, mock_get):
        provider = mock_get.return_value
        full = build_valid_payload(
            total_sets=1, normal_sets=1, simulation_sets=0, questions_per_set=5,
        )
        partial = {
            **full,
            "sets": [{
                **full["sets"][0],
                "questions": full["sets"][0]["questions"][:2],
            }],
        }
        provider.generate_question_bank.return_value = partial
        provider.generate_replacements.return_value = {
            "insufficient_source_content": False,
            "replacements": [],
        }
        bank = generate_question_bank(self.bank.pk)
        self.assertEqual(bank.status, QuestionBank.STATUS_PARTIAL)
        qset = bank.question_sets.get()
        self.assertEqual(qset.status, QuestionSet.STATUS_DRAFT)
        self.assertFalse(qset.is_usable)
        self.assertEqual(usable_sets("phishing_simulator"), [])

    def test_short_source_does_not_hard_fail(self):
        ok, note = estimate_source_capacity("Phishing is a scam.", 5)
        self.assertTrue(ok)

    def test_filter_keeps_valid_rejects_wrong_difficulty(self):
        plans = build_set_plans(
            total_sets=1, normal_sets=1, simulation_sets=0,
            questions_per_set=5, difficulty_mode="mixed",
        )
        payload = build_valid_payload(
            total_sets=1, normal_sets=1, simulation_sets=0, questions_per_set=5,
        )
        payload["sets"][0]["questions"][4]["difficulty"] = "beginner"
        filtered = filter_payload_against_plans(
            payload, set_plans=plans, source_content=RICH_SOURCE,
        )
        self.assertEqual(len(filtered.accepted_questions), 4)
        self.assertEqual(len(filtered.missing_slots), 1)
        self.assertEqual(filtered.missing_slots[0]["difficulty"], "advanced")

    def test_source_material_required(self):
        plans = build_set_plans(
            total_sets=1, normal_sets=1, simulation_sets=0,
            questions_per_set=1, difficulty_mode="beginner",
        )
        payload = {
            "sets": [{
                "set_number": 1,
                "set_type": "normal",
                "title": "T",
                "questions": [{
                    "question_number": 1,
                    "question_type": "mcq",
                    "question": "What is phishing according to the text?",
                    "options": ["A", "B", "C", "D"],
                    "correct_answer": "A",
                    "explanation": "Because the source says so.",
                    "difficulty": "beginner",
                    "source_evidence": "Phishing is a social engineering attack that tricks users",
                }],
            }],
        }
        filtered = filter_payload_against_plans(
            payload, set_plans=plans, source_content=RICH_SOURCE,
        )
        self.assertEqual(len(filtered.accepted_questions), 0)
        self.assertTrue(any("source_material" in e for e in filtered.rejected_errors))
