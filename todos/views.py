from rest_framework import viewsets
from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from .models import Todo
from .serializers import TodoSerializer


class TodoViewSet(viewsets.ModelViewSet):
    serializer_class = TodoSerializer

    def get_queryset(self):
        return Todo.objects.filter(owner=self.request.user)

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)


@login_required
def index(request):
    return render(request, 'todos/index.html')
