"""Transactional email via Resend.

Password reset is the only sender today. Delivery is best-effort by design:
a Resend outage must not turn "forgot password" into a 500 that confirms
whether an address exists, so failures are logged and swallowed.
"""

import logging
import os

import httpx

logger = logging.getLogger(__name__)

RESEND_API_KEY = os.environ.get("RESEND_API_KEY")
RESEND_FROM = os.environ.get("RESEND_FROM", "AIXDraw <noreply@aixccelerate.com>")
APP_URL = os.environ.get("APP_URL", "").rstrip("/")


async def send_password_reset(to_email: str, token: str) -> bool:
    reset_url = f"{APP_URL}/reset-password?token={token}"
    if not RESEND_API_KEY:
        logger.warning("RESEND_API_KEY unset; reset link for %s: %s", to_email, reset_url)
        return False
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                "https://api.resend.com/emails",
                headers={"Authorization": f"Bearer {RESEND_API_KEY}"},
                json={
                    "from": RESEND_FROM,
                    "to": [to_email],
                    "subject": "Reset your AIXDraw password",
                    "html": (
                        "<p>Someone asked to reset the password for this AIXDraw "
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
