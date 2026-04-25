# ============================================================
# app/api/v1/endpoints/prescribe.py
#
# "Precision Prescription" API
# POST /api/v1/prescribe
#
# Accepts coordinates + optional context, calls Gemini 1.5 Pro,
# and returns a ranked list of tree species tailored to that
# exact Bengaluru microclimate.
#
# Auth: Required (Firebase ID token).
# Rate-limit note: Add SlowAPI middleware in main.py for
#   production to protect the Gemini API quota.
# ============================================================

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.auth import get_current_user
from app.core.config import get_settings
from app.core.logging import get_logger
from app.models.schemas import PrescriptionRequest, PrescriptionResponse
from app.services.gemini_service import GeminiService

router = APIRouter(prefix="/prescribe", tags=["Precision Prescription"])
log = get_logger(__name__)

# Singleton — the GenerativeModel object is thread-safe and reusable
_gemini_service = GeminiService()


@router.post(
    "",
    response_model=PrescriptionResponse,
    status_code=status.HTTP_200_OK,
    summary="AI-powered tree species recommendation",
    description=(
        "Send GPS coordinates and optional context (land use, soil type, "
        "plot area) to receive a Gemini 1.5 Pro-generated prescription for "
        "the most suitable native tree species for that exact spot in Bengaluru. "
        "Includes ecological rationale, water requirements, CO₂ absorption, "
        "and alignment with Rotary's Environment Area of Focus."
    ),
)
async def prescribe_species(
    request: PrescriptionRequest,
    current_user: dict = Depends(get_current_user),
    settings=Depends(get_settings),
) -> PrescriptionResponse:
    """
    Tree species prescription powered by Gemini 1.5 Pro.

    Example request body:
    ```json
    {
      "coordinates": {"latitude": 12.9352, "longitude": 77.6245},
      "nearby_land_use": "roadside",
      "ward_name": "Koramangala"
    }
    ```
    """
    uid = current_user.get("uid", "unknown")
    log.info(
        "prescribe.request",
        uid=uid,
        lat=request.coordinates.latitude,
        lng=request.coordinates.longitude,
        ward=request.ward_name,
    )

    try:
        primary, alternatives = await _gemini_service.prescribe_species(request)

    except ValueError as exc:
        # Gemini returned malformed JSON — rare but possible
        log.error("prescribe.parse_error", uid=uid, error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=(
                "The AI recommendation engine returned an unexpected response. "
                "Please try again."
            ),
        )

    except Exception as exc:
        log.error("prescribe.gemini_error", uid=uid, error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "AI recommendation service is temporarily unavailable. "
                "Please retry in a few moments."
            ),
        )

    log.info(
        "prescribe.success",
        uid=uid,
        primary=primary.common_name,
        alternatives=[s.common_name for s in alternatives],
    )

    return PrescriptionResponse(
        coordinates=request.coordinates,
        primary_recommendation=primary,
        alternative_recommendations=alternatives,
        gemini_model_used=settings.gemini_model,
    )
