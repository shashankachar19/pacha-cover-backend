import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status

from app.core.auth import get_current_user
from app.core.logging import get_logger
from app.models.schemas import VerificationStatus
from app.services.gemini_service import GeminiService

router = APIRouter(prefix="/verify-image", tags=["Verification Pipeline"])
log = get_logger(__name__)

_MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB
_POINTS_ON_APPROVAL = 50
_gemini = GeminiService()


@router.post(
    "",
    status_code=status.HTTP_200_OK,
    summary="Instant AI sapling verification (no spot ID required)",
)
async def verify_image(
    image: Annotated[UploadFile, File(description="Photo of the sapling")],
    current_user: dict = Depends(get_current_user),
) -> dict:
    """Stateless Gemini Vision sapling verification — no Firestore needed."""
    uid = current_user.get("uid", "unknown")
    verification_id = str(uuid.uuid4())

    log.info("verify_image.request", uid=uid, filename=image.filename, content_type=image.content_type)

    # ── Read bytes ──────────────────────────────────────────────────────────
    image_bytes = await image.read()

    if len(image_bytes) > _MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail="Image too large. Maximum size is 10MB.")
    if len(image_bytes) < 1024:
        raise HTTPException(status_code=400, detail="Image appears to be empty or corrupt.")

    # Normalise content-type (browsers sometimes send image/jpg)
    raw_ct = (image.content_type or "image/jpeg").lower()
    if raw_ct in ("image/jpg",):
        raw_ct = "image/jpeg"
    if raw_ct not in {"image/jpeg", "image/png", "image/webp"}:
        raw_ct = "image/jpeg"   # safe fallback — Gemini accepts it

    # ── Gemini Vision ──────────────────────────────────────────────────────
    try:
        ai_result = await _gemini.verify_sapling_image(
            image_bytes=image_bytes,
            spot_id=f"demo-{verification_id[:8]}",
            content_type=raw_ct,
        )
    except Exception as exc:
        log.error("verify_image.gemini_error", uid=uid, error=str(exc))
        raise HTTPException(
            status_code=503,
            detail=f"Image analysis failed: {exc}",
        )

    # ── Parse result ───────────────────────────────────────────────────────
    # ai_result["status"] is a VerificationStatus enum — compare via .value
    raw_status = ai_result.get("status")
    if isinstance(raw_status, VerificationStatus):
        status_str = raw_status.value          # "approved" or "rejected"
    else:
        status_str = str(raw_status or "").lower()

    is_approved = status_str == "approved"
    points = _POINTS_ON_APPROVAL if is_approved else 0
    reasoning = ai_result.get("reasoning") or ai_result.get("message", "")

    log.info(
        "verify_image.result",
        uid=uid,
        status=status_str,
        confidence=ai_result.get("confidence_score"),
        approved=is_approved,
        points=points,
    )

    return {
        "verification_id": verification_id,
        "is_verified": is_approved,
        "status": status_str,
        "confidence_score": ai_result.get("confidence_score", 0.0),
        "detected_labels": ai_result.get("detected_labels", []),
        "reasoning": reasoning,
        "green_points_awarded": points,
        "message": (
            f"Sapling verified. +{points} Green Points awarded."
            if is_approved
            else "Verification failed. Please upload a clear photo of a planted sapling."
        ),
    }
