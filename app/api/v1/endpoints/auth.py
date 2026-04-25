from fastapi import APIRouter, Depends

from app.api.deps import get_current_user

router = APIRouter(prefix="/auth", tags=["Authentication"])

@router.get("/me")
async def get_my_profile(current_user: dict = Depends(get_current_user)):
    """
    Returns the currently authenticated user's profile data.
    The Android/Flutter app can call this to verify that the Firebase Token is valid.
    """
    return {
        "success": True,
        "message": "Authentication successful",
        "user": current_user
    }
