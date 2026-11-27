"""Request validation and response shapes for workspaces, team and invitations."""

from __future__ import annotations

from typing import Any
from zoneinfo import available_timezones

from rest_framework import serializers

from intelliflow.workspaces.models import Invitation, Workspace

LANGUAGES = ["en", "ur", "roman-ur"]
_TIMEZONES = available_timezones()


def _check_timezone(value: str | None) -> str | None:
    if value is not None and value not in _TIMEZONES:
        raise serializers.ValidationError("Unknown timezone, e.g. use Asia/Karachi")
    return value


class WorkspaceCreateSerializer(serializers.Serializer):
    name = serializers.CharField(min_length=2, max_length=120)
    business_type = serializers.CharField(
        max_length=60, required=False, allow_null=True, allow_blank=True
    )
    language_pref = serializers.ChoiceField(LANGUAGES, default="en")
    timezone = serializers.CharField(default="Asia/Karachi", validators=[_check_timezone])


class WorkspaceUpdateSerializer(serializers.Serializer):
    name = serializers.CharField(min_length=2, max_length=120, required=False, allow_null=True)
    business_type = serializers.CharField(
        max_length=60, required=False, allow_null=True, allow_blank=True
    )
    language_pref = serializers.ChoiceField(LANGUAGES, required=False, allow_null=True)
    timezone = serializers.CharField(required=False, allow_null=True, validators=[_check_timezone])
    approval_threshold = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        min_value=0,
        max_value=100_000_000,
        required=False,
        allow_null=True,
    )


class WorkspaceSerializer(serializers.ModelSerializer):
    role = serializers.SerializerMethodField()

    class Meta:
        model = Workspace
        fields = [
            "id",
            "name",
            "business_type",
            "language_pref",
            "timezone",
            "status",
            "approval_threshold",
            "currency",
            "ai_credit_limit",
            "created_at",
            "role",
        ]

    def get_role(self, _workspace: Workspace) -> str | None:
        role = self.context.get("role")
        return str(role) if role is not None else None


class InvitationCreateSerializer(serializers.Serializer):
    email = serializers.EmailField()
    role = serializers.ChoiceField(["staff"], default="staff")


class InvitationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Invitation
        fields = ["id", "email", "role", "expires_at", "accepted_at", "revoked_at", "created_at"]


def member_out(membership: Any, user: Any) -> dict[str, Any]:
    return {
        "membership_id": str(membership.id),
        "user_id": str(user.id),
        "full_name": user.full_name,
        "email": user.email,
        "role": membership.role,
        "status": membership.status,
        "joined_at": serializers.DateTimeField().to_representation(membership.created_at),
    }
