# ============================================================
# app/services/ledger_service.py
#
# "Green Ledger" — the core data layer for the Adopt-a-Spot feature.
#
# All tree adoption records live in Firestore under:
#   adopted_spots/{spot_id}
#
# This service is intentionally thin — it's a clean data-access
# layer. Business logic (point calculation, status transitions)
# lives in the endpoint handlers or helper utilities.
#
# Firestore design decisions:
#   • spot_id  = auto-generated UUID (not Firestore's push-ID)
#     so it's URL-safe and predictable for deep-linking.
#   • Coordinates stored as a Firestore GeoPoint for native
#     geo-query support (requires a composite index).
#   • All timestamps stored as UTC datetime objects; Firestore
#     serialises them as Timestamps automatically.
# ============================================================

import uuid
from datetime import datetime, timezone

from google.cloud.firestore import AsyncClient, GeoPoint
from google.cloud.firestore_v1 import AsyncDocumentReference

from app.core.logging import get_logger
from app.models.firestore_collections import Collections, FirestoreFields
from app.models.schemas import (
    AdoptSpotCreate,
    AdoptSpotOut,
    AdoptSpotUpdate,
    AdoptionStatus,
    Coordinates,
)

log = get_logger(__name__)

UTC = timezone.utc


def _doc_to_adopt_spot(doc_id: str, data: dict) -> AdoptSpotOut:
    """
    Convert a raw Firestore document dict → AdoptSpotOut Pydantic model.
    Handles GeoPoint → Coordinates conversion.
    """
    geo: GeoPoint | None = data.get("coordinates")
    coords = (
        Coordinates(latitude=geo.latitude, longitude=geo.longitude)
        if geo
        else Coordinates(latitude=0.0, longitude=0.0)
    )

    return AdoptSpotOut(
        spot_id=doc_id,
        user_id=data["user_id"],
        coordinates=coords,
        spot_name=data["spot_name"],
        ward_name=data["ward_name"],
        species_common_name=data["species_common_name"],
        species_scientific_name=data.get("species_scientific_name"),
        notes=data.get("notes"),
        status=AdoptionStatus(data.get("status", AdoptionStatus.PLEDGED)),
        is_public=data.get("is_public", True),
        green_points_earned=data.get("green_points_earned", 0),
        verification_count=data.get("verification_count", 0),
        adopted_at=data.get("adopted_at", datetime.now(UTC)),
        last_updated=data.get("last_updated", datetime.now(UTC)),
    )


class LedgerService:
    """
    CRUD operations for the Green Ledger (adopted_spots collection).
    Injected with an AsyncClient per-request via FastAPI DI.
    """

    def __init__(self, db: AsyncClient) -> None:
        self._db = db
        self._col = db.collection(Collections.ADOPTED_SPOTS)

    # ── Create ─────────────────────────────────────────────────────────────────

    async def adopt_spot(
        self, user_id: str, payload: AdoptSpotCreate
    ) -> AdoptSpotOut:
        """
        Record a new Adopt-a-Spot pledge in Firestore.
        Also increments the ward's adopted_spots_count counter.
        """
        spot_id = str(uuid.uuid4())
        now = datetime.now(UTC)

        doc_data = {
            "user_id": user_id,
            "coordinates": GeoPoint(
                payload.coordinates.latitude, payload.coordinates.longitude
            ),
            "spot_name": payload.spot_name,
            "ward_name": payload.ward_name,
            "species_common_name": payload.species_common_name,
            "species_scientific_name": payload.species_scientific_name,
            "notes": payload.notes,
            "status": AdoptionStatus.PLEDGED.value,
            "is_public": payload.is_public,
            "green_points_earned": 0,
            "verification_count": 0,
            "adopted_at": now,
            "last_updated": now,
        }

        # ── Batch write: spot + user counter + ward counter ────────────────
        batch = self._db.batch()

        spot_ref: AsyncDocumentReference = self._col.document(spot_id)
        batch.set(spot_ref, doc_data)

        # Increment user's total_trees_adopted
        user_ref = self._db.collection(Collections.USERS).document(user_id)
        batch.set(
            user_ref,
            {
                FirestoreFields.TOTAL_TREES_ADOPTED:
                    _firestore_increment(1),
                FirestoreFields.TOTAL_GREEN_POINTS:
                    _firestore_increment(10),  # Points for pledging
            },
            merge=True
        )

        # Increment ward's adopted_spots_count
        ward_ref = (
            self._db.collection(Collections.WARD_HEAT_DATA)
            .document(_ward_id_from_name(payload.ward_name))
        )
        batch.set(
            ward_ref,
            {FirestoreFields.ADOPTED_SPOTS_COUNT: _firestore_increment(1)},
            merge=True,
        )

        await batch.commit()

        log.info(
            "ledger.spot_adopted",
            spot_id=spot_id,
            user_id=user_id,
            ward=payload.ward_name,
            species=payload.species_common_name,
        )

        return _doc_to_adopt_spot(spot_id, doc_data)

    # ── Read (single) ──────────────────────────────────────────────────────────

    async def get_spot(self, spot_id: str) -> AdoptSpotOut | None:
        """Fetch one adopted spot by its ID."""
        doc = await self._col.document(spot_id).get()
        if not doc.exists:
            return None
        return _doc_to_adopt_spot(doc.id, doc.to_dict())

    # ── Read (list) ────────────────────────────────────────────────────────────

    async def list_user_spots(
        self, user_id: str, limit: int = 20, offset: int = 0
    ) -> list[AdoptSpotOut]:
        """
        Return all spots adopted by a given user.
        Ordered by most recently adopted first.
        Requires a Firestore composite index on (user_id ASC, adopted_at DESC).
        """
        query = (
            self._col
            .where(filter=_where("user_id", "==", user_id))
            .order_by("adopted_at", direction="DESCENDING")
            .limit(limit)
            .offset(offset)
        )

        docs = query.stream()
        results = []
        async for doc in docs:
            results.append(_doc_to_adopt_spot(doc.id, doc.to_dict()))

        log.debug(
            "ledger.list_user_spots",
            user_id=user_id,
            count=len(results),
        )
        return results

    async def list_public_spots(
        self,
        ward_name: str | None = None,
        limit: int = 50,
    ) -> list[AdoptSpotOut]:
        """
        Return publicly visible spots — used for the community map.
        Optionally filtered by ward.
        """
        query = self._col.where(
            filter=_where(FirestoreFields.IS_PUBLIC, "==", True)
        )

        if ward_name:
            query = query.where(
                filter=_where(FirestoreFields.WARD_NAME, "==", ward_name)
            )

        query = query.limit(limit)

        results = []
        async for doc in query.stream():
            results.append(_doc_to_adopt_spot(doc.id, doc.to_dict()))

        return results

    async def get_leaderboard(self, limit: int = 10) -> list[dict]:
        """
        Fetch top users by total_green_points.
        Used by the Profile page to show city-wide or ward-level rankings.
        """
        query = (
            self._db.collection(Collections.USERS)
            .order_by(FirestoreFields.TOTAL_GREEN_POINTS, direction="DESCENDING")
            .limit(limit)
        )
        
        results = []
        async for doc in query.stream():
            data = doc.to_dict() or {}
            results.append({
                "uid": doc.id,
                "name": data.get("name", "Unknown User"),
                "email": data.get("email", ""),
                "total_green_points": data.get(FirestoreFields.TOTAL_GREEN_POINTS, 0),
                "picture": data.get("picture", "")
            })
        return results

    async def get_ward_adoption_counts(self) -> dict[str, int]:
        """
        Aggregate adopted_spots_count per ward.
        Used by the heat-map endpoint to enrich WardHeatData.
        Returns {ward_id: count}.
        """
        counts: dict[str, int] = {}
        async for doc in self._db.collection(Collections.WARD_HEAT_DATA).stream():
            data = doc.to_dict() or {}
            counts[doc.id] = data.get(FirestoreFields.ADOPTED_SPOTS_COUNT, 0)
        return counts

    # ── Update ─────────────────────────────────────────────────────────────────

    async def update_spot(
        self, spot_id: str, user_id: str, payload: AdoptSpotUpdate
    ) -> AdoptSpotOut | None:
        """
        Partial update — only the fields present in payload are written.
        Enforces ownership (user_id must match).
        """
        existing = await self.get_spot(spot_id)
        if existing is None:
            return None
        if existing.user_id != user_id:
            raise PermissionError("Cannot update a spot you did not adopt.")

        updates: dict = {"last_updated": datetime.now(UTC)}
        if payload.spot_name is not None:
            updates["spot_name"] = payload.spot_name
        if payload.notes is not None:
            updates["notes"] = payload.notes
        if payload.status is not None:
            updates["status"] = payload.status.value
        if payload.is_public is not None:
            updates["is_public"] = payload.is_public

        await self._col.document(spot_id).update(updates)

        log.info("ledger.spot_updated", spot_id=spot_id, fields=list(updates.keys()))
        # Re-fetch and return the updated document
        return await self.get_spot(spot_id)

    # ── Delete ─────────────────────────────────────────────────────────────────

    async def delete_spot(self, spot_id: str, user_id: str) -> bool:
        """
        Soft-delete by setting status = ABANDONED.
        Hard deletes are reserved for admin operations only.
        Returns True if the spot was found and abandoned.
        """
        existing = await self.get_spot(spot_id)
        if existing is None:
            return False
        if existing.user_id != user_id:
            raise PermissionError("Cannot delete a spot you did not adopt.")

        await self._col.document(spot_id).update(
            {
                "status": AdoptionStatus.ABANDONED.value,
                "last_updated": datetime.now(UTC),
            }
        )

        log.info("ledger.spot_abandoned", spot_id=spot_id, user_id=user_id)
        return True

    # ── Verification helper ────────────────────────────────────────────────────

    async def record_verification(
        self,
        spot_id: str,
        user_id: str,
        verification_id: str,
        points_awarded: int,
        new_status: AdoptionStatus,
    ) -> None:
        """
        Atomic batch that:
          1. Increments verification_count on the spot
          2. Updates spot status (planted → verified → completed)
          3. Adds green_points to both spot and user profile
        Called by the /verify-growth endpoint after Vertex AI approval.
        """
        now = datetime.now(UTC)
        batch = self._db.batch()

        spot_ref = self._col.document(spot_id)
        batch.update(
            spot_ref,
            {
                "verification_count": _firestore_increment(1),
                "status": new_status.value,
                "green_points_earned": _firestore_increment(points_awarded),
                "last_updated": now,
            },
        )

        user_ref = self._db.collection(Collections.USERS).document(user_id)
        batch.set(
            user_ref,
            {
                FirestoreFields.TOTAL_GREEN_POINTS:
                    _firestore_increment(points_awarded),
                FirestoreFields.TOTAL_TREES_VERIFIED:
                    _firestore_increment(1),
            },
            merge=True
        )

        # Store the verification record for audit trail
        ver_ref = (
            self._db.collection(Collections.VERIFICATIONS)
            .document(verification_id)
        )
        batch.set(
            ver_ref,
            {
                "spot_id": spot_id,
                "user_id": user_id,
                "points_awarded": points_awarded,
                "verified_at": now,
                "status": "approved",
            },
        )

        await batch.commit()
        log.info(
            "ledger.verification_recorded",
            spot_id=spot_id,
            verification_id=verification_id,
            points=points_awarded,
        )


# ── Private helpers ────────────────────────────────────────────────────────────

def _firestore_increment(n: int):
    """Returns a Firestore SERVER_TIMESTAMP-style atomic increment."""
    from google.cloud.firestore_v1.transforms import Increment
    return Increment(n)


def _where(field: str, op: str, value):
    """Construct a FieldFilter — compatible with Firestore v2+ API."""
    from google.cloud.firestore_v1.base_query import FieldFilter
    return FieldFilter(field, op, value)


def _ward_id_from_name(ward_name: str) -> str:
    """
    Convert a human-readable ward name to a Firestore document ID.
    In production this would look up the canonical ward_id from a
    reference collection. For the demo we slugify the name.
    """
    return ward_name.lower().replace(" ", "_")
