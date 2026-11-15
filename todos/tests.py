from django.test import TestCase
from django.db import connection
from django.urls import reverse
from datetime import timedelta
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase, APIClient
from django.contrib.auth.models import User
from .models import Todo

# Create your tests here.


class DatabaseConnectionTests(TestCase):
    def test_database_connection(self):
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            row = cursor.fetchone()
        self.assertEqual(row[0], 1)


class TodoModelTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="alice", password="pass12345")

    def test_todo_default_done(self):
        todo = Todo.objects.create(title="Test Todo", owner=self.user)
        self.assertFalse(todo.done)

    def test_todo_default_priority(self):
        todo = Todo.objects.create(title="Test Todo", owner=self.user)
        self.assertEqual(todo.priority, "medium")

    def test_todo_str(self):
        todo = Todo(title="Buy groceries", owner=self.user)
        self.assertEqual(str(todo), "Buy groceries")

    def test_todo_ordering(self):
        todo1 = Todo.objects.create(title="First", owner=self.user)
        todo2 = Todo.objects.create(title="Second", owner=self.user)
        todos = list(Todo.objects.filter(owner=self.user))
        self.assertEqual(todos, [todo2, todo1])

    def test_is_overdue_property(self):
        today = timezone.localdate()
        past_date = today - timedelta(days=1)
        future_date = today + timedelta(days=1)

        # 1. is_overdue is True for a not-done todo with a past due_date
        todo_past = Todo.objects.create(title="Past", due_date=past_date, done=False, owner=self.user)
        self.assertTrue(todo_past.is_overdue)

        # 2. is_overdue is False when done is True (even if past due_date)
        todo_done_past = Todo.objects.create(title="Done Past", due_date=past_date, done=True, owner=self.user)
        self.assertFalse(todo_done_past.is_overdue)

        # 3. is_overdue is False when due_date is None
        todo_no_date = Todo.objects.create(title="No Date", due_date=None, owner=self.user)
        self.assertFalse(todo_no_date.is_overdue)

        # 4. is_overdue is False when due_date is in the future
        todo_future = Todo.objects.create(title="Future", due_date=future_date, owner=self.user)
        self.assertFalse(todo_future.is_overdue)


class TodoApiTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="alice", password="pass12345")
        self.client.force_authenticate(user=self.user)

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
        self.assertTrue(Todo.objects.filter(title="buy milk", done=False, owner=self.user).exists())

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
        response = self.client.post(url, {'title': ""}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        # Test missing title
        response2 = self.client.post(url, {}, format='json')
        self.assertEqual(response2.status_code, status.HTTP_400_BAD_REQUEST)

    def test_retrieve_todo(self):
        todo = Todo.objects.create(title="Test Todo", owner=self.user)
        url = reverse('todo-detail', args=[todo.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['title'], "Test Todo")
        self.assertEqual(response.data['id'], todo.id)

    def test_patch_todo(self):
        todo = Todo.objects.create(title="Test Todo", done=False, owner=self.user)
        url = reverse('todo-detail', args=[todo.id])
        response = self.client.patch(url, {"done": True}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        todo.refresh_from_db()
        self.assertTrue(todo.done)

    def test_put_todo(self):
        todo = Todo.objects.create(title="Old Title", done=False, owner=self.user)
        url = reverse('todo-detail', args=[todo.id])
        response = self.client.put(url, {"title": "New Title", "done": True}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        todo.refresh_from_db()
        self.assertEqual(todo.title, "New Title")
        self.assertTrue(todo.done)

    def test_delete_todo(self):
        todo = Todo.objects.create(title="To be deleted", owner=self.user)
        url = reverse('todo-detail', args=[todo.id])
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Todo.objects.filter(id=todo.id).exists())

    def test_retrieve_non_existing_todo(self):
        url = reverse('todo-detail', args=[99999])
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class TodoIsolationTests(APITestCase):
    def setUp(self):
        self.alice = User.objects.create_user(username="alice", password="pass12345")
        self.bob = User.objects.create_user(username="bob", password="pass12345")
        self.alice_todo = Todo.objects.create(title="Alice todo", owner=self.alice)
        self.bob_todo = Todo.objects.create(title="Bob todo", owner=self.bob)

    def test_list_returns_only_own_todos(self):
        self.client.force_authenticate(user=self.alice)
        response = self.client.get(reverse('todo-list'))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        titles = [t['title'] for t in response.data]
        self.assertEqual(titles, ["Alice todo"])

    def test_cannot_retrieve_other_users_todo(self):
        self.client.force_authenticate(user=self.alice)
        response = self.client.get(reverse('todo-detail', args=[self.bob_todo.id]))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_cannot_update_other_users_todo(self):
        self.client.force_authenticate(user=self.alice)
        response = self.client.patch(
            reverse('todo-detail', args=[self.bob_todo.id]), {"done": True}, format='json'
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.bob_todo.refresh_from_db()
        self.assertFalse(self.bob_todo.done)

    def test_cannot_delete_other_users_todo(self):
        self.client.force_authenticate(user=self.alice)
        response = self.client.delete(reverse('todo-detail', args=[self.bob_todo.id]))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertTrue(Todo.objects.filter(id=self.bob_todo.id).exists())

    def test_owner_cannot_be_spoofed(self):
        self.client.force_authenticate(user=self.alice)
        response = self.client.post(
            reverse('todo-list'),
            {"title": "hijack", "owner": self.bob.id},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        todo = Todo.objects.get(title="hijack")
        self.assertEqual(todo.owner, self.alice)

    def test_legacy_todo_without_owner_is_invisible(self):
        legacy = Todo.objects.create(title="Legacy")
        self.client.force_authenticate(user=self.alice)
        response = self.client.get(reverse('todo-list'))
        self.assertNotIn("Legacy", [t['title'] for t in response.data])
        response = self.client.get(reverse('todo-detail', args=[legacy.id]))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class AnonymousAccessTests(APITestCase):
    def test_anonymous_api_request_is_forbidden(self):
        # SessionAuthentication sends no WWW-Authenticate header -> 403, not 401
        response = self.client.get(reverse('todo-list'))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_anonymous_index_redirects_to_login(self):
        response = self.client.get(reverse('index'))
        self.assertEqual(response.status_code, status.HTTP_302_FOUND)
        self.assertEqual(response.url, '/accounts/login/?next=/')


class CsrfTests(APITestCase):
    """CSRF is enforced by SessionAuthentication on unsafe methods."""

    def setUp(self):
        self.user = User.objects.create_user(username="alice", password="pass12345")

    def _csrf_client(self):
        """A logged-in client that performs real session auth (no force_authenticate,
        which bypasses CSRF) and enforces CSRF checks."""
        client = APIClient(enforce_csrf_checks=True)
        client.force_login(self.user)
        # Ensure a CSRF cookie exists (force_login does not request a page).
        client.get(reverse('index'))
        return client

    def test_post_without_csrf_token_is_forbidden(self):
        client = self._csrf_client()
        response = client.post(reverse('todo-list'), {"title": "no token"}, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_post_with_csrf_token_succeeds(self):
        client = self._csrf_client()
        token = client.cookies['csrftoken'].value
        response = client.post(
            reverse('todo-list'),
            {"title": "with token"},
            format='json',
            HTTP_X_CSRFTOKEN=token,
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)


class TodoIndexViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="alice", password="pass12345")

    def test_index_view(self):
        self.client.force_login(self.user)
        url = reverse('index')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTemplateUsed(response, 'todos/index.html')
        self.assertContains(response, 'Todo list')
        self.assertContains(response, 'priority')
        self.assertContains(response, 'due_date')
        self.assertContains(response, 'is_overdue')
        self.assertContains(response, 'Low')
        self.assertContains(response, 'Medium')
        self.assertContains(response, 'High')
        self.assertContains(response, 'type="date"')
        self.assertContains(response, 'alice')
        self.assertContains(response, 'Log out')
