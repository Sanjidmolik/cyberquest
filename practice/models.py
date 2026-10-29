from django.conf import settings
from django.db import models
from django.utils import timezone


class PracticeSession(models.Model):
    """One practice attempt: simulation or incident. Stores decisions + result."""

    DOMAIN_CHOICES = [
        ("phishing", "Phishing"),
        ("password", "Password Security"),
        ("network", "Network Defense"),
        ("cryptography", "Cryptography"),
        ("steganography", "Steganography"),
        ("osint", "OSINT Investigation"),
        ("safety", "Online Safety"),
        ("malware", "Malware & Ransomware Defence"),
        ("device", "Device & Data Protection"),
        ("privacy", "Social Media & Privacy"),
        ("response", "Attack Response & Recovery"),
    ]
    ACTIVITY_CHOICES = [
        ("game", "Game"),
        ("simulation", "Simulation"),
        ("incident", "Incident"),
    ]
    DIFFICULTY_CHOICES = [
        ("beginner", "Beginner"),
        ("intermediate", "Intermediate"),
        ("advanced", "Advanced"),
    ]
    STATUS_CHOICES = [
        ("in_progress", "In Progress"),
        ("completed", "Completed"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="practice_sessions",
    )
    domain = models.CharField(max_length=20, choices=DOMAIN_CHOICES)
    activity_type = models.CharField(max_length=20, choices=ACTIVITY_CHOICES)
    scenario_key = models.CharField(max_length=80)
    difficulty = models.CharField(max_length=20, choices=DIFFICULTY_CHOICES)
    score = models.IntegerField(default=0)
    max_score = models.PositiveIntegerField(default=100)
    decisions = models.JSONField(default=list, blank=True)
    state = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="in_progress")
    result_summary = models.TextField(blank=True)
    strengths = models.TextField(blank=True)
    improvements = models.TextField(blank=True)
    xp_awarded = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user_id} {self.domain} {self.activity_type} {self.score}%"

    @property
    def percent(self):
        if not self.max_score:
            return 0
        return max(0, min(100, round(self.score / self.max_score * 100)))


# ---- Interactive practice sessions (step engine) ----
# Seed content comes from practice/scenario_content/*.json (`load_scenarios`) and the original
# scenarios (`convert_scenarios`); staff edit and publish in the Practice Studio. Answers stay on
# the server: see practice/graders.py.

class ScenarioQuerySet(models.QuerySet):
    def published(self):
        """What students can see and play."""
        return self.filter(status=Scenario.PUBLISHED)


class Scenario(models.Model):
    KIND = [("simulation", "Simulation"), ("incident", "Incident"), ("choice", "Choice")]
    DRAFT, PUBLISHED, ARCHIVED = "draft", "published", "archived"
    STATUS = [(DRAFT, "Draft"), (PUBLISHED, "Published"), (ARCHIVED, "Archived")]
    SEED, STUDIO = "seed", "studio"
    SOURCE = [(SEED, "Seed (management commands)"), (STUDIO, "Practice Studio")]

    slug = models.SlugField(unique=True)
    # The course this scenario practises. CyberQuest has no separate module model,
    # so the topic is the Course itself (matched by Course.code when loading).
    topic = models.ForeignKey("courses.Course", on_delete=models.CASCADE, related_name="practice_scenarios")
    kind = models.CharField(max_length=12, choices=KIND)
    title = models.CharField(max_length=160)
    difficulty = models.CharField(max_length=12)
    est_minutes = models.PositiveSmallIntegerField()
    # Kept for the data format, but Practice is self-paced: the engine never shows a countdown.
    time_limit_sec = models.PositiveIntegerField(null=True, blank=True)
    xp_reward = models.PositiveIntegerField()
    # The published content: steps including answers. Never sent to the browser as-is.
    content = models.JSONField()
    version = models.PositiveIntegerField(default=1)
    status = models.CharField(max_length=10, choices=STATUS, default=PUBLISHED)
    # Studio edits not yet published. Students keep getting `content` until publish.
    draft_content = models.JSONField(null=True, blank=True)
    draft_meta = models.JSONField(null=True, blank=True)  # pending title, difficulty, minutes, topic
    # Optimistic locking for the Studio editor: every save must name the revision it started
    # from, so one admin never silently overwrites another's changes.
    draft_revision = models.PositiveIntegerField(default=0)
    draft_saved_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                       related_name="+")
    draft_saved_at = models.DateTimeField(null=True, blank=True)
    # "seed" rows may be rewritten by the seed commands; the first studio save makes a row "studio",
    # and the seed commands never touch it again.
    source = models.CharField(max_length=10, choices=SOURCE, default=SEED)
    # sha256 of the content the seed commands last wrote, so a hand edit is never overwritten.
    content_hash = models.CharField(max_length=64, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                   related_name="+")
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                   related_name="+")
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    objects = ScenarioQuerySet.as_manager()

    class Meta:
        ordering = ["topic__order", "slug"]
        permissions = [
            ("use_studio", "Can use the Practice Studio (create, edit, preview)"),
            ("publish_scenario", "Can publish, unpublish, archive and restore practice scenarios"),
        ]

    def __str__(self):
        return self.slug

    def content_for_version(self, version):
        """The content an attempt was started on: the live content, or a published snapshot."""
        if not version or version == self.version:
            return self.content
        snapshot = self.versions.filter(version=version).values_list("content", flat=True).first()
        return snapshot if snapshot is not None else self.content


class ScenarioVersion(models.Model):
    """A snapshot of a scenario's content: written by the seed commands whenever they write new
    content, and by the studio on every publish. Attempts are graded on the snapshot of the
    version they started on."""
    SEED, STUDIO = "seed", "studio"
    ORIGIN = [(SEED, "Seed command"), (STUDIO, "Studio publish")]

    scenario = models.ForeignKey(Scenario, on_delete=models.CASCADE, related_name="versions")
    version = models.PositiveIntegerField()
    origin = models.CharField(max_length=10, choices=ORIGIN, default=STUDIO)
    content = models.JSONField()
    meta = models.JSONField(default=dict, blank=True)  # title, difficulty, minutes, XP, topic code
    published_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                     related_name="+")
    published_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["scenario", "-version"]
        constraints = [models.UniqueConstraint(fields=["scenario", "version"], name="unique_scenario_version")]

    def __str__(self):
        return f"{self.scenario_id} v{self.version}"


class StudioAuditLog(models.Model):
    """Append-only record of who changed which practice scenario, and how."""
    ACTIONS = [
        ("create", "Created"), ("duplicate", "Duplicated"), ("import", "Imported"), ("edit", "Edited"),
        ("publish", "Published"), ("unpublish", "Unpublished"), ("archive", "Archived"),
        ("restore", "Restored a version"), ("seed_force", "Overwritten by a forced seed command"),
    ]
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                             related_name="+")
    scenario = models.ForeignKey(Scenario, on_delete=models.SET_NULL, null=True, blank=True, related_name="audit")
    slug = models.CharField(max_length=50)  # kept if the scenario is deleted
    action = models.CharField(max_length=12, choices=ACTIONS)
    version = models.PositiveIntegerField(null=True, blank=True)
    summary = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-created_at", "-pk"]

    def __str__(self):
        return f"{self.slug} {self.action} {self.created_at:%Y-%m-%d %H:%M}"


class AttemptQuerySet(models.QuerySet):
    def real(self):
        """Learner attempts: everything except Practice Studio previews."""
        return self.filter(is_preview=False)


class Attempt(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="practice_attempts")
    scenario = models.ForeignKey(Scenario, on_delete=models.CASCADE, related_name="attempts")
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    hearts = models.PositiveSmallIntegerField(default=3)
    score = models.IntegerField(default=0)
    state = models.JSONField(default=dict, blank=True)  # branch meters, current scene, results
    outcome = models.CharField(max_length=20, blank=True)
    xp_awarded = models.PositiveIntegerField(default=0)
    # Staff preview from the Practice Studio: graded like any attempt, but never awards XP or
    # badges and never reaches history, Cyber DNA or analytics.
    is_preview = models.BooleanField(default=False)

    objects = AttemptQuerySet.as_manager()

    class Meta:
        ordering = ["-started_at"]
        indexes = [models.Index(fields=["user", "scenario"])]

    def __str__(self):
        return f"{self.user_id} {self.scenario_id} {self.outcome or 'in progress'}"


class StepAnswer(models.Model):
    attempt = models.ForeignKey(Attempt, on_delete=models.CASCADE, related_name="answers")
    step_index = models.PositiveSmallIntegerField()
    answer = models.JSONField()
    correct = models.BooleanField(null=True)
    time_ms = models.PositiveIntegerField(default=0)
    confidence = models.CharField(max_length=12, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["attempt", "step_index", "pk"]
