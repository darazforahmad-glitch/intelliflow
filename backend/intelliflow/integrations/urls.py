from django.urls import path
from rest_framework.routers import SimpleRouter

from intelliflow.core.api.viewsets import UUID_REGEX, WORKSPACE_PREFIX
from intelliflow.integrations.views import (
    ConnectionViewSet,
    GoogleCallbackView,
    WebformWebhookView,
    WhatsAppWebhookView,
)

router = SimpleRouter(trailing_slash=False)
router.register(f"{WORKSPACE_PREFIX}/connections", ConnectionViewSet, basename="connection")

urlpatterns = [
    path("webhooks/whatsapp", WhatsAppWebhookView.as_view()),
    path("webhooks/webform/<uuid:connection_id>/<str:token>", WebformWebhookView.as_view()),
    path("oauth/google/callback", GoogleCallbackView.as_view()),
    *router.urls,
]

__all__ = ["UUID_REGEX", "urlpatterns"]
