"""Abstract base models: every table has a UUID primary key (Section 4.3) and UTC timestamps."""

from __future__ import annotations

import uuid
from datetime import datetime

from django.db import models
from django.utils import timezone


def utcnow() -> datetime:
    return timezone.now()


class UUIDModel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    class Meta:
        abstract = True


class CreatedModel(UUIDModel):
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        abstract = True


class TimestampedModel(CreatedModel):
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


def choices_check(
    table: str, field: str, choices: type[models.TextChoices]
) -> models.CheckConstraint:
    """DB-level guard for an enum column (the data dictionary's enum types): only the
    listed values can be stored, as with a native PostgreSQL ENUM."""
    return models.CheckConstraint(
        condition=models.Q(**{f"{field}__in": choices.values}), name=f"ck_{table}_{field}"
    )
