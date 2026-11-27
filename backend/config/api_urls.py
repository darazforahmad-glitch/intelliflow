"""Every resource is a plural noun under /api/v1 (Section 5.5). Each app owns its routes."""

from django.urls import include, path

urlpatterns = [
    path("", include(f"intelliflow.{app}.urls"))
    for app in (
        "accounts",
        "workspaces",
        "flowmapper",
        "opportunities",
        "automations",
        "runs",
        "approvals",
        "integrations",
        "dashboard",
        "notifications",
        "platform_admin",
    )
]
