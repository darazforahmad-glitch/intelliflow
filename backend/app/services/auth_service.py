"""Registration, sign-in with lockout, e-mail verification and password reset (REQ-AC-1..6)."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import (
    AuthenticationError,
    ConflictError,
    PermissionDeniedError,
    RateLimitedError,
    ValidationFailedError,
)
from app.core.kv import get_kv
from app.core.security import (
    burn_password_check,
    create_token,
    decode_token,
    generate_url_token,
    hash_password,
    hash_url_token,
    password_needs_rehash,
    validate_password_strength,
    verify_password,
)
from app.models import Membership, User, UserToken
from app.models.base import utcnow
from app.models.enums import MembershipStatus, TokenPurpose, WorkspaceStatus
from app.schemas.auth import RegisterRequest
from app.services import audit_service
from app.services.email_service import queue_email

logger = logging.getLogger(__name__)


def normalize_email(email: str) -> str:
    return email.strip().lower()


@dataclass(frozen=True, slots=True)
class IssuedTokens:
    access_token: str
    refresh_token: str
    expires_in: int


class AuthService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.settings = get_settings()

    # ------------------------------------------------------------------ register
    def register(self, data: RegisterRequest, ip: str | None = None) -> User:
        email = normalize_email(data.email)
        validate_password_strength(data.password)
        if self.db.scalar(select(User.id).where(User.email == email)):
            raise ConflictError(
                "An account with this e-mail already exists.",
                code="email_taken",
                hint="Sign in, or use 'Forgot password' to reset it.",
            )
        user = User(
            full_name=data.full_name.strip(),
            email=email,
            phone=data.phone.strip() if data.phone else None,
            password_hash=hash_password(data.password),
        )
        self.db.add(user)
        self.db.flush()
        self._send_verification(user)
        audit_service.record(
            self.db,
            "user.registered",
            actor_id=user.id,
            entity_type="user",
            entity_id=user.id,
            ip_address=ip,
        )
        self.db.commit()
        return user

    def _issue_user_token(self, user: User, purpose: TokenPurpose, ttl: timedelta) -> str:
        token, token_hash = generate_url_token()
        self.db.add(
            UserToken(
                user_id=user.id, purpose=purpose, token_hash=token_hash, expires_at=utcnow() + ttl
            )
        )
        return token

    def _send_verification(self, user: User) -> None:
        token = self._issue_user_token(
            user, TokenPurpose.VERIFY_EMAIL, timedelta(hours=self.settings.email_token_ttl_hours)
        )
        link = f"{self.settings.frontend_url}/verify-email?token={token}"
        queue_email(
            self.db,
            to=user.email,
            subject="Verify your IntelliFlow e-mail address",
            body=f"Assalam o Alaikum {user.full_name},\n\nPlease confirm your e-mail address to "
            f"start using IntelliFlow:\n{link}\n\nThis link expires in "
            f"{self.settings.email_token_ttl_hours} hours.",
            category="verify_email",
        )

    def _consume_token(self, token: str, purpose: TokenPurpose) -> UserToken:
        record = self.db.scalar(
            select(UserToken).where(
                UserToken.token_hash == hash_url_token(token), UserToken.purpose == purpose
            )
        )
        if record is None or record.used_at is not None or record.expires_at < utcnow():
            raise ValidationFailedError(
                "This link is invalid or has expired.",
                code="invalid_link",
                hint="Request a new link and try again.",
            )
        record.used_at = utcnow()
        return record

    def verify_email(self, token: str) -> User:
        record = self._consume_token(token, TokenPurpose.VERIFY_EMAIL)
        user = self.db.get_one(User, record.user_id)
        user.email_verified = True
        audit_service.record(
            self.db, "user.email_verified", actor_id=user.id, entity_type="user", entity_id=user.id
        )
        self.db.commit()
        return user

    def resend_verification(self, email: str) -> None:
        user = self.db.scalar(select(User).where(User.email == normalize_email(email)))
        if user and not user.email_verified:  # silent otherwise: no account enumeration
            self._send_verification(user)
            self.db.commit()

    # ------------------------------------------------------------------ sign in
    def _check_ip_rate_limit(self, ip: str | None) -> None:
        if not ip:
            return
        minute = int(datetime.now(UTC).timestamp() // 60)
        count = get_kv().incr(f"rl:login:{ip}:{minute}", ttl_seconds=90)
        if count > self.settings.login_rate_limit_per_minute:
            raise RateLimitedError(
                "Too many sign-in attempts from this network. Please wait a minute and try again."
            )

    def login(self, email: str, password: str, ip: str | None = None) -> tuple[User, IssuedTokens]:
        self._check_ip_rate_limit(ip)
        user = self.db.scalar(select(User).where(User.email == normalize_email(email)))
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
        if not verify_password(user.password_hash, password):
            user.failed_login_attempts += 1
            if user.failed_login_attempts >= self.settings.max_failed_logins:  # REQ-AC-2
                user.locked_until = now + timedelta(minutes=self.settings.lockout_minutes)
                user.failed_login_attempts = 0
                audit_service.record(
                    self.db,
                    "user.locked",
                    actor_id=user.id,
                    entity_type="user",
                    entity_id=user.id,
                    ip_address=ip,
                )
            self.db.commit()
            raise invalid
        if not user.email_verified:  # REQ-AC-1
            raise AuthenticationError(
                "Please verify your e-mail address before signing in.",
                code="email_not_verified",
                hint="Check your inbox, or request a new verification link.",
            )
        self._ensure_not_fully_suspended(user)
        user.failed_login_attempts = 0
        user.locked_until = None
        user.last_login_at = now
        if password_needs_rehash(user.password_hash):
            user.password_hash = hash_password(password)
        audit_service.record(
            self.db,
            "user.signed_in",
            actor_id=user.id,
            entity_type="user",
            entity_id=user.id,
            ip_address=ip,
        )
        self.db.commit()
        return user, self.issue_tokens(user)

    def _ensure_not_fully_suspended(self, user: User) -> None:
        memberships = self.db.scalars(
            select(Membership).where(
                Membership.user_id == user.id, Membership.status == MembershipStatus.ACTIVE
            )
        ).all()
        if (
            memberships
            and not user.is_platform_admin
            and all(m.workspace.status == WorkspaceStatus.SUSPENDED for m in memberships)
        ):
            raise PermissionDeniedError(
                "Your workspace has been suspended. Please contact IntelliFlow support.",
                code="workspace_suspended",
            )

    def issue_tokens(self, user: User) -> IssuedTokens:
        access, access_exp = create_token(user.id, user.token_version, "access")
        refresh, _ = create_token(user.id, user.token_version, "refresh")
        return IssuedTokens(access, refresh, int((access_exp - utcnow()).total_seconds()))

    def refresh(self, refresh_token: str) -> tuple[User, IssuedTokens]:
        claims = decode_token(refresh_token, "refresh")
        user = self.db.get(User, claims.user_id)
        if user is None or user.token_version != claims.token_version:
            raise AuthenticationError(
                "Your session has ended. Please sign in again.", code="session_revoked"
            )
        return user, self.issue_tokens(user)

    def logout_all(self, user: User) -> None:
        user.token_version += 1
        audit_service.record(
            self.db,
            "user.signed_out_everywhere",
            actor_id=user.id,
            entity_type="user",
            entity_id=user.id,
        )
        self.db.commit()

    # ------------------------------------------------------------------ password reset
    def forgot_password(self, email: str) -> None:
        user = self.db.scalar(select(User).where(User.email == normalize_email(email)))
        if user is None:
            return  # no enumeration
        token = self._issue_user_token(
            user,
            TokenPurpose.RESET_PASSWORD,
            timedelta(minutes=self.settings.password_reset_ttl_minutes),
        )
        link = f"{self.settings.frontend_url}/reset-password?token={token}"
        queue_email(
            self.db,
            to=user.email,
            subject="Reset your IntelliFlow password",
            body=f"Someone asked to reset your IntelliFlow password.\n\nReset it here: {link}\n\n"
            f"This link expires in {self.settings.password_reset_ttl_minutes} minutes. "
            "If you did not ask for this, you can ignore this e-mail.",
            category="reset_password",
        )
        self.db.commit()

    def reset_password(self, token: str, new_password: str) -> None:
        validate_password_strength(new_password)
        record = self._consume_token(token, TokenPurpose.RESET_PASSWORD)
        user = self.db.get_one(User, record.user_id)
        user.password_hash = hash_password(new_password)
        user.token_version += 1  # revoke every existing session
        user.failed_login_attempts = 0
        user.locked_until = None
        user.email_verified = True  # proven control of the mailbox
        audit_service.record(
            self.db, "user.password_reset", actor_id=user.id, entity_type="user", entity_id=user.id
        )
        self.db.commit()
