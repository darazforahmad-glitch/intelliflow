"""/api/v1/auth: registration, verification, sign-in, tokens and password reset (UC-01)."""

from __future__ import annotations

from typing import Any

from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from intelliflow.accounts import serializers as s
from intelliflow.accounts.services import AuthService
from intelliflow.core.api.permissions import message
from intelliflow.core.middleware import client_ip


def _valid(serializer_class: type, request: Request) -> dict[str, Any]:
    serializer = serializer_class(data=request.data)
    serializer.is_valid(raise_exception=True)
    return dict(serializer.validated_data)


class AuthViewSet(viewsets.ViewSet):
    permission_classes = [AllowAny]
    service = AuthService()

    def get_permissions(self):  # type: ignore[no-untyped-def]
        if self.action in {"me", "logout_all"}:
            return [IsAuthenticated()]
        return super().get_permissions()

    @action(detail=False, methods=["post"])
    def register(self, request: Request) -> Response:
        self.service.register(_valid(s.RegisterSerializer, request), ip=client_ip(request))
        return Response(
            message("Account created. Please check your e-mail to verify your address."),
            status=status.HTTP_201_CREATED,
        )

    @action(detail=False, methods=["post"], url_path="verify-email")
    def verify_email(self, request: Request) -> Response:
        self.service.verify_email(_valid(s.TokenSerializer, request)["token"])
        return Response(message("Your e-mail address is verified. You can sign in now."))

    @action(detail=False, methods=["post"], url_path="resend-verification")
    def resend_verification(self, request: Request) -> Response:
        self.service.resend_verification(_valid(s.EmailSerializer, request)["email"])
        return Response(
            message("If the account exists and is not verified yet, we sent a new link."),
            status=status.HTTP_202_ACCEPTED,
        )

    @action(detail=False, methods=["post"])
    def login(self, request: Request) -> Response:
        data = _valid(s.LoginSerializer, request)
        user, tokens = self.service.login(data["email"], data["password"], ip=client_ip(request))
        return Response(s.token_pair(user, tokens))

    @action(detail=False, methods=["post"])
    def refresh(self, request: Request) -> Response:
        user, tokens = self.service.refresh(_valid(s.RefreshSerializer, request)["refresh_token"])
        return Response(s.token_pair(user, tokens))

    @action(detail=False, methods=["post"], url_path="logout-all")
    def logout_all(self, request: Request) -> Response:
        self.service.logout_all(request.user)
        return Response(message("You have been signed out on every device."))

    @action(detail=False, methods=["post"], url_path="forgot-password")
    def forgot_password(self, request: Request) -> Response:
        self.service.forgot_password(_valid(s.EmailSerializer, request)["email"])
        return Response(
            message(
                "If an account exists for this e-mail, we sent a reset link. It expires in 30 minutes."
            ),
            status=status.HTTP_202_ACCEPTED,
        )

    @action(detail=False, methods=["post"], url_path="reset-password")
    def reset_password(self, request: Request) -> Response:
        data = _valid(s.ResetPasswordSerializer, request)
        self.service.reset_password(data["token"], data["new_password"])
        return Response(
            message("Your password has been changed. Please sign in with the new password.")
        )

    @action(detail=False, methods=["get", "patch"])
    def me(self, request: Request) -> Response:
        user = request.user
        if request.method == "PATCH":
            changes = s.UpdateMeSerializer(data=request.data, partial=True)
            changes.is_valid(raise_exception=True)
            for field, value in changes.validated_data.items():
                if field == "full_name" and value is None:
                    continue  # a name is required; null means "leave unchanged"
                setattr(user, field, value.strip() if isinstance(value, str) else value)
            user.save()
        return Response(s.MeSerializer(user).data)
