"""/api/v1/auth: registration, verification, sign-in, tokens and password reset (UC-01)."""

from __future__ import annotations

from fastapi import APIRouter, Request, status

from app.api.deps import DB, CurrentUser, client_ip
from app.models.enums import MembershipStatus
from app.schemas.auth import (
    EmailRequest,
    LoginRequest,
    MembershipOut,
    MeOut,
    RefreshRequest,
    RegisterRequest,
    ResetPasswordRequest,
    TokenPair,
    TokenRequest,
    UpdateMeRequest,
    UserOut,
)
from app.schemas.common import MessageOut
from app.services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])


def _token_pair(service: AuthService, user, tokens) -> TokenPair:  # type: ignore[no-untyped-def]
    return TokenPair(
        access_token=tokens.access_token,
        refresh_token=tokens.refresh_token,
        expires_in=tokens.expires_in,
        user=UserOut.model_validate(user),
    )


@router.post("/register", response_model=MessageOut, status_code=status.HTTP_201_CREATED)
def register(body: RegisterRequest, db: DB, request: Request) -> MessageOut:
    AuthService(db).register(body, ip=client_ip(request))
    return MessageOut(message="Account created. Please check your e-mail to verify your address.")


@router.post("/verify-email", response_model=MessageOut)
def verify_email(body: TokenRequest, db: DB) -> MessageOut:
    AuthService(db).verify_email(body.token)
    return MessageOut(message="Your e-mail address is verified. You can sign in now.")


@router.post(
    "/resend-verification", response_model=MessageOut, status_code=status.HTTP_202_ACCEPTED
)
def resend_verification(body: EmailRequest, db: DB) -> MessageOut:
    AuthService(db).resend_verification(body.email)
    return MessageOut(message="If the account exists and is not verified yet, we sent a new link.")


@router.post("/login", response_model=TokenPair)
def login(body: LoginRequest, db: DB, request: Request) -> TokenPair:
    service = AuthService(db)
    user, tokens = service.login(body.email, body.password, ip=client_ip(request))
    return _token_pair(service, user, tokens)


@router.post("/refresh", response_model=TokenPair)
def refresh(body: RefreshRequest, db: DB) -> TokenPair:
    service = AuthService(db)
    user, tokens = service.refresh(body.refresh_token)
    return _token_pair(service, user, tokens)


@router.post("/logout-all", response_model=MessageOut)
def logout_all(user: CurrentUser, db: DB) -> MessageOut:
    AuthService(db).logout_all(user)
    return MessageOut(message="You have been signed out on every device.")


@router.post("/forgot-password", response_model=MessageOut, status_code=status.HTTP_202_ACCEPTED)
def forgot_password(body: EmailRequest, db: DB) -> MessageOut:
    AuthService(db).forgot_password(body.email)
    return MessageOut(
        message="If an account exists for this e-mail, we sent a reset link. It expires in 30 minutes."
    )


@router.post("/reset-password", response_model=MessageOut)
def reset_password(body: ResetPasswordRequest, db: DB) -> MessageOut:
    AuthService(db).reset_password(body.token, body.new_password)
    return MessageOut(
        message="Your password has been changed. Please sign in with the new password."
    )


def _me(user) -> MeOut:  # type: ignore[no-untyped-def]
    memberships = [
        MembershipOut(
            membership_id=m.id,
            workspace_id=m.workspace_id,
            workspace_name=m.workspace.name,
            role=m.role.value,
            status=m.status.value,
            workspace_status=m.workspace.status.value,
        )
        for m in user.memberships
        if m.status != MembershipStatus.REMOVED and m.workspace.deleted_at is None
    ]
    return MeOut(**UserOut.model_validate(user).model_dump(), memberships=memberships)


@router.get("/me", response_model=MeOut)
def me(user: CurrentUser) -> MeOut:
    return _me(user)


@router.patch("/me", response_model=MeOut)
def update_me(body: UpdateMeRequest, user: CurrentUser, db: DB) -> MeOut:
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(user, field, value.strip() if isinstance(value, str) else value)
    db.commit()
    return _me(user)
