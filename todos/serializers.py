from rest_framework import serializers
from django.utils import timezone
from .models import Todo


class TodoSerializer(serializers.ModelSerializer):
    is_overdue = serializers.BooleanField(read_only=True)

    class Meta:
        model = Todo
        fields = ['id', 'title', 'done', 'created_at', 'priority', 'due_date', 'is_overdue', 'owner', 'order']
        read_only_fields = ['id', 'created_at', 'is_overdue', 'owner']

    def validate_title(self, value):
        if not value or not str(value).strip():
            raise serializers.ValidationError("This field must not be blank.")
        return value

    def validate_due_date(self, value):
        if value and self.instance is None and value < timezone.localdate():
            raise serializers.ValidationError("Due date must not be in the past.")
        return value
