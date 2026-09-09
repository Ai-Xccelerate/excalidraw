"""Transactional email via Resend.

Delivery is best-effort by design: a Resend outage must not turn signup or
"forgot password" into a 500 that confirms whether an address exists, so
failures are logged and swallowed.
"""

import logging
import os

import httpx

logger = logging.getLogger(__name__)

RESEND_API_KEY = os.environ.get("RESEND_API_KEY")
RESEND_FROM = os.environ.get("RESEND_FROM", "draw.getdraw.app <noreply@aixccelerate.com>")
APP_URL = os.environ.get("APP_URL", "").rstrip("/")


async def send_password_reset(to_email: str, token: str) -> bool:
    reset_url = f"{APP_URL}/reset-password?token={token}"
    if not RESEND_API_KEY:
        # never log the URL: it carries the raw reset token, which would turn
        # log access into account takeover
        logger.error(
            "RESEND_API_KEY unset; password reset email for %s was not sent", to_email
        )
        return False
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                "https://api.resend.com/emails",
                headers={"Authorization": f"Bearer {RESEND_API_KEY}"},
                json={
                    "from": RESEND_FROM,
                    "to": [to_email],
                    "subject": "Reset your draw.getdraw.app password",
                    "html": (
                        "<p>Someone asked to reset the password for this draw.getdraw.app "
                        "account. This link expires in one hour and can be used once.</p>"
                        f'<p><a href="{reset_url}">Reset your password</a></p>'
                        "<p>If that wasn't you, you can ignore this email — your "
                        "password won't change.</p>"
                    ),
                },
            )
    except httpx.HTTPError:
        logger.exception("Resend request failed for %s", to_email)
        return False
    if response.status_code >= 300:
        logger.error("Resend rejected the send: %s %s", response.status_code, response.text)
        return False
    return True


async def _send(to_email: str, subject: str, html: str, fallback: str) -> bool:  # noqa: ARG001
    if not RESEND_API_KEY:
        # `fallback` can embed a single-use token; log only that it failed
        logger.error("RESEND_API_KEY unset; %r email for %s was not sent", subject, to_email)
        return False
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                "https://api.resend.com/emails",
                headers={"Authorization": f"Bearer {RESEND_API_KEY}"},
                json={
                    "from": RESEND_FROM,
                    "to": [to_email],
                    "subject": subject,
                    "html": html,
                },
            )
    except httpx.HTTPError:
        logger.exception("Resend request failed for %s", to_email)
        return False
    if response.status_code >= 300:
        logger.error("Resend rejected the send: %s %s", response.status_code, response.text)
        return False
    return True


async def send_email_verification(to_email: str, token: str) -> bool:
    url = f"{APP_URL}/verify-email?token={token}"
    return await _send(
        to_email,
        "Verify your draw.getdraw.app email",
        (
            "<p>Confirm this address to finish setting up your draw.getdraw.app account. "
            "This link expires in 24 hours.</p>"
            f'<p><a href="{url}">Verify my email</a></p>'
            "<p>Until it's confirmed, any workspace or drawing invites sent to "
            "this address stay pending.</p>"
        ),
        url,
    )


async def send_existing_account_notice(to_email: str) -> bool:
    """Sent when someone tries to sign up with an address that already has an
    account. Signup answers identically either way, so this is what tells the
    real owner that it happened."""
    return await _send(
        to_email,
        "You already have a draw.getdraw.app account",
        (
            "<p>Someone just tried to create a draw.getdraw.app account with this "
            "address, but one already exists.</p>"
            f'<p>If that was you, <a href="{APP_URL}/login">sign in</a> instead, '
            f'or <a href="{APP_URL}/login">reset your password</a> if you\'ve '
            "forgotten it.</p>"
            "<p>If it wasn't you, no action is needed — nothing about your "
            "account has changed.</p>"
        ),
        f"{APP_URL}/login",
    )
