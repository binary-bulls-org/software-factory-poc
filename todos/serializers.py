from rest_framework import serializers
from .models import Todo


class TodoSerializer(serializers.ModelSerializer):
    class Meta:
        model = Todo
        fields = ['id', 'title', 'done', 'created_at']
        read_only_fields = ['id', 'created_at']

    def validate_title(self, value):
        if not value or not str(value).strip():
            raise serializers.ValidationError("This field must not be blank.")
        return value
