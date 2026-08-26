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
