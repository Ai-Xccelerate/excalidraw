"""OAuth 2.1 authorization-server pieces backing the MCP endpoint.

The flow is the one MCP clients (Claude, ChatGPT, and anything else speaking
the spec) expect: discover the server through the protected-resource metadata,
register themselves dynamically, run an authorization-code + PKCE flow against
a consent screen in the app, then call /mcp with the resulting bearer token.

Everything is stored hashed and every code is single use, so neither a leaked
database nor an intercepted redirect yields a usable session.
"""

import base64
import hashlib
import os
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from db import get_db
from models import OAuthAuthorizationCode, OAuthClient, OAuthToken, User

# Where the API answers. Needed verbatim in the discovery documents, and as the
# audience clients bind their tokens to.
PUBLIC_API_URL = os.environ.get("PUBLIC_API_URL", "").rstrip("/")
# Where the consent screen lives (the app, not the API).
PUBLIC_APP_URL = os.environ.get("PUBLIC_APP_URL", "").rstrip("/")

ACCESS_TOKEN_TTL = timedelta(hours=1)
REFRESH_TOKEN_TTL = timedelta(days=60)
CODE_TTL = timedelta(minutes=5)

_REJECTED_SCHEMES = {
    "ftp",
    "ftps",
    "file",
    "data",
    "blob",
    "javascript",
    "vbscript",
    "about",
    "ws",
    "wss",
}

SUPPORTED_SCOPES = ["drawings:read", "drawings:write", "profile"]
DEFAULT_SCOPE = "drawings:read drawings:write profile"


def now() -> datetime:
    return datetime.now(timezone.utc)


def hash_secret(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def new_secret(prefix: str = "") -> str:
    return f"{prefix}{secrets.token_urlsafe(32)}"


def normalize_scope(requested: str | None) -> str:
    """Unknown scopes are dropped rather than rejected: a client asking for
    more than we offer should still get a working, narrower token."""
    if not requested:
        return DEFAULT_SCOPE
    granted = [s for s in requested.split() if s in SUPPORTED_SCOPES]
    return " ".join(granted) if granted else DEFAULT_SCOPE


def is_valid_redirect_uri(uri: str) -> bool:
    """Loopback and custom-scheme redirects are how desktop MCP clients come
    back; anything else has to be https so a code can't be sent in the clear."""
    try:
        parsed = urlparse(uri)
    except ValueError:
        return False
    if not parsed.scheme:
        return False
    if parsed.scheme == "https":
        return True
    if parsed.scheme == "http":
        return parsed.hostname in ("localhost", "127.0.0.1", "::1")
    # a desktop client may come back on its own scheme (cursor://, claude://).
    # Transport and script-bearing schemes are not redirect targets, so they
    # are refused rather than treated as "custom".
    if parsed.scheme in _REJECTED_SCHEMES:
        return False
    return bool(parsed.netloc or parsed.path)


def verify_pkce(verifier: str, challenge: str, method: str) -> bool:
    if method == "S256":
        digest = hashlib.sha256(verifier.encode()).digest()
        expected = base64.urlsafe_b64encode(digest).decode().rstrip("=")
        return secrets.compare_digest(expected, challenge)
    # OAuth 2.1 drops "plain"; we only accept it for local development clients
    return False


# ------------------------------------------------------------------- issuing

def issue_code(
    db: Session,
    *,
    client: OAuthClient,
    user: User,
    redirect_uri: str,
    code_challenge: str,
    code_challenge_method: str,
    scope: str,
    resource: str | None,
) -> str:
    raw = new_secret()
    db.add(
        OAuthAuthorizationCode(
            code_hash=hash_secret(raw),
            client_id=client.client_id,
            user_id=user.id,
            redirect_uri=redirect_uri,
            code_challenge=code_challenge,
            code_challenge_method=code_challenge_method,
            scope=scope,
            resource=resource,
            expires_at=now() + CODE_TTL,
        )
    )
    db.commit()
    return raw


def consume_code(db: Session, raw: str) -> OAuthAuthorizationCode | None:
    """Marks the code used in the same UPDATE that reads it, so two racing
    redemptions can't both succeed."""
    updated = (
        db.query(OAuthAuthorizationCode)
        .filter(
            OAuthAuthorizationCode.code_hash == hash_secret(raw),
            OAuthAuthorizationCode.used_at.is_(None),
            OAuthAuthorizationCode.expires_at > now(),
        )
        .update({OAuthAuthorizationCode.used_at: now()}, synchronize_session=False)
    )
    db.commit()
    if not updated:
        return None
    return db.get(OAuthAuthorizationCode, hash_secret(raw))


def issue_tokens(
    db: Session, *, client_id: str, user_id: str, scope: str
) -> tuple[str, str, int]:
    access = new_secret("aixd_at_")
    refresh = new_secret("aixd_rt_")
    db.add(
        OAuthToken(
            access_token_hash=hash_secret(access),
            refresh_token_hash=hash_secret(refresh),
            client_id=client_id,
            user_id=user_id,
            scope=scope,
            expires_at=now() + ACCESS_TOKEN_TTL,
        )
    )
    db.commit()
    return access, refresh, int(ACCESS_TOKEN_TTL.total_seconds())


def rotate_refresh_token(db: Session, raw_refresh: str) -> tuple[str, str, int] | None:
    """Refresh tokens are single use: the old row is revoked as it is spent, so
    a stolen refresh token stops working as soon as the real client uses it."""
    row = (
        db.query(OAuthToken)
        .filter(
            OAuthToken.refresh_token_hash == hash_secret(raw_refresh),
            OAuthToken.revoked_at.is_(None),
        )
        .first()
    )
    if row is None or row.created_at + REFRESH_TOKEN_TTL < now():
        return None
    row.revoked_at = now()
    db.commit()
    return issue_tokens(db, client_id=row.client_id, user_id=row.user_id, scope=row.scope)


# ---------------------------------------------------------------- validation

class McpContext:
    def __init__(self, user: User, token: OAuthToken):
        self.user = user
        self.user_id = user.id
        self.token = token
        self.scopes = set(token.scope.split())

    def require(self, scope: str) -> None:
        if scope not in self.scopes:
            raise HTTPException(
                status_code=403,
                detail=f"Token is missing the {scope} scope",
            )


def _unauthorized(detail: str) -> HTTPException:
    # the resource-metadata pointer is what lets an MCP client discover where
    # to authorize; without it the client has no way to start the flow
    resource_metadata = f"{PUBLIC_API_URL}/.well-known/oauth-protected-resource"
    return HTTPException(
        status_code=401,
        detail=detail,
        headers={
            "WWW-Authenticate": (
                'Bearer error="invalid_token", '
                f'error_description="{detail}", '
                f'resource_metadata="{resource_metadata}"'
            )
        },
    )


async def get_mcp_context(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> McpContext:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise _unauthorized("Missing bearer token")
    raw = authorization.split(" ", 1)[1].strip()
    row = (
        db.query(OAuthToken)
        .filter(
            OAuthToken.access_token_hash == hash_secret(raw),
            OAuthToken.revoked_at.is_(None),
        )
        .first()
    )
    if row is None:
        raise _unauthorized("Unknown or revoked token")
    if row.expires_at < now():
        raise _unauthorized("Token has expired")
    user = db.get(User, row.user_id)
    if user is None:
        raise _unauthorized("Account no longer exists")
    row.last_used_at = now()
    db.commit()
    return McpContext(user, row)
