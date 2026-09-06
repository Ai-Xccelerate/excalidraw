"""OAuth 2.1 endpoints: discovery, dynamic client registration, and the
authorization-code + PKCE flow that MCP clients run before calling /mcp.

The /authorize step deliberately does not render HTML here. The API has no
session cookie — the app holds the bearer token — so /authorize bounces to the
app's consent screen, which then calls the JSON approve endpoint with the
user's own token and follows the redirect it returns.
"""

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from urllib.parse import urlencode

from auth import AuthContext, get_current_context
from db import get_db
from models import OAuthClient, OAuthToken, User
from oauth import (
    DEFAULT_SCOPE,
    PUBLIC_API_URL,
    PUBLIC_APP_URL,
    SUPPORTED_SCOPES,
    consume_code,
    hash_secret,
    is_valid_redirect_uri,
    issue_code,
    issue_tokens,
    new_secret,
    normalize_scope,
    now,
    rotate_refresh_token,
    verify_pkce,
)

router = APIRouter(tags=["oauth"])


# ------------------------------------------------------------------ discovery

@router.get("/.well-known/oauth-authorization-server")
async def authorization_server_metadata():
    return {
        "issuer": PUBLIC_API_URL,
        "authorization_endpoint": f"{PUBLIC_API_URL}/oauth/authorize",
        "token_endpoint": f"{PUBLIC_API_URL}/oauth/token",
        "registration_endpoint": f"{PUBLIC_API_URL}/oauth/register",
        "revocation_endpoint": f"{PUBLIC_API_URL}/oauth/revoke",
        "scopes_supported": SUPPORTED_SCOPES,
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code", "refresh_token"],
        "token_endpoint_auth_methods_supported": ["none", "client_secret_post"],
        # OAuth 2.1: PKCE is mandatory, and only S256 is accepted
        "code_challenge_methods_supported": ["S256"],
    }


@router.get("/.well-known/oauth-protected-resource")
async def protected_resource_metadata():
    return {
        "resource": f"{PUBLIC_API_URL}/mcp",
        "authorization_servers": [PUBLIC_API_URL],
        "scopes_supported": SUPPORTED_SCOPES,
        "bearer_methods_supported": ["header"],
        "resource_name": "AIXDraw",
    }


# -------------------------------------------------------------- registration

class RegisterRequest(BaseModel):
    client_name: str | None = None
    redirect_uris: list[str] = []
    grant_types: list[str] = ["authorization_code", "refresh_token"]
    token_endpoint_auth_method: str = "none"
    scope: str | None = None
    client_uri: str | None = None


@router.post("/oauth/register", status_code=201)
async def register_client(body: RegisterRequest, db: Session = Depends(get_db)):
    """Dynamic client registration (RFC 7591). Open by design — this is how an
    MCP host with no prior relationship gets a client_id — but it hands out no
    access on its own: nothing happens until a signed-in user approves the
    consent screen."""
    if not body.redirect_uris:
        raise HTTPException(400, "redirect_uris is required")
    for uri in body.redirect_uris:
        if not is_valid_redirect_uri(uri):
            raise HTTPException(400, f"Unsupported redirect_uri: {uri}")

    client_id = new_secret("aixd_client_")
    secret = None
    secret_hash = None
    if body.token_endpoint_auth_method == "client_secret_post":
        secret = new_secret()
        secret_hash = hash_secret(secret)

    client = OAuthClient(
        client_id=client_id,
        client_secret_hash=secret_hash,
        client_name=(body.client_name or "MCP client")[:120],
        redirect_uris=body.redirect_uris,
        grant_types=body.grant_types,
        scope=normalize_scope(body.scope),
        client_uri=body.client_uri,
    )
    db.add(client)
    db.commit()

    out = {
        "client_id": client_id,
        "client_name": client.client_name,
        "redirect_uris": client.redirect_uris,
        "grant_types": client.grant_types,
        "token_endpoint_auth_method": body.token_endpoint_auth_method,
        "scope": client.scope,
        # no expiry: re-registering on every connect would orphan the consent
        # the user already gave to this client
        "client_id_issued_at": int(client.created_at.timestamp()),
        "client_secret_expires_at": 0,
    }
    if secret:
        out["client_secret"] = secret
    return out


# ------------------------------------------------------------------ authorize

@router.get("/oauth/authorize")
async def authorize(request: Request, db: Session = Depends(get_db)):
    """Validates the request, then hands off to the app's consent screen.

    Validating here rather than in the app means a malformed or spoofed request
    never reaches a screen where the user could approve it."""
    params = dict(request.query_params)
    client_id = params.get("client_id", "")
    redirect_uri = params.get("redirect_uri", "")
    client = db.get(OAuthClient, client_id)

    if client is None:
        raise HTTPException(400, "Unknown client_id")
    # an unregistered redirect_uri is never bounced to: that is the one error
    # that must be shown here rather than forwarded to the caller
    if redirect_uri not in client.redirect_uris:
        raise HTTPException(400, "redirect_uri does not match the registered client")

    state = params.get("state", "")

    def bounce(error: str, description: str) -> RedirectResponse:
        query = urlencode(
            {"error": error, "error_description": description, "state": state}
        )
        return RedirectResponse(f"{redirect_uri}?{query}", status_code=302)

    if params.get("response_type") != "code":
        return bounce("unsupported_response_type", "Only response_type=code is supported")
    if not params.get("code_challenge"):
        return bounce("invalid_request", "PKCE code_challenge is required")
    if params.get("code_challenge_method", "S256") != "S256":
        return bounce("invalid_request", "Only S256 PKCE is supported")

    consent = urlencode(
        {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "state": state,
            "code_challenge": params["code_challenge"],
            "code_challenge_method": "S256",
            "scope": normalize_scope(params.get("scope")),
            "resource": params.get("resource", ""),
        }
    )
    return RedirectResponse(f"{PUBLIC_APP_URL}/oauth/consent?{consent}", status_code=302)


class ApproveRequest(BaseModel):
    client_id: str
    redirect_uri: str
    state: str = ""
    code_challenge: str
    code_challenge_method: str = "S256"
    scope: str | None = None
    resource: str | None = None


@router.get("/api/oauth/clients/{client_id}")
async def describe_client(
    client_id: str,
    ctx: AuthContext = Depends(get_current_context),
    db: Session = Depends(get_db),
):
    """What the consent screen shows about who is asking."""
    client = db.get(OAuthClient, client_id)
    if client is None:
        raise HTTPException(404, "Unknown client")
    return {
        "client_id": client.client_id,
        "client_name": client.client_name,
        "client_uri": client.client_uri,
        "registered_at": client.created_at.isoformat(),
    }


@router.post("/api/oauth/approve")
async def approve(
    body: ApproveRequest,
    ctx: AuthContext = Depends(get_current_context),
    db: Session = Depends(get_db),
):
    """Called by the consent screen with the user's own session token. Returns
    the redirect the browser should follow — the code never passes through the
    app's own URL bar as anything but that redirect."""
    client = db.get(OAuthClient, body.client_id)
    if client is None:
        raise HTTPException(400, "Unknown client_id")
    if body.redirect_uri not in client.redirect_uris:
        raise HTTPException(400, "redirect_uri does not match the registered client")
    if body.code_challenge_method != "S256" or not body.code_challenge:
        raise HTTPException(400, "PKCE with S256 is required")

    user = db.get(User, ctx.user_id)
    if user is None:
        raise HTTPException(401, "Session is no longer valid")

    code = issue_code(
        db,
        client=client,
        user=user,
        redirect_uri=body.redirect_uri,
        code_challenge=body.code_challenge,
        code_challenge_method=body.code_challenge_method,
        scope=normalize_scope(body.scope),
        resource=body.resource or None,
    )
    query = urlencode({"code": code, "state": body.state})
    return {"redirect_to": f"{body.redirect_uri}?{query}"}


# ---------------------------------------------------------------------- token

class DenyRequest(BaseModel):
    client_id: str
    redirect_uri: str
    state: str = ""


@router.post("/api/oauth/deny")
async def deny(
    body: DenyRequest,
    ctx: AuthContext = Depends(get_current_context),
    db: Session = Depends(get_db),
):
    """Declining still has to answer the client, and the answer travels to the
    redirect_uri — so the same registration check the approve path makes has to
    happen here. Without it, a crafted consent link would turn Cancel into an
    open redirect."""
    client = db.get(OAuthClient, body.client_id)
    if client is None or body.redirect_uri not in client.redirect_uris:
        # nowhere safe to send the refusal; the app keeps the user instead
        return {"redirect_to": None}

    query = urlencode(
        {
            "error": "access_denied",
            "error_description": "The user declined the request",
            "state": body.state,
        }
    )
    return {"redirect_to": f"{body.redirect_uri}?{query}"}


@router.post("/oauth/token")
async def token(
    grant_type: str = Form(...),
    code: str | None = Form(default=None),
    redirect_uri: str | None = Form(default=None),
    client_id: str | None = Form(default=None),
    client_secret: str | None = Form(default=None),
    code_verifier: str | None = Form(default=None),
    refresh_token: str | None = Form(default=None),
    db: Session = Depends(get_db),
):
    def fail(error: str, description: str) -> JSONResponse:
        return JSONResponse(
            {"error": error, "error_description": description}, status_code=400
        )

    if grant_type == "refresh_token":
        if not refresh_token:
            return fail("invalid_request", "refresh_token is required")
        rotated = rotate_refresh_token(db, refresh_token)
        if rotated is None:
            return fail("invalid_grant", "Refresh token is expired or already used")
        access, refresh, expires_in = rotated
        return {
            "access_token": access,
            "refresh_token": refresh,
            "token_type": "Bearer",
            "expires_in": expires_in,
        }

    if grant_type != "authorization_code":
        return fail("unsupported_grant_type", f"{grant_type} is not supported")
    if not code or not code_verifier:
        return fail("invalid_request", "code and code_verifier are required")

    row = consume_code(db, code)
    if row is None:
        return fail("invalid_grant", "Authorization code is invalid, expired or used")
    if client_id and row.client_id != client_id:
        return fail("invalid_grant", "Code was not issued to this client")
    if redirect_uri and row.redirect_uri != redirect_uri:
        return fail("invalid_grant", "redirect_uri does not match the authorization")

    client = db.get(OAuthClient, row.client_id)
    if client is None:
        return fail("invalid_client", "Client is no longer registered")
    if client.client_secret_hash:
        if not client_secret or hash_secret(client_secret) != client.client_secret_hash:
            return fail("invalid_client", "Client authentication failed")

    if not verify_pkce(code_verifier, row.code_challenge, row.code_challenge_method):
        return fail("invalid_grant", "PKCE verification failed")

    access, refresh, expires_in = issue_tokens(
        db, client_id=row.client_id, user_id=row.user_id, scope=row.scope
    )
    return {
        "access_token": access,
        "refresh_token": refresh,
        "token_type": "Bearer",
        "expires_in": expires_in,
        "scope": row.scope or DEFAULT_SCOPE,
    }


@router.post("/oauth/revoke")
async def revoke(token: str = Form(...), db: Session = Depends(get_db)):
    """RFC 7009. Answers 200 whether or not the token existed, so it can't be
    used to probe which tokens are live."""
    digest = hash_secret(token)
    rows = (
        db.query(OAuthToken)
        .filter(
            (OAuthToken.access_token_hash == digest)
            | (OAuthToken.refresh_token_hash == digest),
            OAuthToken.revoked_at.is_(None),
        )
        .all()
    )
    for row in rows:
        row.revoked_at = now()
    db.commit()
    return {"ok": True}
