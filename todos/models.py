from django.db import models
from django.utils import timezone


class Todo(models.Model):
    PRIORITY_CHOICES = [
        ("low", "Low"),
        ("medium", "Medium"),
        ("high", "High"),
    ]

    title = models.CharField(max_length=200)
    done = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    priority = models.CharField(max_length=6, choices=PRIORITY_CHOICES, default="medium")
    due_date = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at", "-id"]

    def __str__(self):
        return self.title

    @property
    def is_overdue(self):
        if self.due_date and not self.done and self.due_date < timezone.localdate():
            return True
        return False
