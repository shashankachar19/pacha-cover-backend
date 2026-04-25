# ============================================================
# app/api/v1/endpoints/verify.py
#
# Sapling Verification Pipeline
# POST /api/v1/verify-growth
#
# Flow:
#   1. Citizen uploads a photo of their planted sapling
#   2. Image is validated (size, format) and uploaded to GCS
#   3. Vertex AI classifies the image for plant/sapling presence
#   4. On approval → Green Points credited to user in Firestore
#   5. Spot status progresses: planted → verified → completed
#
# Auth: Required (Firebase ID token).
# Max upload: 10MB (enforced by multipart limit below).
#
# Scalability note:
#   For high traffic, replace the synchronous Vertex AI call with
#   a Cloud Tasks queue. The endpoint enqueues the job and returns
#   202 Accepted; a Cloud Function worker processes and updates
#   Firestore. The client polls GET /ledger/{spot_id} for status.
# ============================================================

import uuid
from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    UploadFile,
    status,
)

from app.core.auth import get_current_user
from app.core.config import get_settings
from app.core.firebase import get_firestore_client
from app.core.logging import get_logger
from app.models.schemas import (
    AdoptionStatus,
    VerificationResult,
    VerificationStatus,
)
from app.services.ledger_service import LedgerService
from app.services.vertex_ai_service import VertexAIService

router = APIRouter(prefix="/verify-growth", tags=["Verification Pipeline"])
log = get_logger(__name__)

# Limits
_MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB
_ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp"}

# Singleton Vertex AI service
_vertex_service = VertexAIService()


def _determine_new_status(current_count: int) -> AdoptionStatus:
    """
    Compute the next adoption status based on verification count.
    Lifecycle: pledged → planted → verified → completed (3 verifications)
    """
    if current_count >= 3:
        return AdoptionStatus.COMPLETED
    elif current_count >= 1:
        return AdoptionStatus.VERIFIED
    else:
        return AdoptionStatus.PLANTED


@router.post(
    "",
    response_model=VerificationResult,
    status_code=status.HTTP_200_OK,
    summary="Submit a sapling photo for AI verification",
    description=(
        "Upload a photo (JPEG/PNG/WebP, max 10MB) of your planted sapling. "
        "The image is sent to Vertex AI for plant detection. "
        "On success, Green Points are awarded and your spot status is updated. "
        "The full lifecycle requires 3 successful verifications."
    ),
)
async def verify_growth(
    spot_id: Annotated[str, Form(description="The UUID of your adopted spot")],
    image: Annotated[
        UploadFile,
        File(description="Photo of the planted sapling (JPEG/PNG/WebP, max 10MB)"),
    ],
    current_user: dict = Depends(get_current_user),
    db=Depends(get_firestore_client),
    settings=Depends(get_settings),
) -> VerificationResult:
    """
    End-to-end sapling verification:
      - Validates the uploaded image
      - Runs Vertex AI plant classification
      - Awards Green Points on approval
      - Returns full VerificationResult

    If rejected, the endpoint still returns 200 — the status field
    will be "rejected" and no points are awarded. This lets the
    client display a helpful retry message without treating it as
    an API error.
    """
    uid = current_user["uid"]
    verification_id = str(uuid.uuid4())

    log.info(
        "verify.request",
        uid=uid,
        spot_id=spot_id,
        filename=image.filename,
        content_type=image.content_type,
        verification_id=verification_id,
    )

    # ── Step 1: Validate the uploaded file ────────────────────────────────
    if image.content_type not in _ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=(
                f"Unsupported file type: {image.content_type}. "
                f"Allowed: JPEG, PNG, WebP."
            ),
        )

    image_bytes = await image.read()

    if len(image_bytes) > _MAX_FILE_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Image too large. Maximum size is 10MB.",
        )

    if len(image_bytes) < 1024:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Image appears to be empty or corrupt.",
        )

    # ── Step 2: Verify the spot exists and belongs to this user ───────────
    ledger = LedgerService(db)
    spot = await ledger.get_spot(spot_id)

    if spot is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Spot '{spot_id}' not found in your Green Ledger.",
        )

    if spot.user_id != uid:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only verify your own adopted spots.",
        )

    if spot.status == AdoptionStatus.COMPLETED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "This spot has already completed its full verification lifecycle "
                "(3 verifications). No further submissions needed."
            ),
        )

    # ── Step 3: Vertex AI classification ──────────────────────────────────
    try:
        ai_result = await _vertex_service.verify_sapling_image(
            image_bytes=image_bytes,
            spot_id=spot_id,
            content_type=image.content_type or "image/jpeg",
        )
    except Exception as exc:
        log.error(
            "verify.vertex_ai_error",
            uid=uid,
            spot_id=spot_id,
            error=str(exc),
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Image analysis service is temporarily unavailable. "
                "Please try again in a few minutes."
            ),
        )

    # ── Step 4: Update Firestore if approved ───────────────────────────────
    points_awarded = 0

    if ai_result["status"] == VerificationStatus.APPROVED:
        points_awarded = settings.points_per_verification
        new_verification_count = spot.verification_count + 1
        new_status = _determine_new_status(new_verification_count)

        try:
            await ledger.record_verification(
                spot_id=spot_id,
                user_id=uid,
                verification_id=verification_id,
                points_awarded=points_awarded,
                new_status=new_status,
            )
            log.info(
                "verify.approved",
                uid=uid,
                spot_id=spot_id,
                points=points_awarded,
                new_status=new_status.value,
                verification_count=new_verification_count,
            )
        except Exception as exc:
            log.error(
                "verify.firestore_update_failed",
                uid=uid,
                spot_id=spot_id,
                error=str(exc),
            )
            # Don't surface internal DB errors to the client —
            # the verification was successful, points will be
            # reconciled by a Cloud Function if needed.

    else:
        log.info(
            "verify.rejected",
            uid=uid,
            spot_id=spot_id,
            confidence=ai_result["confidence_score"],
        )

    # ── Step 5: Build and return result ───────────────────────────────────
    return VerificationResult(
        spot_id=spot_id,
        verification_id=verification_id,
        status=ai_result["status"],
        confidence_score=ai_result["confidence_score"],
        detected_labels=ai_result["detected_labels"],
        green_points_awarded=points_awarded,
        message=ai_result["message"],
        image_gcs_uri=ai_result.get("gcs_uri"),
    )
