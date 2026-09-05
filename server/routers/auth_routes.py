import asyncio
import secrets

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session

from auth import (
    AuthContext,
    claim_pending_invites,
    consume_reset_token,
    create_access_token,
    get_current_context,
    hash_password,
    issue_reset_token,
    normalize_email,
    verify_password,
)
from db import get_db
from email_service import send_password_reset
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


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


class UserOut(BaseModel):
    id: str
    email: str
    username: str | None = None
    avatar_url: str | None = None

    class Config:
        from_attributes = True


class SessionOut(BaseModel):
    token: str
    user: UserOut


def _find_by_email(db: Session, email: str) -> User | None:
    return db.query(User).filter(User.email == normalize_email(email)).first()


@router.post("/signup", response_model=SessionOut)
async def signup(body: SignupRequest, db: Session = Depends(get_db)):
    email = normalize_email(body.email)
    password_hash = hash_password(body.password)  # validates before we touch the db
    if _find_by_email(db, email):
        raise HTTPException(status_code=409, detail="An account with that email already exists")
    user = User(
        email=email,
        password_hash=password_hash,
        username=(body.username or "").strip() or email.split("@")[0],
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    claim_pending_invites(db, user)
    return SessionOut(token=create_access_token(user.id), user=UserOut.model_validate(user))


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
    claim_pending_invites(db, user)
    return SessionOut(token=create_access_token(user.id), user=UserOut.model_validate(user))


@router.get("/me", response_model=UserOut)
async def me(ctx: AuthContext = Depends(get_current_context), db: Session = Depends(get_db)):
    user = db.get(User, ctx.user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="User no longer exists")
    return UserOut.model_validate(user)


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
    db.commit()
    db.refresh(user)
    return SessionOut(token=create_access_token(user.id), user=UserOut.model_validate(user))


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
