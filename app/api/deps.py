from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from firebase_admin import auth

from app.core.logging import get_logger

log = get_logger(__name__)

# Standard Bearer token dependency for OpenAPI swagger
security = HTTPBearer()

def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> dict:
    """
    FastAPI Dependency to secure endpoints.
    Requires a valid Firebase ID Token passed in the Authorization header.
    Returns the decoded user dictionary (uid, email, etc).
    """
    token = credentials.credentials
    try:
        # Verify the Firebase ID token
        decoded_token = auth.verify_id_token(token)
        log.info("auth.token_verified", uid=decoded_token.get("uid"))
        return decoded_token
    except Exception as exc:
        log.warning("auth.token_invalid", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
