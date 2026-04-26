# ============================================================
# app/api/v1/endpoints/corridors.py
#
# Feature 2 — "Green Corridor" Cluster API
#
# POST /api/v1/corridors/audit
#     → Triggers a full city-wide corridor audit (admin / scheduler)
#
# GET  /api/v1/corridors
#     → Lists all active corridors (public — powers the map layer)
#
# GET  /api/v1/corridors/ward/{ward_id}
#     → Returns corridors within a specific BBMP ward
#
# Auth:
#   POST /audit  → Requires Firebase Auth token.
#                  In production, triggered by a Cloud Scheduler
#                  job using a service account token.
#   GET endpoints → Public (auth optional for analytics).
# ============================================================

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status

from app.core.auth import get_current_user, get_optional_user
from app.core.firebase import get_firestore_client
from app.core.logging import get_logger
from app.models.firestore_collections import Collections
from app.models.schemas import APIResponse, CorridorAuditResult, GreenCorridor, CorridorStatus
from app.services.corridor_service import CorridorService

router = APIRouter(prefix="/corridors", tags=["Green Corridor Clustering"])
log = get_logger(__name__)


# ── POST /corridors/audit ──────────────────────────────────────────────────────

@router.post(
    "/audit",
    response_model=CorridorAuditResult,
    status_code=status.HTTP_200_OK,
    summary="Run city-wide Green Corridor audit",
    description=(
        "Scans all verified adopted spots across Bengaluru, detects "
        "geospatial clusters using Haversine distance, promotes qualifying "
        "clusters (≥5 trees within 100m) to Active Green Corridors, and "
        "awards the **Corridor Creator** badge + 200 Green Points to "
        "all contributing planters.\n\n"
        "This endpoint is idempotent — badges are only awarded once per user "
        "regardless of how many times the audit runs.\n\n"
        "**Typical use:** Called daily at 02:00 IST by a Cloud Scheduler job."
    ),
)
async def trigger_corridor_audit(
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user),
    db=Depends(get_firestore_client),
) -> CorridorAuditResult:
    """
    Runs the corridor detection algorithm synchronously and returns the
    full audit result. For the production Cloud Scheduler call, the
    response is logged but not consumed.

    The audit typically completes in < 5 seconds for ~10,000 verified spots.
    If scaling beyond 100,000 spots, move to a Cloud Task / Pub/Sub pattern.
    """
    uid = current_user.get("uid", "unknown")
    log.info("corridors.audit_triggered", triggered_by=uid)

    service = CorridorService(db)

    try:
        result = await service.audit_corridor_status()
    except Exception as exc:
        log.error("corridors.audit_error", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Corridor audit failed: {str(exc)}",
        )

    log.info(
        "corridors.audit_result",
        new_corridors=result.new_corridors_detected,
        badges=result.badges_awarded,
        duration=result.audit_duration_seconds,
    )
    return result


# ── GET /corridors ─────────────────────────────────────────────────────────────

@router.get(
    "",
    response_model=list[GreenCorridor],
    summary="List all active Green Corridors across Bengaluru",
    description=(
        "Returns every active Green Corridor cluster detected by the last audit. "
        "Used to render the **Green Corridor** overlay on the city heat map. "
        "Public endpoint — no authentication required."
    ),
)
async def list_all_corridors(
    db=Depends(get_firestore_client),
    _user=Depends(get_optional_user),
) -> list[GreenCorridor]:
    """
    Fetches all corridor documents from Firestore with status = active.
    """
    corridors: list[GreenCorridor] = []

    query = (
        db.collection(Collections.GREEN_CORRIDORS)
        .where(
            filter=_where("status", "==", CorridorStatus.ACTIVE.value)
        )
        .limit(500)          # Bengaluru has 198 wards — 500 is a safe ceiling
    )

    async for doc in query.stream():
        data = doc.to_dict() or {}
        geo = data.get("centre_coordinates")
        if geo:
            data["centre_coordinates"] = {
                "latitude": geo.latitude,
                "longitude": geo.longitude,
            }
        try:
            corridors.append(GreenCorridor(**data))
        except Exception as exc:
            log.warning(
                "corridors.deserialise_error", doc_id=doc.id, error=str(exc)
            )

    log.info("corridors.list_served", count=len(corridors))
    return corridors


# ── GET /corridors/ward/{ward_id} ──────────────────────────────────────────────

@router.get(
    "/ward/{ward_id}",
    response_model=list[GreenCorridor],
    summary="Get Green Corridors in a specific BBMP ward",
)
async def get_ward_corridors(
    ward_id: str,
    db=Depends(get_firestore_client),
) -> list[GreenCorridor]:
    """
    Returns active corridors filtered to a specific ward.
    Used by the ward detail panel in the dashboard.

    **ward_id** format: `koramangala`, `hsr_layout`, `jayanagar`
    (lowercased, spaces replaced with underscores).
    """
    service = CorridorService(db)
    corridors = await service.get_ward_corridors(ward_id)

    if not corridors:
        log.info("corridors.ward_none_found", ward_id=ward_id)

    return corridors


# ── Private helpers ────────────────────────────────────────────────────────────

def _where(field: str, op: str, value):
    from google.cloud.firestore_v1.base_query import FieldFilter
    return FieldFilter(field, op, value)
