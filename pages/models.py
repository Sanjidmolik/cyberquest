from django.db import models


class ContactMessage(models.Model):
    """A message submitted through the public Contact form."""

    name = models.CharField(max_length=150)
    email = models.EmailField()
    message = models.TextField()
    submitted_at = models.DateTimeField(auto_now_add=True)
    is_resolved = models.BooleanField(default=False, help_text="Admin can check this off once handled.")

    class Meta:
        ordering = ["-submitted_at"]

    def __str__(self):
        return f"{self.name} <{self.email}> - {self.submitted_at:%Y-%m-%d}"


class HomepageVisitDay(models.Model):
    """Session-deduped homepage visits for one calendar day. Not unique visitors."""

    day = models.DateField(unique=True)
    visits = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["-day"]
        indexes = [models.Index(fields=["day"])]

    def __str__(self):
        return f"{self.day}: {self.visits}"
