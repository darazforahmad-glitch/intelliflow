"""SQLAlchemy models. Importing this package registers every table on Base.metadata."""

from app.models.approval import ApprovalTask
from app.models.audit import AuditLog, LLMUsage
from app.models.automation import Automation, AutomationVersion
from app.models.base import Base
from app.models.connection import Connection, SandboxRecord
from app.models.interview import InterviewMessage, InterviewSession
from app.models.notification import EmailMessage, Notification, PushSubscription
from app.models.opportunity import Opportunity
from app.models.process import ProcessMap, ProcessStep
from app.models.run import Run, StepRun
from app.models.template import Template
from app.models.user import User, UserToken
from app.models.workspace import Invitation, Membership, Workspace

__all__ = [
    "ApprovalTask",
    "AuditLog",
    "Automation",
    "AutomationVersion",
    "Base",
    "Connection",
    "EmailMessage",
    "InterviewMessage",
    "InterviewSession",
    "Invitation",
    "LLMUsage",
    "Membership",
    "Notification",
    "Opportunity",
    "ProcessMap",
    "ProcessStep",
    "PushSubscription",
    "Run",
    "SandboxRecord",
    "StepRun",
    "Template",
    "User",
    "UserToken",
    "Workspace",
]
