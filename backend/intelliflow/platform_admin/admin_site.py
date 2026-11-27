"""The Django admin site as IntelliFlow's Platform Admin interface (Section 4.1).

Platform admins (users with is_platform_admin) manage templates (REQ-PA-1), see platform
metrics (REQ-PA-2), set AI credit limits (REQ-PA-3), suspend or reactivate workspaces
(REQ-PA-4) and read the audit log (REQ-PA-5). Sign-in goes through the same rules as
the web app: lockout after failed attempts and a per-IP rate limit (REQ-AC-2, SEC-7).
Message content is never shown here (BR-8).
"""

from __future__ import annotations

from typing import Any

from django.contrib.admin import AdminSite
from django.contrib.admin.forms import AdminAuthenticationForm
from django.core.exceptions import ValidationError
from django.http import HttpRequest
from django.template.response import TemplateResponse

from intelliflow.core.errors import AppError
from intelliflow.core.middleware import client_ip


class PlatformAdminLoginForm(AdminAuthenticationForm):
    def clean(self) -> dict[str, Any]:
        from intelliflow.accounts.services import AuthService

        email = self.cleaned_data.get("username")
        password = self.cleaned_data.get("password")
        if email and password:
            try:
                user, _tokens = AuthService().login(email, password, ip=client_ip(self.request))
            except AppError as exc:
                raise ValidationError(exc.message, code=exc.code) from exc
            self.confirm_login_allowed(user)  # platform admins only
            self.user_cache = user
        return self.cleaned_data


class PlatformAdminSite(AdminSite):
    site_header = "IntelliFlow Platform Admin"
    site_title = "IntelliFlow admin"
    index_title = "Platform overview"
    index_template = "admin/platform/index.html"
    login_form = PlatformAdminLoginForm

    def index(
        self, request: HttpRequest, extra_context: dict[str, Any] | None = None
    ) -> TemplateResponse:
        from intelliflow.platform_admin.services import metrics

        data = metrics()
        peak = max((d["runs"] for d in data["runs_per_day"]), default=0) or 1
        for day in data["runs_per_day"]:
            day["height"] = round(day["runs"] / peak * 100)
        return super().index(request, {**(extra_context or {}), "metrics": data})
