# ============================================================
# app/api/v1/endpoints/prescribe.py
#
# "Precision Prescription" API
# POST /api/v1/prescribe
#
# Accepts coordinates + optional context, enriches the request
# with satellite NDVI/LST and India Soil Health Card data via
# SoilHealthService, then calls Gemini 2.5 Flash for a highly
# precise native tree recommendation.
#
# Auth: Required (Firebase ID token).
# ============================================================

import asyncio

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.auth import get_current_user
from app.core.config import get_settings
from app.core.logging import get_logger
from app.models.schemas import PrescriptionRequest, PrescriptionResponse
from app.services.gemini_service import GeminiService
from app.services.soil_health_service import SoilHealthService

router = APIRouter(prefix="/prescribe", tags=["Precision Prescription"])
log = get_logger(__name__)

# Singletons — thread-safe and reusable across requests
_gemini_service = GeminiService()
_soil_service = SoilHealthService()


@router.post(
    "",
    response_model=PrescriptionResponse,
    status_code=status.HTTP_200_OK,
    summary="AI-powered tree species recommendation",
    description=(
        "Send GPS coordinates and optional context (land use, soil type, "
        "plot area) to receive a Gemini 2.5 Flash-generated prescription for "
        "the most suitable native tree species for that exact spot in Bengaluru. "
        "The recommendation is automatically enriched with real-time NDVI, "
        "Land Surface Temperature from Google Earth Engine, and soil parameters "
        "(pH, Nitrogen, Organic Carbon) from the India Soil Health Card dataset. "
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
    Tree species prescription powered by Gemini 2.5 Flash + Earth Engine.

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
    lat = request.coordinates.latitude
    lng = request.coordinates.longitude

    log.info("prescribe.request", uid=uid, lat=lat, lng=lng, ward=request.ward_name)

    # ── Step 1: Fetch site health data concurrently in a thread ──────────────
    # get_site_health is synchronous (GEE uses blocking .getInfo()),
    # so we run it in a thread pool to avoid blocking the event loop.
    loop = asyncio.get_event_loop()
    try:
        site_health = await loop.run_in_executor(
            None, _soil_service.get_site_health, lat, lng
        )
        log.info(
            "prescribe.site_health_fetched",
            ndvi=site_health["ndvi"],
            lst=site_health["lst_celsius"],
            soil_zone=site_health["soil"]["zone"],
            source=site_health["data_source"],
        )
    except Exception as exc:
        # Site health enrichment failure is non-fatal — degrade gracefully
        log.warning("prescribe.site_health_failed", error=str(exc))
        site_health = None

    # ── Step 2: Call Gemini with the enriched context ────────────────────────
    try:
        primary, alternatives = await _gemini_service.prescribe_species(
            request, site_health=site_health
        )

    except ValueError as exc:
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
        enriched=site_health is not None,
    )

    return PrescriptionResponse(
        coordinates=request.coordinates,
        primary_recommendation=primary,
        alternative_recommendations=alternatives,
        gemini_model_used=settings.gemini_model,
        soil_analysis=site_health,
    )
