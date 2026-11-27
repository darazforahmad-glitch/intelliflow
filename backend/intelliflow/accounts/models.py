"""Users (Table 4.1) and single-use e-mail tokens.

`User` is Django's custom user model: e-mail is the username, the password is an
Argon2id hash (SEC-1) kept in the `password_hash` column, and platform admins are
allowed into the Django admin site (Platform Admin module).
"""

from __future__ import annotations

from typing import Any, ClassVar

from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.db import models

from intelliflow.core.enums import TokenPurpose
from intelliflow.core.models import CreatedModel, choices_check


class UserManager(BaseUserManager["User"]):
    use_in_migrations = True

    def create_user(self, email: str, password: str | None = None, **extra: Any) -> User:
        user = self.model(email=email.strip().lower(), **extra)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email: str, password: str | None = None, **extra: Any) -> User:
        extra.setdefault("full_name", "Platform Admin")
        extra.update(is_platform_admin=True, email_verified=True)
        return self.create_user(email, password, **extra)


class User(AbstractBaseUser, CreatedModel):
    full_name = models.CharField(max_length=100)
    email = models.CharField(max_length=255, unique=True)  # stored lower-case
    phone = models.CharField(max_length=20, null=True, blank=True)
    password = models.CharField(max_length=255, db_column="password_hash")  # Argon2id (SEC-1)
    email_verified = models.BooleanField(default=False)
    # --- extensions to Table 4.1 needed by REQ-AC-2/REQ-AC-4 and session revocation ---
    is_platform_admin = models.BooleanField(default=False)
    failed_login_attempts = models.SmallIntegerField(default=0)
    locked_until = models.DateTimeField(null=True, blank=True)
    token_version = models.IntegerField(default=0)
    last_login = models.DateTimeField(null=True, blank=True, db_column="last_login_at")

    objects: ClassVar[UserManager] = UserManager()

    USERNAME_FIELD = "email"
    EMAIL_FIELD = "email"
    REQUIRED_FIELDS: ClassVar[list[str]] = ["full_name"]

    class Meta:
        db_table = "users"

    def __str__(self) -> str:  # never include PII beyond the id
        return f"User {self.id}"

    # --- Django admin access: platform admins only ---
    @property
    def is_staff(self) -> bool:
        return self.is_platform_admin

    @property
    def is_superuser(self) -> bool:
        return self.is_platform_admin

    def has_perm(self, perm: str, obj: object = None) -> bool:
        return self.is_platform_admin

    def has_module_perms(self, app_label: str) -> bool:
        return self.is_platform_admin


class UserToken(CreatedModel):
    """Single-use token; only its SHA-256 hash is stored."""

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="tokens")
    purpose = models.CharField(max_length=20, choices=TokenPurpose.choices)
    token_hash = models.CharField(max_length=64, unique=True)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "user_tokens"
        constraints = [
            choices_check("user_tokens", "purpose", TokenPurpose),
        ]
