"""Registration, sign-in with lockout, e-mail verification and password reset (REQ-AC-1..6)."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from django.conf import settings
from django.db import transaction

from intelliflow.accounts.models import User, UserToken
from intelliflow.accounts.tokens import TokenPair, issue_pair, user_from_token
from intelliflow.audit import services as audit_service
from intelliflow.core.enums import MembershipStatus, TokenPurpose, WorkspaceStatus
from intelliflow.core.errors import (
    AuthenticationError,
    ConflictError,
    PermissionDeniedError,
    RateLimitedError,
    ValidationFailedError,
)
from intelliflow.core.kv import get_kv
from intelliflow.core.models import utcnow
from intelliflow.core.security import (
    burn_password_check,
    generate_url_token,
    hash_url_token,
    validate_password_strength,
)
from intelliflow.notifications.email import queue_email
from intelliflow.workspaces.models import Membership

logger = logging.getLogger(__name__)


def normalize_email(email: str) -> str:
    return email.strip().lower()


class AuthService:
    # ------------------------------------------------------------------ register
    @transaction.atomic
    def register(self, data: dict[str, Any], ip: str | None = None) -> User:
        email = normalize_email(data["email"])
        validate_password_strength(data["password"])
        if User.objects.filter(email=email).exists():
            raise ConflictError(
                "An account with this e-mail already exists.",
                code="email_taken",
                hint="Sign in, or use 'Forgot password' to reset it.",
            )
        phone = data.get("phone")
        user = User(
            full_name=data["full_name"].strip(),
            email=email,
            phone=phone.strip() if phone else None,
        )
        user.set_password(data["password"])  # Argon2id (SEC-1)
        user.save()
        self._send_verification(user)
        audit_service.record(
            "user.registered",
            actor_id=user.id,
            entity_type="user",
            entity_id=user.id,
            ip_address=ip,
        )
        return user

    def _issue_user_token(self, user: User, purpose: TokenPurpose, ttl: timedelta) -> str:
        token, token_hash = generate_url_token()
        UserToken.objects.create(
            user=user, purpose=purpose, token_hash=token_hash, expires_at=utcnow() + ttl
        )
        return token

    def _send_verification(self, user: User) -> None:
        token = self._issue_user_token(
            user, TokenPurpose.VERIFY_EMAIL, timedelta(hours=settings.EMAIL_TOKEN_TTL_HOURS)
        )
        link = f"{settings.FRONTEND_URL}/verify-email?token={token}"
        queue_email(
            to=user.email,
            subject="Verify your IntelliFlow e-mail address",
            body=f"Assalam o Alaikum {user.full_name},\n\nPlease confirm your e-mail address to "
            f"start using IntelliFlow:\n{link}\n\nThis link expires in "
            f"{settings.EMAIL_TOKEN_TTL_HOURS} hours.",
            category="verify_email",
        )

    def _consume_token(self, token: str, purpose: TokenPurpose) -> UserToken:
        record = (
            UserToken.objects.select_for_update()
            .filter(token_hash=hash_url_token(token), purpose=purpose)
            .first()
        )
        if record is None or record.used_at is not None or record.expires_at < utcnow():
            raise ValidationFailedError(
                "This link is invalid or has expired.",
                code="invalid_link",
                hint="Request a new link and try again.",
            )
        record.used_at = utcnow()
        record.save(update_fields=["used_at"])
        return record

    @transaction.atomic
    def verify_email(self, token: str) -> User:
        record = self._consume_token(token, TokenPurpose.VERIFY_EMAIL)
        user = User.objects.get(pk=record.user_id)
        user.email_verified = True
        user.save(update_fields=["email_verified"])
        audit_service.record(
            "user.email_verified", actor_id=user.id, entity_type="user", entity_id=user.id
        )
        return user

    @transaction.atomic
    def resend_verification(self, email: str) -> None:
        user = User.objects.filter(email=normalize_email(email)).first()
        if user and not user.email_verified:  # silent otherwise: no account enumeration
            self._send_verification(user)

    # ------------------------------------------------------------------ sign in
    def _check_ip_rate_limit(self, ip: str | None) -> None:
        if not ip:
            return
        minute = int(datetime.now(UTC).timestamp() // 60)
        count = get_kv().incr(f"rl:login:{ip}:{minute}", ttl_seconds=90)
        if count > settings.LOGIN_RATE_LIMIT_PER_MINUTE:
            raise RateLimitedError(
                "Too many sign-in attempts from this network. Please wait a minute and try again."
            )

    def login(self, email: str, password: str, ip: str | None = None) -> tuple[User, TokenPair]:
        self._check_ip_rate_limit(ip)
        user = User.objects.filter(email=normalize_email(email)).first()
        invalid = AuthenticationError("Incorrect e-mail or password.", code="invalid_credentials")
        if user is None:
            burn_password_check(password)  # constant-ish timing for unknown accounts
            raise invalid
        now = utcnow()
        if user.locked_until and user.locked_until > now:
            minutes = max(1, int((user.locked_until - now).total_seconds() // 60) + 1)
            raise AuthenticationError(
                f"Too many failed attempts. Your account is locked for about {minutes} more minute(s).",
                code="account_locked",
                hint="Wait and try again, or reset your password.",
            )
        # check_password also upgrades the stored hash if the hasher settings changed.
        if not user.check_password(password):
            # Saved (autocommit) before raising: failed attempts must survive the error.
            user.failed_login_attempts += 1
            if user.failed_login_attempts >= settings.MAX_FAILED_LOGINS:  # REQ-AC-2
                user.locked_until = now + timedelta(minutes=settings.LOCKOUT_MINUTES)
                user.failed_login_attempts = 0
                audit_service.record(
                    "user.locked",
                    actor_id=user.id,
                    entity_type="user",
                    entity_id=user.id,
                    ip_address=ip,
                )
            user.save(update_fields=["failed_login_attempts", "locked_until"])
            raise invalid
        if not user.email_verified:  # REQ-AC-1
            raise AuthenticationError(
                "Please verify your e-mail address before signing in.",
                code="email_not_verified",
                hint="Check your inbox, or request a new verification link.",
            )
        self._ensure_not_fully_suspended(user)
        with transaction.atomic():
            user.failed_login_attempts = 0
            user.locked_until = None
            user.last_login = now
            user.save(update_fields=["failed_login_attempts", "locked_until", "last_login"])
            audit_service.record(
                "user.signed_in",
                actor_id=user.id,
                entity_type="user",
                entity_id=user.id,
                ip_address=ip,
            )
        return user, issue_pair(user)

    def _ensure_not_fully_suspended(self, user: User) -> None:
        memberships = list(
            Membership.objects.select_related("workspace").filter(
                user=user, status=MembershipStatus.ACTIVE
            )
        )
        if (
            memberships
            and not user.is_platform_admin
            and all(m.workspace.status == WorkspaceStatus.SUSPENDED for m in memberships)
        ):
            raise PermissionDeniedError(
                "Your workspace has been suspended. Please contact IntelliFlow support.",
                code="workspace_suspended",
            )

    def refresh(self, refresh_token: str) -> tuple[User, TokenPair]:
        user = user_from_token(refresh_token, "refresh")
        return user, issue_pair(user)  # rotation: a new refresh token every time

    @transaction.atomic
    def logout_all(self, user: User) -> None:
        user.token_version += 1
        user.save(update_fields=["token_version"])
        audit_service.record(
            "user.signed_out_everywhere", actor_id=user.id, entity_type="user", entity_id=user.id
        )

    # ------------------------------------------------------------------ password reset
    @transaction.atomic
    def forgot_password(self, email: str) -> None:
        user = User.objects.filter(email=normalize_email(email)).first()
        if user is None:
            return  # no enumeration
        token = self._issue_user_token(
            user,
            TokenPurpose.RESET_PASSWORD,
            timedelta(minutes=settings.PASSWORD_RESET_TTL_MINUTES),
        )
        link = f"{settings.FRONTEND_URL}/reset-password?token={token}"
        queue_email(
            to=user.email,
            subject="Reset your IntelliFlow password",
            body=f"Someone asked to reset your IntelliFlow password.\n\nReset it here: {link}\n\n"
            f"This link expires in {settings.PASSWORD_RESET_TTL_MINUTES} minutes. "
            "If you did not ask for this, you can ignore this e-mail.",
            category="reset_password",
        )

    @transaction.atomic
    def reset_password(self, token: str, new_password: str) -> None:
        validate_password_strength(new_password)
        record = self._consume_token(token, TokenPurpose.RESET_PASSWORD)
        user = User.objects.get(pk=record.user_id)
        user.set_password(new_password)
        user.token_version += 1  # revoke every existing session
        user.failed_login_attempts = 0
        user.locked_until = None
        user.email_verified = True  # proven control of the mailbox
        user.save()
        audit_service.record(
            "user.password_reset", actor_id=user.id, entity_type="user", entity_id=user.id
        )
