from django.db import models
from django.conf import settings
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
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="todos",
    )

    order = models.IntegerField(default=0)

    class Meta:
        ordering = ["order", "-created_at", "-id"]

    def __str__(self):
        return self.title

    @property
    def is_overdue(self):
        if self.due_date and not self.done and self.due_date < timezone.localdate():
            return True
        return False
