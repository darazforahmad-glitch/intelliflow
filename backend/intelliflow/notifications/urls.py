from django.conf import settings
from django.urls import path
from rest_framework.routers import SimpleRouter

from intelliflow.notifications.views import DevOutboxView, NotificationViewSet, PushViewSet

router = SimpleRouter(trailing_slash=False)
router.register("notifications", NotificationViewSet, basename="notification")
router.register("push", PushViewSet, basename="push")

urlpatterns = list(router.urls)
if settings.IS_DEV_LIKE:
    urlpatterns.append(path("dev/outbox", DevOutboxView.as_view()))
