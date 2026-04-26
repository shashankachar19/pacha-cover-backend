# ============================================================
# app/core/auth.py
#
# Firebase + Google OAuth Authentication middleware for FastAPI.
#
# Verification order:
#   1. Development bypass  — token == "test-token"
#   2. Google OAuth token  — verified via Google's userinfo API
#   3. Firebase ID token   — verified via firebase_admin
# ============================================================

from __future__ import annotations

import httpx
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from firebase_admin import auth

security = HTTPBearer(auto_error=False)

from app.core.config import get_settings
from app.core.logging import get_logger

log = get_logger(__name__)

_GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"


def _extract_token(request: Request) -> str | None:
    """Extract the Bearer token from the Authorization header."""
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        return auth_header[7:]
    return None


async def _verify_google_oauth_token(token: str) -> dict | None:
    """
    Verify a Google OAuth access token via the userinfo endpoint.
    Returns user dict on success, None if the token is not a Google OAuth token.
    """
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(
                _GOOGLE_USERINFO_URL,
                headers={"Authorization": f"Bearer {token}"},
            )
        if resp.status_code == 200:
            info = resp.json()
            # Normalise to a Firebase-like claims dict
            return {
                "uid": info.get("sub", info.get("email", "google-user")),
                "email": info.get("email", ""),
                "name": info.get("name", ""),
                "picture": info.get("picture", ""),
                "provider": "google_oauth",
            }
    except Exception as exc:
        log.debug("auth.google_oauth_check_failed", error=str(exc))
    return None


def _verify_firebase_token(token: str) -> dict:
    """Verify a Firebase ID token."""
    try:
        decoded = auth.verify_id_token(token)
        decoded["provider"] = "firebase"
        return decoded
    except auth.ExpiredIdTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired. Please sign in again.",
        )
    except auth.InvalidIdTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token.",
        )
    except Exception as exc:
        log.error("auth.firebase_verify_failed", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication failed.",
        )


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> dict:
    """
    FastAPI dependency — REQUIRED authentication.
    Accepts Google OAuth access tokens OR Firebase ID tokens.
    Raises HTTP 401 if no valid token is present.
    """
    token = _extract_token(request)

    # 1 ── Dev bypass
    settings = get_settings()
    if settings.app_env == "development" and token == "test-token":
        log.warning("auth.test_token_used", user="mock-user")
        return {"uid": "test-user-123", "email": "test@pachacover.com", "provider": "bypass"}

    if token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header.",
        )

    # 2 ── Google OAuth access token (short, no dots → not a JWT)
    #      Google access tokens are opaque strings, not JWTs (no dots).
    #      Firebase ID tokens are JWTs (two dots).
    if token.count(".") < 2:
        user = await _verify_google_oauth_token(token)
        if user:
            log.info("auth.google_oauth_verified", email=user.get("email"))
            return user
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Google OAuth token.",
        )

    # 3 ── Firebase ID token (JWT)
    return _verify_firebase_token(token)


async def get_optional_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> dict | None:
    """
    FastAPI dependency — OPTIONAL authentication.
    Returns decoded claims if a valid token is present, else None.
    """
    token = _extract_token(request)
    if token is None:
        return None
    try:
        return await get_current_user(request, credentials)
    except HTTPException:
        return None
