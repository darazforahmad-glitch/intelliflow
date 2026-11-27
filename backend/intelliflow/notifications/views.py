"""In-app notifications and Web Push subscriptions for the PWA (REQ-AP-2), plus the
development e-mail inbox."""

from __future__ import annotations

from typing import Any

from django.conf import settings
from rest_framework import serializers, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from intelliflow.core.api.permissions import message
from intelliflow.core.api.viewsets import UUID_REGEX
from intelliflow.core.models import utcnow
from intelliflow.notifications.models import EmailMessage, Notification, PushSubscription


class NotificationQuerySerializer(serializers.Serializer):
    unread_only = serializers.BooleanField(default=False)
    limit = serializers.IntegerField(default=30)


class PushKeysSerializer(serializers.Serializer):
    p256dh = serializers.CharField(min_length=10, max_length=255)
    auth = serializers.CharField(min_length=8, max_length=255)


class PushSubscriptionSerializer(serializers.Serializer):
    endpoint = serializers.RegexField(r"^https://", min_length=10, max_length=2000)
    keys = PushKeysSerializer()


class EndpointSerializer(serializers.Serializer):
    endpoint = serializers.CharField()


def _valid(serializer_class: type, data: Any) -> dict[str, Any]:
    body = serializer_class(data=data)
    body.is_valid(raise_exception=True)
    return dict(body.validated_data)


class NotificationViewSet(viewsets.ViewSet):
    lookup_value_regex = UUID_REGEX

    def list(self, request: Request) -> Response:
        query = _valid(NotificationQuerySerializer, request.query_params)
        mine = Notification.objects.filter(user=request.user)
        items = mine.filter(read_at__isnull=True) if query["unread_only"] else mine
        items = items.order_by("-created_at")[: min(query["limit"], 100)]
        return Response(
            {
                "unread": mine.filter(read_at__isnull=True).count(),
                "items": [
                    {
                        "id": str(n.id),
                        "kind": n.kind,
                        "title": n.title,
                        "body": n.body,
                        "url": n.url,
                        "workspace_id": str(n.workspace_id) if n.workspace_id else None,
                        "read": n.read_at is not None,
                        "created_at": n.created_at.isoformat(),
                    }
                    for n in items
                ],
            }
        )

    @action(detail=True, methods=["post"])
    def read(self, request: Request, pk: str) -> Response:
        Notification.objects.filter(pk=pk, user=request.user, read_at__isnull=True).update(
            read_at=utcnow()
        )
        return Response(message("Marked as read."))

    @action(detail=False, methods=["post"], url_path="read-all")
    def read_all(self, request: Request) -> Response:
        Notification.objects.filter(user=request.user, read_at__isnull=True).update(
            read_at=utcnow()
        )
        return Response(message("All notifications marked as read."))


class PushViewSet(viewsets.ViewSet):
    @action(detail=False, methods=["get"])
    def config(self, request: Request) -> Response:
        return Response(
            {"enabled": settings.WEB_PUSH_ENABLED, "vapid_public_key": settings.VAPID_PUBLIC_KEY}
        )

    @action(detail=False, methods=["post", "delete"])
    def subscriptions(self, request: Request) -> Response:
        if request.method == "DELETE":
            endpoint = _valid(EndpointSerializer, request.data)["endpoint"]
            PushSubscription.objects.filter(endpoint=endpoint, user=request.user).delete()
            return Response(message("Push notifications turned off for this device."))
        data = _valid(PushSubscriptionSerializer, request.data)
        PushSubscription.objects.update_or_create(
            endpoint=data["endpoint"],
            defaults={
                "user": request.user,
                "p256dh": data["keys"]["p256dh"],
                "auth": data["keys"]["auth"],
                "user_agent": (request.headers.get("user-agent") or "")[:255],
            },
        )
        return Response(message("This device will receive approval alerts."))


class DevOutboxQuerySerializer(serializers.Serializer):
    to = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    limit = serializers.IntegerField(min_value=1, max_value=100, default=20)


class DevOutboxView(APIView):
    """The console e-mail backend's 'inbox', so verification links work without SMTP.
    Mounted only when ENVIRONMENT is development or test."""

    authentication_classes: list[Any] = []
    permission_classes = [AllowAny]

    def get(self, request: Request) -> Response:
        query = _valid(DevOutboxQuerySerializer, request.query_params)
        messages = EmailMessage.objects.all()
        if query.get("to"):
            messages = messages.filter(to_address=query["to"].strip().lower())
        return Response(
            [
                {
                    "id": str(m.id),
                    "to": m.to_address,
                    "subject": m.subject,
                    "body": m.body_text,
                    "category": m.category,
                    "created_at": m.created_at.isoformat(),
                }
                for m in messages.order_by("-created_at")[: query["limit"]]
            ]
        )
