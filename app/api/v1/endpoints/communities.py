from fastapi import APIRouter, Depends, Query

from app.core.auth import get_optional_user
from app.core.firebase import get_firestore_client
from app.core.logging import get_logger
from app.models.schemas import CommunityLeaderboardEntry, CommunityProgressOut
from app.services.community_service import CommunityService

router = APIRouter(prefix="/communities", tags=["Communities"])
log = get_logger(__name__)


@router.get(
    "",
    response_model=list[CommunityProgressOut],
    summary="List all green communities with live progress",
)
async def list_communities(
    limit: int = Query(default=50, ge=1, le=200),
    db=Depends(get_firestore_client),
    _user=Depends(get_optional_user),
) -> list[CommunityProgressOut]:
    service = CommunityService(db)
    try:
        communities = await service.list_communities(limit=limit)
        log.info(
            "communities.list_served",
            count=len(communities),
            used_fallback=False,
        )
    except Exception as exc:
        communities = service.deterministic_fallback_communities()
        log.error(
            "communities.list_failed_fallback_served",
            error=str(exc),
            fallback_count=len(communities),
            used_fallback=True,
        )
    return communities


@router.get(
    "/leaderboard",
    response_model=list[CommunityLeaderboardEntry],
    summary="Ward leaderboard by community planting progress",
)
async def community_leaderboard(
    limit: int = Query(default=10, ge=1, le=50),
    db=Depends(get_firestore_client),
    _user=Depends(get_optional_user),
) -> list[CommunityLeaderboardEntry]:
    service = CommunityService(db)
    try:
        leaderboard = await service.get_ward_leaderboard(limit=limit)
        log.info(
            "communities.leaderboard_served",
            count=len(leaderboard),
            used_fallback=False,
        )
    except Exception as exc:
        fallback = service.deterministic_fallback_communities()
        leaderboard = [
            CommunityLeaderboardEntry(
                rank=index + 1,
                community_id=item.community_id,
                ward_name=item.ward_name,
                current_value=item.current_value,
                target_value=item.target_value,
                progress_percent=item.progress_percent,
                members_count=item.members_count,
            )
            for index, item in enumerate(fallback[:limit])
        ]
        log.error(
            "communities.leaderboard_failed_fallback_served",
            error=str(exc),
            fallback_count=len(leaderboard),
            used_fallback=True,
        )
    return leaderboard
