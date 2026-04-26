from __future__ import annotations

import math
from datetime import datetime, timezone

from google.cloud.firestore import AsyncClient, GeoPoint
from google.cloud.firestore_v1.transforms import ArrayUnion, Increment

from app.core.logging import get_logger
from app.models.firestore_collections import Collections, FirestoreFields
from app.models.schemas import (
    CommunityGeofence,
    CommunityGoalType,
    CommunityLeaderboardEntry,
    CommunityProgressOut,
    Coordinates,
)

log = get_logger(__name__)
UTC = timezone.utc
EARTH_RADIUS_KM = 6371.0


def _haversine_km(a: Coordinates, b: Coordinates) -> float:
    lat1, lon1 = math.radians(a.latitude), math.radians(a.longitude)
    lat2, lon2 = math.radians(b.latitude), math.radians(b.longitude)
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    h = (
        math.sin(dlat / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    )
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(h))


def _ward_name_from_id(community_id: str) -> str | None:
    parts = community_id.split("_")
    if len(parts) < 2:
        return None
    ward_tokens = parts[1:]
    return " ".join(token.capitalize() for token in ward_tokens)


class CommunityService:
    def __init__(self, db: AsyncClient) -> None:
        self._db = db
        self._col = db.collection(Collections.COMMUNITIES)

    def _parse_geofence(self, geofence: dict | None) -> CommunityGeofence | None:
        if not geofence:
            return None
        center = geofence.get(FirestoreFields.CENTER) or geofence.get(
            FirestoreFields.CENTER.capitalize()
        )
        radius_km = geofence.get(FirestoreFields.RADIUS_KM)
        if not center or radius_km is None:
            return None

        if isinstance(center, GeoPoint):
            coords = Coordinates(latitude=center.latitude, longitude=center.longitude)
        elif isinstance(center, (list, tuple)) and len(center) == 2:
            coords = Coordinates(latitude=float(center[0]), longitude=float(center[1]))
        elif isinstance(center, dict):
            coords = Coordinates(
                latitude=float(center.get("latitude")),
                longitude=float(center.get("longitude")),
            )
        else:
            return None

        return CommunityGeofence(center=coords, radius_km=float(radius_km))

    def deterministic_fallback_communities(self) -> list[CommunityProgressOut]:
        now = datetime.now(UTC)
        fallback = CommunityProgressOut(
            community_id="ward_koramangala",
            ward_name="Koramangala",
            goal_type=CommunityGoalType.TREE_COUNT,
            target_value=500,
            current_value=0,
            members_count=0,
            geofence=CommunityGeofence(
                center=Coordinates(latitude=12.9352, longitude=77.6245),
                radius_km=2.0,
            ),
            progress_percent=0.0,
            target_reached=False,
            last_updated=now,
        )
        return [fallback]

    def _to_progress_out(self, doc_id: str, data: dict) -> CommunityProgressOut | None:
        geofence = self._parse_geofence(data.get(FirestoreFields.GEOFENCE))
        if geofence is None:
            return None

        target = int(data.get(FirestoreFields.TARGET_VALUE, 0))
        if target <= 0:
            return None
        current = int(data.get(FirestoreFields.CURRENT_VALUE, 0))
        progress = round(min(100.0, (current / target) * 100), 2)

        members = data.get(FirestoreFields.MEMBERS) or []
        community_id = data.get(FirestoreFields.COMMUNITY_ID, doc_id)

        return CommunityProgressOut(
            community_id=community_id,
            ward_name=data.get("ward_name") or _ward_name_from_id(community_id),
            goal_type=CommunityGoalType(
                data.get(FirestoreFields.GOAL_TYPE, CommunityGoalType.TREE_COUNT.value)
            ),
            target_value=target,
            current_value=current,
            members_count=len(members),
            geofence=geofence,
            progress_percent=progress,
            target_reached=current >= target,
            last_updated=data.get(FirestoreFields.LAST_UPDATED),
        )

    async def list_communities(self, limit: int = 50) -> list[CommunityProgressOut]:
        results: list[CommunityProgressOut] = []
        query = self._col.limit(limit)
        async for doc in query.stream():
            community = self._to_progress_out(doc.id, doc.to_dict() or {})
            if community:
                results.append(community)
        return results

    async def get_ward_leaderboard(
        self, limit: int = 10
    ) -> list[CommunityLeaderboardEntry]:
        communities = await self.list_communities(limit=200)
        communities.sort(
            key=lambda c: (c.progress_percent, c.current_value, c.members_count),
            reverse=True,
        )
        trimmed = communities[:limit]
        return [
            CommunityLeaderboardEntry(
                rank=i + 1,
                community_id=c.community_id,
                ward_name=c.ward_name,
                current_value=c.current_value,
                target_value=c.target_value,
                progress_percent=c.progress_percent,
                members_count=c.members_count,
            )
            for i, c in enumerate(trimmed)
        ]

    async def update_community_progress(
        self,
        *,
        user_id: str,
        user_location: Coordinates,
        tree_count: int = 1,
    ) -> list[str]:
        if tree_count <= 0:
            return []

        now = datetime.now(UTC)
        matched_ids: list[str] = []
        scanned_count = 0
        invalid_geofence_count = 0

        log.info(
            "community.progress_update_started",
            uid=user_id,
            tree_count=tree_count,
            latitude=user_location.latitude,
            longitude=user_location.longitude,
        )

        async for doc in self._col.stream():
            scanned_count += 1
            data = doc.to_dict() or {}
            geofence = self._parse_geofence(data.get(FirestoreFields.GEOFENCE))
            if geofence is None:
                invalid_geofence_count += 1
                continue

            distance_km = _haversine_km(user_location, geofence.center)
            if distance_km > geofence.radius_km:
                continue

            current_before = int(data.get(FirestoreFields.CURRENT_VALUE, 0))
            target_value = int(data.get(FirestoreFields.TARGET_VALUE, 0))
            await self._col.document(doc.id).set(
                {
                    FirestoreFields.CURRENT_VALUE: Increment(tree_count),
                    FirestoreFields.MEMBERS: ArrayUnion([user_id]),
                    FirestoreFields.LAST_UPDATED: now,
                },
                merge=True,
            )
            matched_ids.append(doc.id)
            log.info(
                "community.progress_match_applied",
                uid=user_id,
                community_id=doc.id,
                distance_km=round(distance_km, 4),
                radius_km=geofence.radius_km,
                current_before=current_before,
                current_expected_after=current_before + tree_count,
                target_value=target_value,
            )

        log.info(
            "community.progress_update_finished",
            uid=user_id,
            scanned_communities=scanned_count,
            invalid_geofences=invalid_geofence_count,
            matched_count=len(matched_ids),
            matched_communities=matched_ids,
            tree_count=tree_count,
        )

        return matched_ids
