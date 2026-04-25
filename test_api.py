# ============================================================
# tests/test_api.py
#
# Integration tests for all Pacha Cover API endpoints.
# Uses pytest-asyncio + httpx.AsyncClient to test the full
# FastAPI application including middleware and DI.
#
# Firebase Auth is mocked — tests don't require a live Firebase project.
# Firestore is mocked via unittest.mock.AsyncMock.
# Gemini and Vertex AI calls are patched to avoid external API costs.
#
# Run:
#   pytest tests/ -v --asyncio-mode=auto
# ============================================================

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.main import create_app
from app.models.schemas import (
    AdoptionStatus,
    Coordinates,
    HeatRiskLevel,
    TreeSpecies,
    VerificationStatus,
    WardHeatData,
)

UTC = timezone.utc

# ── Fixtures ───────────────────────────────────────────────────────────────────

@pytest.fixture
def app():
    """Fresh FastAPI app instance for each test."""
    return create_app()


@pytest_asyncio.fixture
async def client(app):
    """Async test client with ASGI transport."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac


@pytest.fixture
def mock_user():
    """Decoded Firebase token dict returned by auth middleware."""
    return {
        "uid": "test-uid-123",
        "email": "priya@example.com",
        "name": "Priya Sharma",
    }


@pytest.fixture
def auth_header():
    """Authorization header with a fake bearer token."""
    return {"Authorization": "Bearer fake-firebase-token"}


@pytest.fixture
def mock_ward():
    """Sample WardHeatData object."""
    return WardHeatData(
        ward_id="ward_147",
        ward_name="Koramangala",
        avg_land_surface_temp=36.4,
        avg_ndvi=0.18,
        green_cover_percent=22.5,
        heat_risk_score=72.1,
        heat_risk_level=HeatRiskLevel.HIGH,
        adopted_spots_count=14,
        last_updated=datetime.now(UTC),
    )


# ── Health Check ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_health_check(client):
    response = await client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "healthy"
    assert body["service"] == "pacha-cover-api"


@pytest.mark.asyncio
async def test_root(client):
    response = await client.get("/")
    assert response.status_code == 200
    assert "Pacha Cover" in response.json()["message"]


# ── Heat Map ───────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_heatmap_success(client, mock_ward):
    """GET /heatmap returns a list of wards with heat data."""
    with (
        patch(
            "app.api.v1.endpoints.heatmap._ee_service.get_ward_heat_data",
            new_callable=AsyncMock,
            return_value=[mock_ward],
        ),
        patch(
            "app.api.v1.endpoints.heatmap.LedgerService",
        ) as mock_ledger_cls,
    ):
        mock_ledger = AsyncMock()
        mock_ledger.get_ward_adoption_counts.return_value = {"ward_147": 14}
        mock_ledger_cls.return_value = mock_ledger

        # Mock Firestore client
        with patch("app.api.v1.endpoints.heatmap.get_firestore_client"):
            response = await client.get("/api/v1/heatmap")

    assert response.status_code == 200
    body = response.json()
    assert "wards" in body
    assert body["total_wards"] == 1
    ward = body["wards"][0]
    assert ward["ward_id"] == "ward_147"
    assert ward["heat_risk_level"] == "high"
    assert ward["avg_ndvi"] == 0.18


@pytest.mark.asyncio
async def test_get_heatmap_filter_by_risk(client, mock_ward):
    """GET /heatmap?risk_level=high filters correctly."""
    with (
        patch(
            "app.api.v1.endpoints.heatmap._ee_service.get_ward_heat_data",
            new_callable=AsyncMock,
            return_value=[mock_ward],
        ),
        patch("app.api.v1.endpoints.heatmap.LedgerService"),
        patch("app.api.v1.endpoints.heatmap.get_firestore_client"),
    ):
        response = await client.get("/api/v1/heatmap?risk_level=high")

    assert response.status_code == 200
    assert len(response.json()["wards"]) == 1

    # Critical wards should be filtered out
    with (
        patch(
            "app.api.v1.endpoints.heatmap._ee_service.get_ward_heat_data",
            new_callable=AsyncMock,
            return_value=[mock_ward],
        ),
        patch("app.api.v1.endpoints.heatmap.LedgerService"),
        patch("app.api.v1.endpoints.heatmap.get_firestore_client"),
    ):
        response = await client.get("/api/v1/heatmap?risk_level=critical")
    assert len(response.json()["wards"]) == 0


# ── Prescribe ──────────────────────────────────────────────────────────────────

@pytest.fixture
def mock_neem_species():
    return TreeSpecies(
        common_name="Neem",
        scientific_name="Azadirachta indica",
        kannada_name="ಬೇವು",
        why_recommended=(
            "Neem is ideal for this high-temperature roadside spot in "
            "Koramangala. Its dense canopy provides excellent shade and "
            "it thrives in Bengaluru's red laterite soil."
        ),
        expected_canopy_spread_m=8.0,
        water_requirement="Low",
        growth_rate="Fast",
        co2_absorption_kg_per_year=22.0,
    )


@pytest.mark.asyncio
async def test_prescribe_requires_auth(client):
    """POST /prescribe without token returns 403."""
    response = await client.post(
        "/api/v1/prescribe",
        json={"coordinates": {"latitude": 12.93, "longitude": 77.62}},
    )
    assert response.status_code in (401, 403)


@pytest.mark.asyncio
async def test_prescribe_success(client, auth_header, mock_user, mock_neem_species):
    """POST /prescribe returns a Gemini prescription."""
    with (
        patch(
            "app.core.auth.auth.verify_id_token",
            return_value=mock_user,
        ),
        patch(
            "app.api.v1.endpoints.prescribe._gemini_service.prescribe_species",
            new_callable=AsyncMock,
            return_value=(mock_neem_species, []),
        ),
    ):
        response = await client.post(
            "/api/v1/prescribe",
            json={
                "coordinates": {"latitude": 12.9352, "longitude": 77.6245},
                "ward_name": "Koramangala",
                "nearby_land_use": "roadside",
            },
            headers=auth_header,
        )

    assert response.status_code == 200
    body = response.json()
    assert body["primary_recommendation"]["common_name"] == "Neem"
    assert body["primary_recommendation"]["water_requirement"] == "Low"
    assert "disclaimer" in body


@pytest.mark.asyncio
async def test_prescribe_invalid_coordinates(client, auth_header, mock_user):
    """POST /prescribe with out-of-range coordinates returns 422."""
    with patch("app.core.auth.auth.verify_id_token", return_value=mock_user):
        response = await client.post(
            "/api/v1/prescribe",
            json={"coordinates": {"latitude": 999.0, "longitude": 77.62}},
            headers=auth_header,
        )
    assert response.status_code == 422


# ── Green Ledger ───────────────────────────────────────────────────────────────

@pytest.fixture
def sample_spot_payload():
    return {
        "coordinates": {"latitude": 12.9116, "longitude": 77.6389},
        "spot_name": "Near HSR Layout Metro",
        "ward_name": "HSR Layout",
        "species_common_name": "Neem",
        "species_scientific_name": "Azadirachta indica",
        "notes": "Empty plot by footpath",
        "is_public": True,
    }


@pytest.fixture
def sample_spot_out():
    return {
        "spot_id": "abc-123",
        "user_id": "test-uid-123",
        "coordinates": {"latitude": 12.9116, "longitude": 77.6389},
        "spot_name": "Near HSR Layout Metro",
        "ward_name": "HSR Layout",
        "species_common_name": "Neem",
        "species_scientific_name": "Azadirachta indica",
        "notes": "Empty plot by footpath",
        "status": "pledged",
        "is_public": True,
        "green_points_earned": 0,
        "verification_count": 0,
        "adopted_at": datetime.now(UTC).isoformat(),
        "last_updated": datetime.now(UTC).isoformat(),
    }


@pytest.mark.asyncio
async def test_adopt_spot_success(
    client, auth_header, mock_user, sample_spot_payload, sample_spot_out
):
    """POST /ledger/adopt creates a new spot."""
    from app.models.schemas import AdoptSpotOut, Coordinates

    mock_result = AdoptSpotOut(
        spot_id="abc-123",
        user_id="test-uid-123",
        coordinates=Coordinates(latitude=12.9116, longitude=77.6389),
        spot_name="Near HSR Layout Metro",
        ward_name="HSR Layout",
        species_common_name="Neem",
        species_scientific_name="Azadirachta indica",
        notes="Empty plot by footpath",
        status=AdoptionStatus.PLEDGED,
        is_public=True,
        green_points_earned=0,
        verification_count=0,
        adopted_at=datetime.now(UTC),
        last_updated=datetime.now(UTC),
    )

    with (
        patch("app.core.auth.auth.verify_id_token", return_value=mock_user),
        patch("app.api.v1.endpoints.ledger.get_firestore_client"),
        patch("app.api.v1.endpoints.ledger.LedgerService") as mock_cls,
    ):
        mock_svc = AsyncMock()
        mock_svc.adopt_spot.return_value = mock_result
        mock_cls.return_value = mock_svc

        response = await client.post(
            "/api/v1/ledger/adopt",
            json=sample_spot_payload,
            headers=auth_header,
        )

    assert response.status_code == 201
    body = response.json()
    assert body["spot_id"] == "abc-123"
    assert body["status"] == "pledged"
    assert body["ward_name"] == "HSR Layout"


@pytest.mark.asyncio
async def test_get_spot_not_found(client):
    """GET /ledger/{spot_id} with unknown ID returns 404."""
    with (
        patch("app.api.v1.endpoints.ledger.get_firestore_client"),
        patch("app.api.v1.endpoints.ledger.LedgerService") as mock_cls,
    ):
        mock_svc = AsyncMock()
        mock_svc.get_spot.return_value = None
        mock_cls.return_value = mock_svc

        response = await client.get("/api/v1/ledger/nonexistent-id")

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_delete_spot_forbidden(client, auth_header, mock_user):
    """DELETE /ledger/{spot_id} by non-owner returns 403."""
    from app.models.schemas import AdoptSpotOut, Coordinates

    other_user_spot = AdoptSpotOut(
        spot_id="xyz-999",
        user_id="other-user-uid",  # ← different user
        coordinates=Coordinates(latitude=12.9, longitude=77.6),
        spot_name="Someone else's spot",
        ward_name="Jayanagar",
        species_common_name="Peepal",
        status=AdoptionStatus.PLANTED,
        is_public=True,
        adopted_at=datetime.now(UTC),
        last_updated=datetime.now(UTC),
    )

    with (
        patch("app.core.auth.auth.verify_id_token", return_value=mock_user),
        patch("app.api.v1.endpoints.ledger.get_firestore_client"),
        patch("app.api.v1.endpoints.ledger.LedgerService") as mock_cls,
    ):
        mock_svc = AsyncMock()
        mock_svc.delete_spot.side_effect = PermissionError("Not owner")
        mock_cls.return_value = mock_svc

        response = await client.delete(
            "/api/v1/ledger/xyz-999", headers=auth_header
        )

    assert response.status_code == 403


# ── Verification Pipeline ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_verify_growth_approved(client, auth_header, mock_user):
    """POST /verify-growth with a valid image returns APPROVED + points."""
    from app.models.schemas import AdoptSpotOut, Coordinates

    existing_spot = AdoptSpotOut(
        spot_id="spot-001",
        user_id="test-uid-123",
        coordinates=Coordinates(latitude=12.93, longitude=77.62),
        spot_name="Test spot",
        ward_name="Koramangala",
        species_common_name="Neem",
        status=AdoptionStatus.PLANTED,
        is_public=True,
        verification_count=0,
        adopted_at=datetime.now(UTC),
        last_updated=datetime.now(UTC),
    )

    fake_image = b"\xff\xd8\xff" + b"\x00" * 2048  # Minimal fake JPEG bytes

    with (
        patch("app.core.auth.auth.verify_id_token", return_value=mock_user),
        patch("app.api.v1.endpoints.verify.get_firestore_client"),
        patch("app.api.v1.endpoints.verify.LedgerService") as mock_ledger_cls,
        patch("app.api.v1.endpoints.verify._vertex_service") as mock_vertex,
    ):
        mock_ledger = AsyncMock()
        mock_ledger.get_spot.return_value = existing_spot
        mock_ledger.record_verification.return_value = None
        mock_ledger_cls.return_value = mock_ledger

        mock_vertex.verify_sapling_image = AsyncMock(
            return_value={
                "status": VerificationStatus.APPROVED,
                "confidence_score": 0.91,
                "detected_labels": ["plant", "sapling", "leaf"],
                "gcs_uri": "gs://pacha-cover-images/verifications/spot-001/abc.jpg",
                "message": "Sapling verified! 🌱",
            }
        )

        response = await client.post(
            "/api/v1/verify-growth",
            data={"spot_id": "spot-001"},
            files={"image": ("sapling.jpg", fake_image, "image/jpeg")},
            headers=auth_header,
        )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "approved"
    assert body["green_points_awarded"] == 50
    assert "plant" in body["detected_labels"]


@pytest.mark.asyncio
async def test_verify_growth_unsupported_format(client, auth_header, mock_user):
    """POST /verify-growth with a PDF returns 415."""
    with patch("app.core.auth.auth.verify_id_token", return_value=mock_user):
        response = await client.post(
            "/api/v1/verify-growth",
            data={"spot_id": "spot-001"},
            files={"image": ("doc.pdf", b"%PDF-1.4", "application/pdf")},
            headers=auth_header,
        )
    assert response.status_code == 415
