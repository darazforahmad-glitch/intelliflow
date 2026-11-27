"""Replaces Django's default admin site with the IntelliFlow Platform Admin site.

Kept in its own module: Django imports it while the app registry is still loading."""

from django.contrib.admin.apps import AdminConfig


class IntelliFlowAdminConfig(AdminConfig):
    default_site = "intelliflow.platform_admin.admin_site.PlatformAdminSite"
