from django.contrib import admin
from .models import Todo


@admin.register(Todo)
class TodoAdmin(admin.ModelAdmin):
    list_display = ["title", "owner", "priority", "done", "due_date", "created_at"]
    list_filter = ["owner", "priority", "done"]
    raw_id_fields = ["owner"]
