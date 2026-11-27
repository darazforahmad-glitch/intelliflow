"""Request validation and response shapes for /api/v1/auth (UC-01)."""

from __future__ import annotations

from typing import Any

from rest_framework import serializers

from intelliflow.accounts.models import User
from intelliflow.core.enums import MembershipStatus

PHONE_PATTERN = r"^\+?[0-9][0-9\s-]{6,19}$"


class RegisterSerializer(serializers.Serializer):
    full_name = serializers.CharField(min_length=2, max_length=100)
    email = serializers.EmailField()
    phone = serializers.RegexField(PHONE_PATTERN, required=False, allow_null=True)
    password = serializers.CharField(min_length=8, max_length=128, trim_whitespace=False)


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(min_length=1, max_length=128, trim_whitespace=False)


class RefreshSerializer(serializers.Serializer):
    refresh_token = serializers.CharField()


class EmailSerializer(serializers.Serializer):
    email = serializers.EmailField()


class TokenSerializer(serializers.Serializer):
    token = serializers.CharField(min_length=10, max_length=200)


class ResetPasswordSerializer(serializers.Serializer):
    token = serializers.CharField(min_length=10, max_length=200)
    new_password = serializers.CharField(min_length=8, max_length=128, trim_whitespace=False)


class UpdateMeSerializer(serializers.Serializer):
    full_name = serializers.CharField(min_length=2, max_length=100, required=False, allow_null=True)
    phone = serializers.RegexField(PHONE_PATTERN, required=False, allow_null=True)


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = [
            "id",
            "full_name",
            "email",
            "phone",
            "email_verified",
            "is_platform_admin",
            "created_at",
        ]


class MeSerializer(UserSerializer):
    memberships = serializers.SerializerMethodField()

    class Meta(UserSerializer.Meta):
        fields = [*UserSerializer.Meta.fields, "memberships"]

    def get_memberships(self, user: User) -> list[dict[str, Any]]:
        memberships = (
            user.memberships.select_related("workspace")
            .exclude(status=MembershipStatus.REMOVED)
            .filter(workspace__deleted_at__isnull=True)
            .order_by("created_at")
        )
        return [
            {
                "membership_id": str(m.id),
                "workspace_id": str(m.workspace_id),
                "workspace_name": m.workspace.name,
                "role": m.role,
                "status": m.status,
                "workspace_status": m.workspace.status,
            }
            for m in memberships
        ]


def token_pair(user: User, tokens: Any) -> dict[str, Any]:
    return {
        "access_token": tokens.access_token,
        "refresh_token": tokens.refresh_token,
        "token_type": "bearer",
        "expires_in": tokens.expires_in,
        "user": UserSerializer(user).data,
    }
