"""Enumerations from the data dictionary (Section 4.3) and state diagrams (4.8)."""

from enum import StrEnum


class WorkspaceStatus(StrEnum):
    ACTIVE = "active"
    SUSPENDED = "suspended"


class MembershipRole(StrEnum):
    OWNER = "owner"
    STAFF = "staff"


class MembershipStatus(StrEnum):
    INVITED = "invited"
    ACTIVE = "active"
    REMOVED = "removed"


class TokenPurpose(StrEnum):
    VERIFY_EMAIL = "verify_email"
    RESET_PASSWORD = "reset_password"  # noqa: S105 - enum label, not a secret


class InterviewStatus(StrEnum):
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    ABANDONED = "abandoned"


class MessageSender(StrEnum):
    AI = "ai"
    USER = "user"


class StepType(StrEnum):
    START = "start"
    MANUAL = "manual"
    AUTOMATED = "automated"
    HUMAN_ONLY = "human_only"
    END = "end"


class OpportunityStatus(StrEnum):
    SUGGESTED = "suggested"
    SELECTED = "selected"
    DISMISSED = "dismissed"
    AUTOMATED = "automated"


class ConnectionProvider(StrEnum):
    WHATSAPP = "whatsapp"
    GMAIL = "gmail"
    GOOGLE_SHEETS = "google_sheets"
    WEBFORM = "webform"


class ConnectionStatus(StrEnum):
    CONNECTED = "connected"
    NEEDS_ATTENTION = "needs_attention"
    DISCONNECTED = "disconnected"


class ConnectionMode(StrEnum):
    LIVE = "live"
    SANDBOX = "sandbox"


class AutomationStatus(StrEnum):
    """Automation lifecycle, Figure 4.9."""

    DRAFT = "draft"
    VALIDATED = "validated"
    TESTED = "tested"
    ACTIVE = "active"
    PAUSED = "paused"
    ERROR = "error"
    ARCHIVED = "archived"


class RunStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    WAITING_APPROVAL = "waiting_approval"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"

    @property
    def is_terminal(self) -> bool:
        return self in {RunStatus.SUCCEEDED, RunStatus.FAILED, RunStatus.CANCELLED}


class StepRunStatus(StrEnum):
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"
    WAITING = "waiting"


class ApprovalStatus(StrEnum):
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


class ApprovalKind(StrEnum):
    CUSTOMER_MESSAGE = "customer_message"
    MONEY = "money"
    REVIEW = "review"
    WINDOW_CLOSED = "window_closed"
