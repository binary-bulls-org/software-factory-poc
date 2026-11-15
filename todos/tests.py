from django.test import TestCase
from django.db import connection
from django.urls import reverse
from datetime import timedelta
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase
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

    def test_todo_default_priority(self):
        todo = Todo.objects.create(title="Test Todo")
        self.assertEqual(todo.priority, "medium")

    def test_todo_str(self):
        todo = Todo(title="Buy groceries")
        self.assertEqual(str(todo), "Buy groceries")

    def test_todo_ordering(self):
        todo1 = Todo.objects.create(title="First")
        todo2 = Todo.objects.create(title="Second")
        todos = list(Todo.objects.all())
        self.assertEqual(todos, [todo2, todo1])

    def test_is_overdue_property(self):
        today = timezone.localdate()
        past_date = today - timedelta(days=1)
        future_date = today + timedelta(days=1)

        # 1. is_overdue is True for a not-done todo with a past due_date
        todo_past = Todo.objects.create(title="Past", due_date=past_date, done=False)
        self.assertTrue(todo_past.is_overdue)

        # 2. is_overdue is False when done is True (even if past due_date)
        todo_done_past = Todo.objects.create(title="Done Past", due_date=past_date, done=True)
        self.assertFalse(todo_done_past.is_overdue)

        # 3. is_overdue is False when due_date is None
        todo_no_date = Todo.objects.create(title="No Date", due_date=None, done=False)
        self.assertFalse(todo_no_date.is_overdue)

        # 4. is_overdue is False when due_date is in the future
        todo_future = Todo.objects.create(title="Future", due_date=future_date, done=False)
        self.assertFalse(todo_future.is_overdue)


class TodoApiTests(APITestCase):
    def test_list_todos_empty(self):
        url = reverse('todo-list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, [])

    def test_create_todo(self):
        url = reverse('todo-list')
        data = {"title": "buy milk"}
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertFalse(response.data['done'])
        self.assertEqual(response.data['priority'], 'medium')
        self.assertTrue(Todo.objects.filter(title="buy milk", done=False).exists())

    def test_create_todo_with_priority_and_future_duedate(self):
        url = reverse('todo-list')
        future_date = timezone.localdate() + timedelta(days=1)
        data = {
            "title": "important task",
            "priority": "high",
            "due_date": future_date.isoformat()
        }
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['priority'], 'high')
        self.assertEqual(response.data['due_date'], future_date.isoformat())

    def test_create_todo_invalid_priority(self):
        url = reverse('todo-list')
        data = {
            "title": "invalid priority",
            "priority": "urgent"
        }
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_todo_past_duedate(self):
        url = reverse('todo-list')
        past_date = timezone.localdate() - timedelta(days=1)
        data = {
            "title": "past due",
            "due_date": past_date.isoformat()
        }
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_todo_invalid_title(self):
        url = reverse('todo-list')
        # Test empty title
        response = self.client.post(url, {"title": ""}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        # Test missing title
        response2 = self.client.post(url, {}, format='json')
        self.assertEqual(response2.status_code, status.HTTP_400_BAD_REQUEST)

    def test_retrieve_todo(self):
        todo = Todo.objects.create(title="Test Todo")
        url = reverse('todo-detail', args=[todo.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['title'], "Test Todo")
        self.assertEqual(response.data['id'], todo.id)

    def test_patch_todo(self):
        todo = Todo.objects.create(title="Test Todo", done=False)
        url = reverse('todo-detail', args=[todo.id])
        response = self.client.patch(url, {"done": True}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        todo.refresh_from_db()
        self.assertTrue(todo.done)

    def test_put_todo(self):
        todo = Todo.objects.create(title="Old Title", done=False)
        url = reverse('todo-detail', args=[todo.id])
        response = self.client.put(url, {"title": "New Title", "done": True}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        todo.refresh_from_db()
        self.assertEqual(todo.title, "New Title")
        self.assertTrue(todo.done)

    def test_delete_todo(self):
        todo = Todo.objects.create(title="To be deleted")
        url = reverse('todo-detail', args=[todo.id])
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Todo.objects.filter(id=todo.id).exists())

    def test_retrieve_non_existing_todo(self):
        url = reverse('todo-detail', args=[99999])
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class TodoIndexViewTests(TestCase):
    def test_index_view(self):
        url = reverse('index')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTemplateUsed(response, 'todos/index.html')
        self.assertContains(response, 'Todo list')
