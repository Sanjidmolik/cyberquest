"""Tests for difficulty × question_type balanced selection."""

from __future__ import annotations

import random
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from certificates.eligibility import is_eligible_for_certificate
from games.models import GameAttempt, Question, QuestionSet, QuestionSetItem
from question_bank.models import QuestionBank
from question_bank.services.difficulty_blueprint import (
    create_selection_plan,
    create_type_blueprint,
)
from question_bank.services.selection import (
    SelectionShortageError,
    load_questions_by_ids,
    select_questions_for_attempt,
)

User = get_user_model()


def _seed_approved_pool(course="phishing_simulator"):
    bank = QuestionBank.objects.create(
        title="Pool Bank",
        domain=course,
        source_content="Phishing is a social engineering attack. " * 20,
        status=QuestionBank.STATUS_APPROVED,
        attempt_question_count=5,
        attempt_mcq_count=2,
        attempt_simulation_count=3,
        difficulty=QuestionBank.DIFF_MIXED,
    )
    # Enough questions per (difficulty, type) for a 5-slot mixed plan
    specs = [
        ("beginner", "mcq", 3),
        ("beginner", "simulation", 3),
        ("intermediate", "mcq", 3),
        ("intermediate", "simulation", 3),
        ("advanced", "mcq", 2),
        ("advanced", "simulation", 3),
    ]
    created = []
    n = 0
    for diff, qtype, count in specs:
        qset = QuestionSet.objects.create(
            course=course,
            set_number=10 + len(created),
            set_type=(
                QuestionSet.SET_TYPE_SIMULATION
                if qtype == "simulation"
                else QuestionSet.SET_TYPE_NORMAL
            ),
            question_bank=bank,
            status=QuestionSet.STATUS_APPROVED,
            is_active=True,
            title=f"{diff}-{qtype}",
        )
        for i in range(count):
            n += 1
            q = Question.objects.create(
                course=course,
                prompt=f"{diff} {qtype} question number {n} unique text",
                options=["A", "B", "C", "D"],
                correct_index=0,
                explanation="Because the source says so.",
                question_type=qtype,
                difficulty=diff,
                source_evidence="Phishing is a social engineering attack",
                source_section=f"{diff} material",
                scenario_data=(
                    {"title": "Scenario", "body": "Suspicious email"}
                    if qtype == "simulation"
                    else {}
                ),
                generated_by_ai=True,
                is_active=True,
            )
            QuestionSetItem.objects.create(question_set=qset, question=q, order=i + 1)
            created.append(q)
    return bank, created


class TypeBlueprintTests(TestCase):
    def test_mcq_only(self):
        bp = create_type_blueprint(5, mcq_count=5, simulation_count=0, allowed_types=("mcq",))
        self.assertEqual(bp, ["mcq"] * 5)

    def test_simulation_only(self):
        bp = create_type_blueprint(
            5, mcq_count=0, simulation_count=5, allowed_types=("simulation",),
        )
        self.assertEqual(bp, ["simulation"] * 5)

    def test_mixed_2_3(self):
        bp = create_type_blueprint(5, mcq_count=2, simulation_count=3)
        self.assertEqual(bp.count("mcq"), 2)
        self.assertEqual(bp.count("simulation"), 3)

    def test_selection_plan_independent_axes(self):
        plan = create_selection_plan(
            question_count=5,
            difficulty_mode="mixed",
            mcq_count=2,
            simulation_count=3,
        )
        self.assertEqual(len(plan), 5)
        self.assertEqual(
            [p["difficulty"] for p in plan],
            ["beginner", "beginner", "intermediate", "intermediate", "advanced"],
        )
        self.assertEqual(sum(1 for p in plan if p["question_type"] == "mcq"), 2)
        self.assertEqual(sum(1 for p in plan if p["question_type"] == "simulation"), 3)


class BalancedSelectionTests(TestCase):
    def setUp(self):
        self.bank, self.questions = _seed_approved_pool()

    def test_beginner_mcq_selectable(self):
        plan = [{"difficulty": "beginner", "question_type": "mcq", "slot": 1}]
        result = select_questions_for_attempt(
            "phishing_simulator", plan=plan, rng=random.Random(1),
        )
        self.assertEqual(len(result.questions), 1)
        self.assertEqual(result.questions[0].difficulty, "beginner")
        self.assertEqual(result.questions[0].question_type, "mcq")

    def test_beginner_simulation_selectable(self):
        plan = [{"difficulty": "beginner", "question_type": "simulation", "slot": 1}]
        result = select_questions_for_attempt(
            "phishing_simulator", plan=plan, rng=random.Random(1),
        )
        self.assertEqual(result.questions[0].question_type, "simulation")
        self.assertEqual(result.questions[0].difficulty, "beginner")

    def test_mixed_attempt_ratio(self):
        result = select_questions_for_attempt(
            "phishing_simulator", bank=self.bank, rng=random.Random(7),
        )
        self.assertEqual(len(result.questions), 5)
        types = [q.question_type for q in result.questions]
        diffs = [q.difficulty for q in result.questions]
        self.assertEqual(types.count("mcq"), 2)
        self.assertEqual(types.count("simulation"), 3)
        self.assertEqual(diffs.count("beginner"), 2)
        self.assertEqual(diffs.count("intermediate"), 2)
        self.assertEqual(diffs.count("advanced"), 1)

    def test_simulation_only_game(self):
        plan = create_selection_plan(
            question_count=5,
            difficulty_mode="mixed",
            mcq_count=0,
            simulation_count=5,
            allowed_types=("simulation",),
        )
        result = select_questions_for_attempt(
            "phishing_simulator", plan=plan, rng=random.Random(3),
        )
        self.assertTrue(all(q.question_type == "simulation" for q in result.questions))
        self.assertEqual(
            [q.difficulty for q in result.questions].count("advanced"),
            1,
        )

    def test_mcq_only_game(self):
        plan = create_selection_plan(
            question_count=5,
            difficulty_mode="mixed",
            mcq_count=5,
            simulation_count=0,
            allowed_types=("mcq",),
        )
        result = select_questions_for_attempt(
            "phishing_simulator", plan=plan, rng=random.Random(3),
        )
        self.assertTrue(all(q.question_type == "mcq" for q in result.questions))

    def test_advanced_simulation_shortage(self):
        Question.objects.filter(
            course="phishing_simulator",
            difficulty="advanced",
            question_type="simulation",
        ).update(is_active=False)
        plan = [{"difficulty": "advanced", "question_type": "simulation", "slot": 1}]
        with self.assertRaises(SelectionShortageError) as ctx:
            select_questions_for_attempt("phishing_simulator", plan=plan)
        msg = str(ctx.exception)
        self.assertIn("Advanced Simulation", msg)
        self.assertIn("available: 0", msg)
        self.assertIn("Required: 1", msg)

    def test_order_stable_via_ids(self):
        result = select_questions_for_attempt(
            "phishing_simulator", bank=self.bank, rng=random.Random(11),
        )
        ids = result.question_ids
        reloaded = load_questions_by_ids(ids)
        self.assertEqual([q.pk for q in reloaded], ids)

    def test_intermediate_advanced_simulation_labels(self):
        for diff in ("intermediate", "advanced"):
            plan = [{"difficulty": diff, "question_type": "simulation", "slot": 1}]
            result = select_questions_for_attempt(
                "phishing_simulator", plan=plan, rng=random.Random(2),
            )
            self.assertEqual(result.questions[0].difficulty, diff)
            self.assertEqual(result.questions[0].question_type, "simulation")


class BalancedGameplayTests(TestCase):
    def setUp(self):
        self.bank, _ = _seed_approved_pool()
        self.user = User.objects.create_user(
            email="play@example.com", password="pass12345", username="playuser",
        )
        self.client = Client()
        self.client.login(email="play@example.com", password="pass12345")

    def test_refresh_keeps_same_question_ids(self):
        with patch("games.views.has_completed_all_courses", return_value=True):
            r1 = self.client.get(reverse("games:phishing_simulator"))
            self.assertEqual(r1.status_code, 200)
            ids1 = [q["id"] for q in r1.context["questions"]]
            r2 = self.client.get(reverse("games:phishing_simulator"))
            ids2 = [q["id"] for q in r2.context["questions"]]
            self.assertEqual(ids1, ids2)

    def test_scoring_unchanged(self):
        with patch("games.views.has_completed_all_courses", return_value=True):
            res = self.client.get(reverse("games:phishing_simulator"))
            questions = res.context["questions"]
            post = {f"question_{q['id']}": str(q["correct_index"]) for q in questions}
            res = self.client.post(reverse("games:phishing_simulator"), post)
            self.assertEqual(res.status_code, 200)
            attempt = GameAttempt.objects.get(user=self.user)
            self.assertEqual(attempt.score, len(questions))
            self.assertEqual(attempt.total_questions, len(questions))
            self.assertEqual(attempt.selected_question_ids, [q["id"] for q in questions])
            self.assertEqual(attempt.xp_awarded, attempt.score * 20)

    def test_certificate_rule_unchanged_for_staff(self):
        self.user.is_staff = True
        self.user.save()
        self.assertTrue(is_eligible_for_certificate(self.user))
