"""URL routes: the versioned REST API under /api/v1 (Section 5.5), OpenAPI docs,
health probes and the Django admin site used for Platform Admin."""

from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularRedocView, SpectacularSwaggerView

from intelliflow.core.api.views import healthz, readyz

urlpatterns = [
    path("healthz", healthz),
    path("readyz", readyz),
    path("api/v1/", include("config.api_urls")),
    path("api/v1/openapi.json", SpectacularAPIView.as_view(), name="openapi-schema"),
    path("api/docs", SpectacularSwaggerView.as_view(url_name="openapi-schema"), name="api-docs"),
    path("api/redoc", SpectacularRedocView.as_view(url_name="openapi-schema"), name="api-redoc"),
    path("admin/", admin.site.urls),
]
