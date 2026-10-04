from django.conf import settings
from django.db import models
from django.core.exceptions import ValidationError
from django.db.models import Q


SET_COURSES = [
    ("phishing_simulator", "Phishing"),
    ("password_cracker", "Password Security"),
    ("network_defense", "Network Defense"),
    ("cryptography", "Cryptography"),
    ("osint", "OSINT"),
]

SET_COURSE_KEYS = [c[0] for c in SET_COURSES]

ADMIN_SET_NUMBERS = (1, 2, 3)
AUTO_SET_NUMBERS = (4, 5, 6, 7, 8, 9, 10)
QUESTIONS_PER_SET = 5  # Legacy ADMIN/AUTO sets still use exactly 5
ADMIN_SETS_PER_COURSE = 3
AUTO_SETS_PER_COURSE = 7
SETS_PER_COURSE = 10


class GameAttempt(models.Model):
    GAME_CHOICES = [
        ("phishing_simulator", "Phishing Simulator"),
        ("password_cracker", "Password Cracker Challenge"),
        ("whack_a_phish", "Whack-a-Phish"),
        ("network_defense", "Network Defense"),
        ("cryptography", "Cryptography Challenge"),
        ("osint", "OSINT Investigation"),
        ("steganography", "Steganography Hunt"),
    ]
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="game_attempts")
    game_key = models.CharField(max_length=50, choices=GAME_CHOICES, db_index=True)
    score = models.PositiveIntegerField()
    total_questions = models.PositiveIntegerField()
    xp_awarded = models.PositiveIntegerField(default=0)
    completed_at = models.DateTimeField(auto_now_add=True, db_index=True)

    # Question-set tracking (nullable for legacy / non-set games)
    question_set = models.ForeignKey(
        "games.QuestionSet",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="attempts",
    )
    set_number = models.PositiveSmallIntegerField(null=True, blank=True)
    set_version = models.PositiveIntegerField(null=True, blank=True)
    # Balanced selection: ordered question IDs used for this attempt (audit / debugging)
    selected_question_ids = models.JSONField(
        default=list,
        blank=True,
        help_text="Ordered question PKs when the attempt used balanced difficulty×type selection.",
    )

    def __str__(self):
        return f"{self.user.email} - {self.game_key} - {self.score}/{self.total_questions}"

    @property
    def percent(self):
        if not self.total_questions:
            return 0
        return round(self.score / self.total_questions * 100)


class Question(models.Model):
    """Reusable MCQ in the course question pool (manual seed or AI bank)."""

    TYPE_MCQ = "mcq"
    TYPE_SIMULATION = "simulation"
    TYPE_TRUE_FALSE = "true_false"
    QUESTION_TYPE_CHOICES = [
        (TYPE_MCQ, "Multiple Choice"),
        (TYPE_SIMULATION, "Simulation"),
        (TYPE_TRUE_FALSE, "True / False"),
    ]

    DIFF_BEGINNER = "beginner"
    DIFF_INTERMEDIATE = "intermediate"
    DIFF_ADVANCED = "advanced"
    DIFFICULTY_CHOICES = [
        (DIFF_BEGINNER, "Beginner"),
        (DIFF_INTERMEDIATE, "Intermediate"),
        (DIFF_ADVANCED, "Advanced"),
    ]

    course = models.CharField(max_length=50, choices=SET_COURSES, db_index=True)
    prompt = models.TextField()
    options = models.JSONField(help_text="List of answer option strings.")
    correct_index = models.PositiveSmallIntegerField()
    explanation = models.TextField(help_text="Explanation shown after answering (esp. when correct).")
    correct_feedback = models.TextField(
        blank=True,
        help_text="Short message when the learner is correct. Defaults to 'Correct!' if blank.",
    )
    wrong_feedback = models.TextField(
        blank=True,
        help_text="Message when wrong — why the choice fails. Defaults to a standard incorrect line if blank.",
    )
    is_active = models.BooleanField(default=True)

    # AI Question Bank extensions (optional for legacy seed questions)
    question_type = models.CharField(
        max_length=20,
        choices=QUESTION_TYPE_CHOICES,
        default=TYPE_MCQ,
        db_index=True,
    )
    question_number = models.PositiveSmallIntegerField(null=True, blank=True)
    difficulty = models.CharField(
        max_length=20,
        choices=DIFFICULTY_CHOICES,
        blank=True,
        default="",
    )
    source_evidence = models.TextField(blank=True, default="")
    source_excerpt = models.TextField(blank=True, default="")
    source_section = models.CharField(max_length=255, blank=True, default="")
    scenario_data = models.JSONField(default=dict, blank=True)
    generated_by_ai = models.BooleanField(default=False)
    manually_edited = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["course", "id"]

    def __str__(self):
        return f"[{self.get_course_display()}] {self.prompt[:60]}"

    def clean(self):
        if not isinstance(self.options, list) or len(self.options) < 2:
            raise ValidationError({"options": "Provide at least 2 answer options."})
        if self.correct_index >= len(self.options):
            raise ValidationError({"correct_index": "correct_index must point to an option."})
        if self.question_type == self.TYPE_SIMULATION and not self.scenario_data:
            raise ValidationError({"scenario_data": "Simulation questions require scenario_data."})

    def save(self, *args, **kwargs):
        # Track manual edits on AI-generated questions after first create.
        if self.pk and self.generated_by_ai and not self.manually_edited:
            try:
                previous = Question.objects.get(pk=self.pk)
            except Question.DoesNotExist:
                previous = None
            if previous is not None:
                tracked = (
                    "prompt", "options", "correct_index", "explanation",
                    "scenario_data", "source_evidence", "source_excerpt",
                )
                for field in tracked:
                    if getattr(previous, field) != getattr(self, field):
                        self.manually_edited = True
                        break
        super().save(*args, **kwargs)

    def to_quiz_dict(self):
        data = {
            "id": self.pk,
            "prompt": self.prompt,
            "options": list(self.options),
            "correct_index": self.correct_index,
            "explanation": self.explanation,
            "correct_feedback": self.correct_feedback or "Correct!",
            "wrong_feedback": self.wrong_feedback or "Incorrect.",
            "question_type": self.question_type,
            "scenario": self.scenario_data or None,
            "difficulty": self.difficulty,
        }
        return data


class QuestionSet(models.Model):
    SET_TYPE_ADMIN = "ADMIN"
    SET_TYPE_AUTO = "AUTO"
    SET_TYPE_NORMAL = "NORMAL"
    SET_TYPE_SIMULATION = "SIMULATION"
    SET_TYPE_CHOICES = [
        (SET_TYPE_ADMIN, "Admin-created"),
        (SET_TYPE_AUTO, "System-generated"),
        (SET_TYPE_NORMAL, "Normal knowledge"),
        (SET_TYPE_SIMULATION, "Simulation"),
    ]

    STATUS_DRAFT = "DRAFT"
    STATUS_REVIEW = "REVIEW"
    STATUS_APPROVED = "APPROVED"
    STATUS_REJECTED = "REJECTED"
    STATUS_CHOICES = [
        (STATUS_DRAFT, "Draft"),
        (STATUS_REVIEW, "Review"),
        (STATUS_APPROVED, "Approved"),
        (STATUS_REJECTED, "Rejected"),
    ]

    course = models.CharField(max_length=50, choices=SET_COURSES, db_index=True)
    set_number = models.PositiveSmallIntegerField()
    set_type = models.CharField(max_length=12, choices=SET_TYPE_CHOICES)
    is_active = models.BooleanField(default=True)
    version = models.PositiveIntegerField(default=1)
    questions = models.ManyToManyField(Question, through="QuestionSetItem", related_name="sets", blank=True)

    # AI Question Bank linkage (null = legacy ADMIN/AUTO slot)
    question_bank = models.ForeignKey(
        "question_bank.QuestionBank",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="question_sets",
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_APPROVED,
        db_index=True,
        help_text="Bank-backed sets start as REVIEW; legacy sets remain APPROVED.",
    )
    title = models.CharField(max_length=255, blank=True, default="")
    description = models.TextField(blank=True, default="")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["course", "set_number"]
        constraints = [
            models.UniqueConstraint(
                fields=["course", "set_number"],
                condition=Q(question_bank__isnull=True),
                name="games_qset_legacy_course_setnum_uniq",
            ),
            models.UniqueConstraint(
                fields=["question_bank", "set_number"],
                condition=Q(question_bank__isnull=False),
                name="games_qset_bank_setnum_uniq",
            ),
        ]

    def __str__(self):
        bank = f" bank#{self.question_bank_id}" if self.question_bank_id else ""
        return f"{self.get_course_display()} Set {self.set_number} ({self.set_type}){bank}"

    @property
    def question_count(self):
        return self.items.count()

    @property
    def expected_question_count(self) -> int:
        if self.question_bank_id:
            return self.question_bank.questions_per_set
        return QUESTIONS_PER_SET

    @property
    def readiness(self):
        count = self.question_count
        needed = self.expected_question_count
        if count == needed:
            return "READY"
        if count > needed:
            return "INVALID"
        return "INCOMPLETE"

    @property
    def is_usable(self):
        """Students may only play active READY sets that are APPROVED (bank gate included)."""
        if not self.is_active or self.readiness != "READY":
            return False
        if self.question_bank_id:
            from question_bank.models import QuestionBank

            return (
                self.status == self.STATUS_APPROVED
                and self.question_bank.status == QuestionBank.STATUS_APPROVED
            )
        # Legacy ADMIN/AUTO slots
        return self.status == self.STATUS_APPROVED

    def ordered_questions(self):
        return [
            item.question
            for item in self.items.select_related("question").order_by("order", "id")
            if item.question.is_active
        ]


class QuestionSetItem(models.Model):
    question_set = models.ForeignKey(QuestionSet, on_delete=models.CASCADE, related_name="items")
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name="set_items")
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["order", "id"]
        unique_together = [("question_set", "question")]
