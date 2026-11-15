from django.contrib.auth import login
from django.contrib.auth.views import LoginView, LogoutView
from django.http import HttpResponseNotAllowed
from django.shortcuts import redirect, render
from django.urls import reverse_lazy
from django.views import View

from .forms import RegisterForm


class RegisterView(View):
    """Create a user account and log the user in."""

    template_name = "accounts/register.html"

    def get(self, request):
        if request.user.is_authenticated:
            return redirect("index")
        return render(request, self.template_name, {"form": RegisterForm()})

    def post(self, request):
        form = RegisterForm(request.POST)
        if not form.is_valid():
            return render(request, self.template_name, {"form": form}, status=400)

        user = form.save(commit=False)
        user.set_password(form.cleaned_data["password"])
        user.save()
        login(request, user)
        return redirect("index")


class CustomLoginView(LoginView):
    template_name = "accounts/login.html"
    redirect_authenticated_user = True


class CustomLogoutView(LogoutView):
    """POST-only logout (GET returns 405)."""

    next_page = reverse_lazy("login")

    def get(self, request, *args, **kwargs):
        return HttpResponseNotAllowed(["POST"])  # type: ignore[return-value]
