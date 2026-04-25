# ============================================================
# app/api/v1/endpoints/assets.py
#
# Feature 1 — "Pacha Vision" AR Asset API
#
# GET /api/v1/assets/ar-model/{species_id}
#     → Full AR metadata for a specific species slug
#
# GET /api/v1/assets/ar-model/by-name/{common_name}
#     → Lookup by common name (e.g. "Neem") — useful when the
#       frontend has a prescription response but not the slug
#
# GET /api/v1/assets/ar-model/by-scientific/{scientific_name}
#     → Lookup by scientific name
#
# GET /api/v1/assets/ar-models
#     → Full catalogue — used by the AR app to preload all models
#
# POST /api/v1/assets/ar-model/seed  (admin only)
#     → Seeds the Firestore ar_models collection from the
#       hardcoded catalogue (run once after deployment)
#
# Auth:
#   Public GET endpoints — no auth required so the AR app can
#   fetch assets before the user logs in.
#   POST /seed — requires auth (admin check via custom claim).
# ============================================================

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import RedirectResponse

from app.core.auth import get_current_user, get_optional_user
from app.core.firebase import get_firestore_client
from app.core.logging import get_logger
from app.models.schemas import APIResponse, ARModelMetadata
from app.services.ar_service import ARService, scientific_name_to_species_id

router = APIRouter(prefix="/assets", tags=["Pacha Vision — AR Assets"])
log = get_logger(__name__)


# ── GET /assets/ar-model/{species_id} ─────────────────────────────────────────

@router.get(
    "/ar-model/{species_id}",
    response_model=ARModelMetadata,
    summary="Get AR 3D model metadata by species ID",
    description=(
        "Returns the `.glb` asset URL, real-world scale, and environmental "
        "overlay data for AR placement of a specific tree species.\n\n"
        "**species_id** is the slugified scientific name: "
        "`Azadirachta indica` → `azadirachta_indica`.\n\n"
        "Use `GET /assets/ar-model/by-name/{common_name}` if you only have "
        "the common name from a `/prescribe` response."
    ),
)
async def get_ar_model_by_species_id(
    species_id: str,
    db=Depends(get_firestore_client),
    _user=Depends(get_optional_user),   # logged for analytics; not required
) -> ARModelMetadata:
    """
    Primary AR metadata lookup used by the Flutter ARCore widget.

    Response includes:
    - `gltf_url` — direct link to the .glb file on GCS/CDN
    - `real_world_scale_m` — bounding box for AR anchor placement
    - `sapling_scale_factor` — scale multiplier for newly planted trees
    - Environmental data cards (CO2, canopy spread, water requirement)
    """
    service = ARService(db)
    meta = await service.get_by_species_id(species_id)

    if meta is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"No AR model found for species_id '{species_id}'. "
                "Use GET /assets/ar-models to list all available species."
            ),
        )

    log.info(
        "ar.model_served",
        species_id=species_id,
        common_name=meta.common_name,
    )
    return meta


# ── GET /assets/ar-model/by-name/{common_name} ────────────────────────────────

@router.get(
    "/ar-model/by-name/{common_name}",
    response_model=ARModelMetadata,
    summary="Get AR model by common name (e.g. 'Neem')",
)
async def get_ar_model_by_common_name(
    common_name: str,
    db=Depends(get_firestore_client),
) -> ARModelMetadata:
    """
    Convenience endpoint: looks up the species_id from the common name
    and returns the same ARModelMetadata as the primary endpoint.

    Case-insensitive. Handles partial matches:
    "Honge" matches "Honge (Pongamia)".
    """
    service = ARService(db)
    meta = await service.get_by_common_name(common_name)

    if meta is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"No AR model found for common name '{common_name}'. "
                "Use GET /assets/ar-models for the full catalogue."
            ),
        )

    return meta


# ── GET /assets/ar-model/by-scientific/{scientific_name} ──────────────────────

@router.get(
    "/ar-model/by-scientific/{scientific_name}",
    response_model=ARModelMetadata,
    summary="Get AR model by scientific name",
)
async def get_ar_model_by_scientific_name(
    scientific_name: str,
    db=Depends(get_firestore_client),
) -> ARModelMetadata:
    """
    Converts the scientific name to a species_id slug internally,
    then returns ARModelMetadata. Useful when the app has a
    `TreeSpecies.scientific_name` value from a prescription response.
    """
    service = ARService(db)
    meta = await service.get_by_scientific_name(scientific_name)

    if meta is None:
        species_id = scientific_name_to_species_id(scientific_name)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"No AR model found for '{scientific_name}' "
                f"(resolved species_id: '{species_id}'). "
                "This species may not yet have a 3D model."
            ),
        )

    return meta


# ── GET /assets/ar-models ──────────────────────────────────────────────────────

@router.get(
    "/ar-models",
    response_model=list[ARModelMetadata],
    summary="List all available AR tree models",
    description=(
        "Returns the full AR species catalogue. "
        "The Flutter app uses this to pre-download .glb assets on Wi-Fi "
        "before the user goes into AR mode in the field."
    ),
)
async def list_ar_models(
    db=Depends(get_firestore_client),
) -> list[ARModelMetadata]:
    """Full catalogue — 10 BBMP-preferred native species."""
    service = ARService(db)
    models = await service.list_all_species()
    log.info("ar.catalogue_listed", count=len(models))
    return models


# ── POST /assets/ar-model/seed ─────────────────────────────────────────────────

@router.post(
    "/ar-model/seed",
    response_model=APIResponse,
    status_code=status.HTTP_200_OK,
    summary="[Admin] Seed Firestore AR catalogue from hardcoded defaults",
    description=(
        "Writes all species entries from the in-process catalogue to "
        "Firestore (merge=True, idempotent). "
        "Run once after initial deployment or when adding new species.\n\n"
        "Requires a Firebase Auth token with `admin: true` custom claim."
    ),
)
async def seed_ar_catalogue(
    current_user: dict = Depends(get_current_user),
    db=Depends(get_firestore_client),
) -> APIResponse:
    """
    Admin endpoint — seeds the ar_models Firestore collection.

    Protected by a custom claim check so only admin accounts
    (set via Firebase Admin SDK: auth.set_custom_user_claims)
    can call this endpoint.
    """
    # Enforce admin custom claim
    if not current_user.get("admin", False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required. Set 'admin: true' custom claim in Firebase.",
        )

    service = ARService(db)
    count = await service.seed_firestore_catalogue()

    log.info(
        "ar.catalogue_seed_complete",
        uid=current_user.get("uid"),
        count=count,
    )
    return APIResponse(
        message=f"Successfully seeded {count} AR model records to Firestore.",
        data={"species_count": count},
    )
