# ============================================================
# app/api/v1/endpoints/ledger.py
#
# Green Ledger API — "Adopt a Spot" CRUD
#
# POST   /api/v1/ledger/adopt            → pledge to plant a tree
# GET    /api/v1/ledger/my-spots         → list my adopted spots
# GET    /api/v1/ledger/community        → public community map spots
# GET    /api/v1/ledger/{spot_id}        → single spot details
# PATCH  /api/v1/ledger/{spot_id}        → update spot (owner only)
# DELETE /api/v1/ledger/{spot_id}        → abandon spot (owner only)
#
# All write endpoints require Firebase Auth.
# GET /community is public (optional auth for richer data).
# ============================================================

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.core.auth import get_current_user, get_optional_user
from app.core.firebase import get_firestore_client
from app.core.logging import get_logger
from app.models.schemas import (
    APIResponse,
    AdoptSpotCreate,
    AdoptSpotOut,
    AdoptSpotUpdate,
)
from app.services.ledger_service import LedgerService

router = APIRouter(prefix="/ledger", tags=["Green Ledger"])
log = get_logger(__name__)


# ── POST /ledger/adopt ─────────────────────────────────────────────────────────

@router.post(
    "/adopt",
    response_model=AdoptSpotOut,
    status_code=status.HTTP_201_CREATED,
    summary="Adopt a spot — pledge to plant a tree",
    description=(
        "Records the user's commitment to plant a tree at the given coordinates. "
        "Awards 10 Green Points immediately for pledging. "
        "The spot appears on the community heat map once verified."
    ),
)
async def adopt_spot(
    payload: AdoptSpotCreate,
    current_user: dict = Depends(get_current_user),
    db=Depends(get_firestore_client),
) -> AdoptSpotOut:
    """
    Create a new adopted spot in the Green Ledger.

    Example:
    ```json
    {
      "coordinates": {"latitude": 12.9116, "longitude": 77.6389},
      "spot_name": "Near HSR Layout Metro Exit 2",
      "ward_name": "HSR Layout",
      "species_common_name": "Neem",
      "species_scientific_name": "Azadirachta indica",
      "notes": "Empty plot next to footpath, good sunlight",
      "is_public": true
    }
    ```
    """
    uid = current_user["uid"]
    log.info("ledger.adopt_request", uid=uid, ward=payload.ward_name)

    ledger = LedgerService(db)

    try:
        spot = await ledger.adopt_spot(user_id=uid, payload=payload)
    except Exception as exc:
        log.error("ledger.adopt_failed", uid=uid, error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to record your adoption. Please try again.",
        )

    log.info(
        "ledger.adopted",
        uid=uid,
        spot_id=spot.spot_id,
        species=spot.species_common_name,
    )
    return spot


# ── GET /ledger/my-spots ───────────────────────────────────────────────────────

@router.get(
    "/my-spots",
    response_model=list[AdoptSpotOut],
    summary="List all spots adopted by the authenticated user",
)
async def list_my_spots(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    current_user: dict = Depends(get_current_user),
    db=Depends(get_firestore_client),
) -> list[AdoptSpotOut]:
    """
    Returns the authenticated user's Green Ledger — all their adopted spots,
    ordered by most recently adopted.
    """
    uid = current_user["uid"]
    ledger = LedgerService(db)
    spots = await ledger.list_user_spots(user_id=uid, limit=limit, offset=offset)
    log.debug("ledger.my_spots", uid=uid, count=len(spots))
    return spots


# ── GET /ledger/community ──────────────────────────────────────────────────────

@router.get(
    "/community",
    response_model=list[AdoptSpotOut],
    summary="Community map — all public adopted spots",
    description="Public endpoint. Returns spots that users have marked as public.",
)
async def list_community_spots(
    ward_name: str | None = Query(
        default=None, description="Filter by BBMP ward name"
    ),
    limit: int = Query(default=50, ge=1, le=200),
    db=Depends(get_firestore_client),
    current_user: dict | None = Depends(get_optional_user),
) -> list[AdoptSpotOut]:
    """
    Powers the community heat map overlay — showing where citizens
    are actively planting trees across Bengaluru.
    """
    ledger = LedgerService(db)
    spots = await ledger.list_public_spots(ward_name=ward_name, limit=limit)
    log.info(
        "ledger.community_spots",
        ward=ward_name,
        count=len(spots),
        requester=current_user.get("uid") if current_user else "anonymous",
    )
    return spots


# ── GET /ledger/{spot_id} ──────────────────────────────────────────────────────

@router.get(
    "/{spot_id}",
    response_model=AdoptSpotOut,
    summary="Get details of a single adopted spot",
)
async def get_spot(
    spot_id: str,
    db=Depends(get_firestore_client),
    current_user: dict | None = Depends(get_optional_user),
) -> AdoptSpotOut:
    """
    Fetch a single adopted spot by its UUID.
    Private spots are only visible to their owner.
    """
    ledger = LedgerService(db)
    spot = await ledger.get_spot(spot_id)

    if spot is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Spot '{spot_id}' not found.",
        )

    # Privacy: non-public spots only visible to owner
    uid = current_user.get("uid") if current_user else None
    if not spot.is_public and spot.user_id != uid:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This spot is private.",
        )

    return spot


# ── PATCH /ledger/{spot_id} ────────────────────────────────────────────────────

@router.patch(
    "/{spot_id}",
    response_model=AdoptSpotOut,
    summary="Update an adopted spot (owner only)",
)
async def update_spot(
    spot_id: str,
    payload: AdoptSpotUpdate,
    current_user: dict = Depends(get_current_user),
    db=Depends(get_firestore_client),
) -> AdoptSpotOut:
    """
    Partially update a spot. Only the spot owner can update.
    Useful for updating status (pledged → planted) or notes.
    """
    uid = current_user["uid"]
    ledger = LedgerService(db)

    try:
        updated = await ledger.update_spot(
            spot_id=spot_id, user_id=uid, payload=payload
        )
    except PermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)
        )

    if updated is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Spot '{spot_id}' not found.",
        )

    log.info("ledger.spot_updated", uid=uid, spot_id=spot_id)
    return updated


# ── DELETE /ledger/{spot_id} ───────────────────────────────────────────────────

@router.delete(
    "/{spot_id}",
    response_model=APIResponse,
    summary="Abandon an adopted spot (owner only)",
)
async def delete_spot(
    spot_id: str,
    current_user: dict = Depends(get_current_user),
    db=Depends(get_firestore_client),
) -> APIResponse:
    """
    Soft-delete: marks the spot as ABANDONED.
    The record is retained for audit/analytics purposes.
    """
    uid = current_user["uid"]
    ledger = LedgerService(db)

    try:
        deleted = await ledger.delete_spot(spot_id=spot_id, user_id=uid)
    except PermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)
        )

    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Spot '{spot_id}' not found.",
        )

    log.info("ledger.spot_abandoned", uid=uid, spot_id=spot_id)
    return APIResponse(
        message=f"Spot '{spot_id}' has been marked as abandoned."
    )
