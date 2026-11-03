from django.contrib.auth.views import LoginView

from .forms import LoginForm


class ERPLoginView(LoginView):
    max_error_growth_steps = 10
    template_name = "purchasing/login.html"
    authentication_form = LoginForm

    def form_invalid(self, form):
        # Track consecutive authentication failures in this browser session.
        # Missing required fields are not incorrect credentials.
        if form.has_error("__all__", "invalid_login") or form.has_error("__all__", "inactive"):
            self.request.session["login_failures"] = min(
                self.request.session.get("login_failures", 0) + 1,
                self.max_error_growth_steps + 1,
            )
        return super().form_invalid(form)

    def form_valid(self, form):
        self.request.session.pop("login_failures", None)
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        failures = self.request.session.get("login_failures", 0)
        growth_steps = min(max(0, failures - 1), self.max_error_growth_steps)
        context["login_error_size"] = 100 + growth_steps * 20
        return context
