from django.test import TestCase
from django.db import connection
from django.urls import reverse
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

    def test_todo_str(self):
        todo = Todo(title="Buy groceries")
        self.assertEqual(str(todo), "Buy groceries")

    def test_todo_ordering(self):
        todo1 = Todo.objects.create(title="First")
        todo2 = Todo.objects.create(title="Second")
        todos = list(Todo.objects.all())
        self.assertEqual(todos, [todo2, todo1])


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
        self.assertTrue(Todo.objects.filter(title="buy milk", done=False).exists())

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
