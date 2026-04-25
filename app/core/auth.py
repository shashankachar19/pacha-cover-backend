# ============================================================
# app/core/auth.py
#
# Firebase Authentication middleware for FastAPI.
#
# Provides two dependency functions:
#   • get_current_user  — REQUIRED auth (raises 401 if missing)
#   • get_optional_user — OPTIONAL auth (returns None if absent)
#
# Both verify the Firebase ID token from the Authorization header
# and return the decoded user claims dict (uid, email, etc.).
# ============================================================

from __future__ import annotations

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from firebase_admin import auth

security = HTTPBearer(auto_error=False)

from app.core.config import get_settings
from app.core.logging import get_logger

log = get_logger(__name__)


def _extract_token(request: Request) -> str | None:
    """Extract the Bearer token from the Authorization header."""
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        return auth_header[7:]
    return None


def _verify_token(token: str) -> dict:
    """
    Verify a Firebase ID token and return the decoded claims.
    Raises HTTPException(401) on invalid/expired tokens.
    """
    try:
        decoded = auth.verify_id_token(token)
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
        log.error("auth.verify_failed", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication failed.",
        )


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(security)
) -> dict:
    """
    FastAPI dependency — REQUIRED authentication.
    Returns the decoded Firebase user claims (uid, email, etc.).
    Raises HTTP 401 if no valid token is present.
    """
    token = _extract_token(request)
    
    settings = get_settings()
    if settings.app_env == "development" and token == "test-token":
        log.warning("auth.test_token_used", user="mock-user")
        return {"uid": "test-user-123", "email": "test@pachacover.com"}
        
    if token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header. Send: Bearer <Firebase ID Token>",
        )
    return _verify_token(token)


async def get_optional_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(security)
) -> dict | None:
    """
    FastAPI dependency — OPTIONAL authentication.
    Returns decoded claims if a valid token is present, else None.
    Used for endpoints that work for both anonymous and logged-in users.
    """
    token = _extract_token(request)
    if token is None:
        return None
    try:
        return _verify_token(token)
    except HTTPException:
        return None
