from django.test import TestCase
from django.urls import reverse
from django.contrib.auth.models import User


class RegisterTests(TestCase):
    def test_register_page_renders(self):
        response = self.client.get(reverse('register'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'accounts/register.html')

    def test_register_creates_user_and_logs_in(self):
        response = self.client.post(reverse('register'), {
            'username': 'newuser',
            'password': 'Str0ngPass!123',
            'password_confirm': 'Str0ngPass!123',
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, '/')
        self.assertTrue(User.objects.filter(username='newuser').exists())
        # logged in: the index page shows the username
        me = self.client.get(reverse('index'))
        self.assertContains(me, 'newuser')

    def test_register_duplicate_username_rejected(self):
        User.objects.create_user(username='taken', password='Str0ngPass!123')
        response = self.client.post(reverse('register'), {
            'username': 'taken',
            'password': 'Str0ngPass!123',
            'password_confirm': 'Str0ngPass!123',
        })
        self.assertEqual(response.status_code, 400)
        self.assertFalse(User.objects.filter(username='taken').count() > 1)

    def test_register_password_mismatch_rejected(self):
        response = self.client.post(reverse('register'), {
            'username': 'mismatch',
            'password': 'Str0ngPass!123',
            'password_confirm': 'OtherPass!123',
        })
        self.assertEqual(response.status_code, 400)
        self.assertFalse(User.objects.filter(username='mismatch').exists())

    def test_register_weak_password_rejected(self):
        response = self.client.post(reverse('register'), {
            'username': 'weakling',
            'password': '123',
            'password_confirm': '123',
        })
        self.assertEqual(response.status_code, 400)

    def test_register_requires_csrf(self):
        from rest_framework.test import APIClient
        client = APIClient(enforce_csrf_checks=True)
        response = client.post(reverse('register'), {
            'username': 'csrfless',
            'password': 'Str0ngPass!123',
            'password_confirm': 'Str0ngPass!123',
        })
        self.assertEqual(response.status_code, 403)


class LoginTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='alice', password='Str0ngPass!123')

    def test_login_page_renders(self):
        response = self.client.get(reverse('login'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'accounts/login.html')

    def test_login_success(self):
        response = self.client.post(reverse('login'), {
            'username': 'alice',
            'password': 'Str0ngPass!123',
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, '/')

    def test_login_wrong_password(self):
        response = self.client.post(reverse('login'), {
            'username': 'alice',
            'password': 'wrong',
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'error')

    def test_authenticated_user_redirected_away_from_login(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse('login'))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, '/')


class LogoutTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='alice', password='Str0ngPass!123')
        self.client.force_login(self.user)

    def test_logout_post_clears_session(self):
        response = self.client.post(reverse('logout'))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, '/accounts/login/')
        me = self.client.get(reverse('index'))
        self.assertEqual(me.status_code, 302)

    def test_logout_get_not_allowed(self):
        response = self.client.get(reverse('logout'))
        self.assertIn(response.status_code, [405, 302])
