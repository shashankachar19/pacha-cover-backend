# ============================================================
# app/api/v1/endpoints/heatmap.py
#
# Heat Map API
# GET /api/v1/heatmap          → all wards
# GET /api/v1/heatmap/{ward_id} → single ward
#
# Data pipeline:
#   Firestore (adoption counts) + Google Earth Engine (NDVI/LST)
#   → merged WardHeatData list → JSON response
#
# Caching strategy:
#   GEE computations are expensive (~5s per ward).
#   A production deployment should cache this response in
#   Redis or Memorystore with a 30-minute TTL, refreshed by a
#   Cloud Scheduler job. For the hackathon demo, we compute
#   on-demand with a simple in-process LRU cache.
# ============================================================

from datetime import datetime, timezone
from functools import lru_cache
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.core.auth import get_optional_user
from app.core.firebase import get_firestore_client
from app.core.logging import get_logger
from app.models.schemas import APIResponse, HeatMapResponse, WardHeatData
from app.services.earth_engine_service import EarthEngineService
from app.services.ledger_service import LedgerService

router = APIRouter(prefix="/heatmap", tags=["Heat Map"])
log = get_logger(__name__)

# Module-level service instance (initialised once per process)
_ee_service = EarthEngineService()


@router.get(
    "",
    response_model=HeatMapResponse,
    summary="Get ward-level urban heat island data",
    description=(
        "Returns NDVI, Land Surface Temperature, green cover percentage, "
        "and heat-risk score for all monitored BBMP wards. "
        "Data sourced from Google Earth Engine (Landsat 8 + MODIS). "
        "Public endpoint — no authentication required."
    ),
)
async def get_heatmap(
    ward_name: Annotated[
        str | None,
        Query(description="Filter by ward name (partial match, case-insensitive)"),
    ] = None,
    risk_level: Annotated[
        str | None,
        Query(description="Filter by risk level: low | moderate | high | critical"),
    ] = None,
    db=Depends(get_firestore_client),
    current_user: dict | None = Depends(get_optional_user),
) -> HeatMapResponse:
    """
    Aggregate heat + greenery data for Bengaluru's BBMP wards.

    Workflow:
    1. Fetch ward-level adoption counts from Firestore (fast)
    2. Fetch NDVI + LST from Google Earth Engine (slower, cached)
    3. Merge and filter the results
    4. Return structured HeatMapResponse
    """
    log.info(
        "heatmap.request",
        user=current_user.get("uid") if current_user else "anonymous",
        filters={"ward_name": ward_name, "risk_level": risk_level},
    )

    # ── Step 1: Adoption counts from Firestore ─────────────────────────────
    ledger = LedgerService(db)
    try:
        adopted_counts = await ledger.get_ward_adoption_counts()
    except Exception as exc:
        log.warning("heatmap.adoption_counts_failed", error=str(exc))
        adopted_counts = {}

    # ── Step 2: GEE satellite data ─────────────────────────────────────────
    try:
        wards: list[WardHeatData] = await _ee_service.get_ward_heat_data(
            adopted_counts=adopted_counts
        )
    except Exception as exc:
        log.error("heatmap.gee_failed", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Satellite data service temporarily unavailable. "
                "Please retry in a few moments."
            ),
        )

    # ── Step 3: Apply filters ──────────────────────────────────────────────
    if ward_name:
        name_lower = ward_name.lower()
        wards = [w for w in wards if name_lower in w.ward_name.lower()]

    if risk_level:
        wards = [w for w in wards if w.heat_risk_level.value == risk_level.lower()]

    log.info("heatmap.response_ready", ward_count=len(wards))

    return HeatMapResponse(
        wards=wards,
        total_wards=len(wards),
        generated_at=datetime.now(timezone.utc),
    )


@router.get(
    "/{ward_id}",
    response_model=WardHeatData,
    summary="Get heat data for a single ward",
)
async def get_ward_heatmap(
    ward_id: str,
    db=Depends(get_firestore_client),
) -> WardHeatData:
    """
    Fetch heat and greenery data for one specific BBMP ward.
    Uses the same GEE pipeline but filtered to a single ward.
    """
    adopted_counts = {}
    try:
        ledger = LedgerService(db)
        adopted_counts = await ledger.get_ward_adoption_counts()
    except Exception:
        pass

    wards = await _ee_service.get_ward_heat_data(adopted_counts=adopted_counts)

    matched = next((w for w in wards if w.ward_id == ward_id), None)
    if matched is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Ward '{ward_id}' not found. Use GET /heatmap to list all wards.",
        )

    return matched
