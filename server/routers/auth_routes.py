import asyncio
import secrets
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session

from auth import (
    AuthContext,
    claim_pending_invites,
    consume_reset_token,
    consume_verification_token,
    create_access_token,
    get_current_context,
    hash_password,
    issue_reset_token,
    invalidate_verification_tokens,
    issue_verification_token,
    normalize_email,
    verify_password,
)
from db import get_db
from email_service import (
    send_email_verification,
    send_existing_account_notice,
    send_password_reset,
)
from models import User

router = APIRouter(prefix="/api/auth", tags=["auth"])


class SignupRequest(BaseModel):
    email: EmailStr
    password: str
    username: str | None = None


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    password: str


class VerifyEmailRequest(BaseModel):
    token: str


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


class UserOut(BaseModel):
    id: str
    email: str
    username: str | None = None
    avatar_url: str | None = None
    email_verified: bool = False

    @classmethod
    def of(cls, user: User) -> "UserOut":
        return cls(
            id=user.id,
            email=user.email,
            username=user.username,
            avatar_url=user.avatar_url,
            email_verified=user.email_verified_at is not None,
        )


class SessionOut(BaseModel):
    token: str
    user: UserOut


def _find_by_email(db: Session, email: str) -> User | None:
    return db.query(User).filter(User.email == normalize_email(email)).first()


SIGNUP_MESSAGE = (
    "Check your email to confirm your address, then sign in."
)


@router.post("/signup")
async def signup(body: SignupRequest, db: Session = Depends(get_db)):
    """Answers identically whether or not the address is already taken, so
    signup can't be used to discover which emails have accounts. The real owner
    of an existing address learns about the attempt by email instead."""
    email = normalize_email(body.email)
    password_hash = hash_password(body.password)  # validates before we touch the db

    existing = _find_by_email(db, email)
    if existing is not None:
        if existing.email_verified_at is None:
            # Account pre-hijacking defence: an unverified account proves
            # nothing about who created it, so the newest signup takes over the
            # password and every earlier verification link is burned. Only
            # someone who can read this inbox can finish the takeover.
            existing.password_hash = password_hash
            existing.username = (
                (body.username or "").strip() or existing.username or email.split("@")[0]
            )
            db.commit()
            invalidate_verification_tokens(db, existing)
            await send_email_verification(
                email, issue_verification_token(db, existing)
            )
        else:
            await send_existing_account_notice(email)
        return {"ok": True, "message": SIGNUP_MESSAGE}

    user = User(
        email=email,
        password_hash=password_hash,
        username=(body.username or "").strip() or email.split("@")[0],
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    # no session here: the account exists but hasn't proven it owns the address,
    # and issuing a token on the taken-email branch would leak existence anyway
    await send_email_verification(email, issue_verification_token(db, user))
    return {"ok": True, "message": SIGNUP_MESSAGE}


@router.post("/verify-email", response_model=SessionOut)
async def verify_email(body: VerifyEmailRequest, db: Session = Depends(get_db)):
    user = consume_verification_token(db, body.token)
    if user is None:
        raise HTTPException(
            status_code=400, detail="That verification link is invalid or has expired"
        )
    if user.email_verified_at is None:
        user.email_verified_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(user)
    # only now is it safe to hand over anything addressed to this email
    claim_pending_invites(db, user)
    return SessionOut(token=create_access_token(user.id), user=UserOut.of(user))


@router.post("/resend-verification")
async def resend_verification(
    body: ForgotPasswordRequest, db: Session = Depends(get_db)
):
    user = _find_by_email(db, body.email)
    if user is not None and user.email_verified_at is None:
        await send_email_verification(user.email, issue_verification_token(db, user))
    else:
        await asyncio.sleep(0.2)
    return {"ok": True, "message": SIGNUP_MESSAGE}


@router.post("/login", response_model=SessionOut)
async def login(body: LoginRequest, db: Session = Depends(get_db)):
    user = _find_by_email(db, body.email)
    # compare against a dummy hash when the address is unknown so response time
    # doesn't reveal which addresses have accounts
    if user is None:
        verify_password(body.password, hash_password(secrets.token_urlsafe(16)))
        raise HTTPException(status_code=401, detail="Incorrect email or password")
    if not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Incorrect email or password")
    # no-op while the address is unverified; picks the invites up on the first
    # sign-in after verification
    claim_pending_invites(db, user)
    return SessionOut(token=create_access_token(user.id), user=UserOut.of(user))


@router.get("/me", response_model=UserOut)
async def me(ctx: AuthContext = Depends(get_current_context), db: Session = Depends(get_db)):
    user = db.get(User, ctx.user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="User no longer exists")
    return UserOut.of(user)


@router.post("/forgot-password")
async def forgot_password(body: ForgotPasswordRequest, db: Session = Depends(get_db)):
    user = _find_by_email(db, body.email)
    if user is not None:
        await send_password_reset(user.email, issue_reset_token(db, user))
    else:
        # keep the timing in the same ballpark as the real branch
        await asyncio.sleep(0.2)
    # always the same answer: this endpoint must not disclose who has an account
    return {"ok": True, "message": "If that account exists, a reset link is on its way."}


@router.post("/reset-password", response_model=SessionOut)
async def reset_password(body: ResetPasswordRequest, db: Session = Depends(get_db)):
    password_hash = hash_password(body.password)
    user = consume_reset_token(db, body.token)
    if user is None:
        raise HTTPException(status_code=400, detail="That reset link is invalid or has expired")
    user.password_hash = password_hash
    # following a link in the inbox proves ownership just as well as the
    # verification link does, so don't make them do it twice
    if user.email_verified_at is None:
        user.email_verified_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(user)
    claim_pending_invites(db, user)
    return SessionOut(token=create_access_token(user.id), user=UserOut.of(user))


@router.post("/change-password")
async def change_password(
    body: ChangePasswordRequest,
    ctx: AuthContext = Depends(get_current_context),
    db: Session = Depends(get_db),
):
    user = db.get(User, ctx.user_id)
    if user is None or not verify_password(body.current_password, user.password_hash):
        raise HTTPException(status_code=403, detail="Current password is incorrect")
    user.password_hash = hash_password(body.new_password)
    db.commit()
    return {"ok": True}
