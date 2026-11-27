"""Enumerations from the data dictionary (Section 4.3) and state diagrams (4.8).

Django `TextChoices`: the stored values are the same lower-case strings as before.
Values read from the database are plain strings, so wrap them (`RunStatus(run.status)`)
before using the helper properties."""

from django.db import models


class WorkspaceStatus(models.TextChoices):
    ACTIVE = "active"
    SUSPENDED = "suspended"


class MembershipRole(models.TextChoices):
    OWNER = "owner"
    STAFF = "staff"


class MembershipStatus(models.TextChoices):
    INVITED = "invited"
    ACTIVE = "active"
    REMOVED = "removed"


class TokenPurpose(models.TextChoices):
    VERIFY_EMAIL = "verify_email"
    RESET_PASSWORD = "reset_password"  # noqa: S105 - enum label, not a secret


class InterviewStatus(models.TextChoices):
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    ABANDONED = "abandoned"


class MessageSender(models.TextChoices):
    AI = "ai"
    USER = "user"


class StepType(models.TextChoices):
    START = "start"
    MANUAL = "manual"
    AUTOMATED = "automated"
    HUMAN_ONLY = "human_only"
    END = "end"


class OpportunityStatus(models.TextChoices):
    SUGGESTED = "suggested"
    SELECTED = "selected"
    DISMISSED = "dismissed"
    AUTOMATED = "automated"


class ConnectionProvider(models.TextChoices):
    WHATSAPP = "whatsapp"
    GMAIL = "gmail"
    GOOGLE_SHEETS = "google_sheets"
    WEBFORM = "webform"


class ConnectionStatus(models.TextChoices):
    CONNECTED = "connected"
    NEEDS_ATTENTION = "needs_attention"
    DISCONNECTED = "disconnected"


class ConnectionMode(models.TextChoices):
    LIVE = "live"
    SANDBOX = "sandbox"


class AutomationStatus(models.TextChoices):
    """Automation lifecycle, Figure 4.9."""

    DRAFT = "draft"
    VALIDATED = "validated"
    TESTED = "tested"
    ACTIVE = "active"
    PAUSED = "paused"
    ERROR = "error"
    ARCHIVED = "archived"


class RunStatus(models.TextChoices):
    QUEUED = "queued"
    RUNNING = "running"
    WAITING_APPROVAL = "waiting_approval"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"

    @property
    def is_terminal(self) -> bool:
        return self in {RunStatus.SUCCEEDED, RunStatus.FAILED, RunStatus.CANCELLED}


class StepRunStatus(models.TextChoices):
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"
    WAITING = "waiting"


class ApprovalStatus(models.TextChoices):
    """Approval task states, Figure 4.10."""

    PENDING = "pending"
    REMINDED = "reminded"
    APPROVED = "approved"
    EDITED = "edited"
    REJECTED = "rejected"
    EXPIRED = "expired"

    @property
    def is_open(self) -> bool:
        return self in {ApprovalStatus.PENDING, ApprovalStatus.REMINDED}


class ApprovalKind(models.TextChoices):
    CUSTOMER_MESSAGE = "customer_message"
    MONEY = "money"
    REVIEW = "review"
    WINDOW_CLOSED = "window_closed"
