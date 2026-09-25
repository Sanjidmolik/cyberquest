from django.contrib.auth import get_user_model
from django.test import TestCase, Client
from django.urls import reverse

from certificates.eligibility import is_eligible_for_certificate
from certificates.competency import get_competency_profile
from games.stats import get_best_attempt_percentages

from .models import (
    ADMIN_SET_NUMBERS,
    AUTO_SET_NUMBERS,
    QUESTIONS_PER_SET,
    SET_COURSE_KEYS,
    GameAttempt,
    Question,
    QuestionSet,
    QuestionSetItem,
)
from .question_sets import (
    ensure_set_slots,
    pick_set_for_user,
    regenerate_auto_sets,
    assign_questions_to_set,
    usable_sets,
)
from .seed_pool import iter_seed_questions

User = get_user_model()


class QuestionSetArchitectureTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        # Seed a compact but sufficient pool per course
        for course in SET_COURSE_KEYS:
            for i in range(40):
                Question.objects.create(
                    course=course,
                    prompt=f"{course} seed question {i}",
                    options=["A", "B", "C", "D"],
                    correct_index=0,
                    explanation=f"Explanation {i}",
                    correct_feedback="Correct!",
                    wrong_feedback=f"Incorrect. The correct answer is A. Explanation {i}",
                    is_active=True,
                )
        ensure_set_slots()
        for course in SET_COURSE_KEYS:
            # Fill admin sets 1-3
            qs_pool = list(Question.objects.filter(course=course).order_by("id"))
            for idx, num in enumerate(ADMIN_SET_NUMBERS):
                qset = QuestionSet.objects.get(course=course, set_number=num)
                chunk = qs_pool[idx * 5:(idx + 1) * 5]
                assign_questions_to_set(qset, chunk)
            regenerate_auto_sets(course)

    def setUp(self):
        self.user = User.objects.create_user(
            email="qset@example.com", password="testpass123", username="qsetuser",
        )
        self.client = Client()

    def test_each_course_has_exactly_10_sets(self):
        for course in SET_COURSE_KEYS:
            self.assertEqual(QuestionSet.objects.filter(course=course).count(), 10)

    def test_three_admin_seven_auto(self):
        for course in SET_COURSE_KEYS:
            self.assertEqual(
                QuestionSet.objects.filter(course=course, set_type="ADMIN").count(), 3
            )
            self.assertEqual(
                QuestionSet.objects.filter(course=course, set_type="AUTO").count(), 7
            )
            self.assertEqual(list(
                QuestionSet.objects.filter(course=course, set_type="ADMIN")
                .order_by("set_number").values_list("set_number", flat=True)
            ), list(ADMIN_SET_NUMBERS))
            self.assertEqual(list(
                QuestionSet.objects.filter(course=course, set_type="AUTO")
                .order_by("set_number").values_list("set_number", flat=True)
            ), list(AUTO_SET_NUMBERS))

    def test_admin_set_not_ready_with_fewer_than_five(self):
        qset = QuestionSet.objects.get(course="phishing_simulator", set_number=1)
        QuestionSetItem.objects.filter(question_set=qset).delete()
        self.assertEqual(qset.readiness, "INCOMPLETE")
        self.assertFalse(qset.is_usable)
        qs = list(Question.objects.filter(course="phishing_simulator")[:5])
        assign_questions_to_set(qset, qs)
        qset.refresh_from_db()
        self.assertEqual(qset.readiness, "READY")

    def test_auto_sets_have_five_unique_questions_from_course(self):
        for course in SET_COURSE_KEYS:
            for qset in QuestionSet.objects.filter(course=course, set_type="AUTO"):
                items = list(qset.items.select_related("question"))
                self.assertEqual(len(items), 5)
                ids = [i.question_id for i in items]
                self.assertEqual(len(ids), len(set(ids)))
                self.assertTrue(all(i.question.course == course for i in items))

    def test_user_receives_complete_set_and_feedback(self):
        self.client.login(email="qset@example.com", password="testpass123")
        # Bypass course gate
        self.user.course_intro_completed = True
        self.user.save()
        # has_completed_all_courses may check CourseProgress — patch via staff bypass if needed
        from unittest.mock import patch
        with patch("games.views.has_completed_all_courses", return_value=True):
            res = self.client.get(reverse("games:phishing_simulator"))
            self.assertEqual(res.status_code, 200)
            self.assertContains(res, "Question Set")
            questions = res.context["questions"]
            self.assertEqual(len(questions), 5)

            post = {f"question_{q['id']}": str(q["correct_index"]) for q in questions}
            res = self.client.post(reverse("games:phishing_simulator"), post)
            self.assertEqual(res.status_code, 200)
            self.assertContains(res, "Correct")
            self.assertEqual(GameAttempt.objects.filter(user=self.user).count(), 1)
            attempt = GameAttempt.objects.get(user=self.user)
            self.assertEqual(attempt.score, 5)
            self.assertEqual(attempt.total_questions, 5)
            self.assertIsNotNone(attempt.set_number)

    def test_wrong_answer_feedback_shows_correct(self):
        self.client.login(email="qset@example.com", password="testpass123")
        from unittest.mock import patch
        with patch("games.views.has_completed_all_courses", return_value=True):
            res = self.client.get(reverse("games:cryptography"))
            questions = res.context["questions"]
            # Answer all wrong (pick a different index)
            post = {}
            for q in questions:
                wrong = 0 if q["correct_index"] != 0 else 1
                post[f"question_{q['id']}"] = str(wrong)
            res = self.client.post(reverse("games:cryptography"), post)
            self.assertContains(res, "Incorrect")
            self.assertContains(res, "Correct answer:")
            self.assertContains(res, questions[0]["options"][questions[0]["correct_index"]])

    def test_prefer_unused_sets_then_allow_repeat(self):
        course = "osint"
        ready = list(usable_sets(course))
        self.assertGreaterEqual(len(ready), 10)
        seen = []
        for _ in range(10):
            chosen = pick_set_for_user(self.user, course)
            seen.append(chosen.set_number)
            GameAttempt.objects.create(
                user=self.user, game_key=course, score=3, total_questions=5,
                question_set=chosen, set_number=chosen.set_number, set_version=chosen.version,
            )
        self.assertEqual(len(set(seen)), 10)
        # After all used, still returns a ready set
        again = pick_set_for_user(self.user, course)
        self.assertIsNotNone(again)
        self.assertEqual(again.question_count, 5)

    def test_personal_best_never_decreases(self):
        GameAttempt.objects.create(user=self.user, game_key="network_defense", score=3, total_questions=5)
        GameAttempt.objects.create(user=self.user, game_key="network_defense", score=4, total_questions=5)
        GameAttempt.objects.create(user=self.user, game_key="network_defense", score=2, total_questions=5)
        best = get_best_attempt_percentages(self.user)
        self.assertEqual(best["network_defense"], 80)
        profile = get_competency_profile(self.user)
        net = next(c for c in profile["categories"] if c["game_key"] == "network_defense")
        self.assertEqual(net["percent"], 80)

    def test_regen_auto_preserves_attempts(self):
        qset = QuestionSet.objects.get(course="phishing_simulator", set_number=4)
        attempt = GameAttempt.objects.create(
            user=self.user, game_key="phishing_simulator", score=4, total_questions=5,
            question_set=qset, set_number=4, set_version=qset.version,
        )
        old_version = qset.version
        result = regenerate_auto_sets("phishing_simulator")
        self.assertTrue(result["ok"])
        attempt.refresh_from_db()
        self.assertEqual(attempt.score, 4)
        self.assertEqual(attempt.set_number, 4)
        qset.refresh_from_db()
        self.assertGreater(qset.version, old_version)

    def test_not_enough_questions_warns(self):
        course = "osint"
        Question.objects.filter(course=course).update(is_active=False)
        keep_ids = list(Question.objects.filter(course=course).order_by("id").values_list("id", flat=True)[:3])
        Question.objects.filter(id__in=keep_ids).update(is_active=True)
        result = regenerate_auto_sets(course)
        self.assertFalse(result["ok"])
        self.assertIn("Not enough questions", result["warning"])
        Question.objects.filter(course=course).update(is_active=True)
        regenerate_auto_sets(course)

    def test_certificate_still_works_for_staff(self):
        self.user.is_staff = True
        self.user.save()
        self.assertTrue(is_eligible_for_certificate(self.user))

    def test_seed_pool_iterable(self):
        rows = list(iter_seed_questions())
        self.assertGreaterEqual(len(rows), 100)
        courses = {r["course"] for r in rows}
        self.assertTrue(set(SET_COURSE_KEYS).issubset(courses))
