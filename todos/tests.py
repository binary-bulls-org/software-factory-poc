from django.test import TestCase
from django.db import connection
from .models import Todo

# Create your tests here.


class DatabaseConnectionTests(TestCase):
    def test_database_connection(self):
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            row = cursor.fetchone()
        self.assertEqual(row[0], 1)


class TodoModelTests(TestCase):
    def test_todo_default_done(self):
        todo = Todo.objects.create(title="Test Todo")
        self.assertFalse(todo.done)

    def test_todo_str(self):
        todo = Todo(title="Buy groceries")
        self.assertEqual(str(todo), "Buy groceries")

    def test_todo_ordering(self):
        todo1 = Todo.objects.create(title="First")
        todo2 = Todo.objects.create(title="Second")
        todos = list(Todo.objects.all())
        self.assertEqual(todos, [todo2, todo1])
