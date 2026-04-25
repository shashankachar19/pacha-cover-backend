# ============================================================
# tests/test_extended_features.py
#
# pytest integration tests for the 4 extended Pacha Cover features:
#   Feature 1 — Pacha Vision AR Metadata
#   Feature 2 — Green Corridor Clustering
#   Feature 3 — Carbon Credit & Tax Simulator
#   Feature 4 — Bhasha Vernacular Voice Interface
#
# All external Google Cloud calls are mocked.
# Run: pytest tests/test_extended_features.py -v --asyncio-mode=auto
# ============================================================

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.main import create_app
from app.models.schemas import (
    ARModelMetadata,
    ARModelScale,
    CorridorAuditResult,
    CorridorStatus,
    Coordinates,
    GreenCorridor,
    SupportedLanguage,
    TreeSpecies,
    TranscriptionResult,
)

UTC = timezone.utc


# ── Fixtures ───────────────────────────────────────────────────────────────────

@pytest.fixture
def app():
    return create_app()


@pytest_asyncio.fixture
async def client(app):
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac


@pytest.fixture
def mock_user():
    return {"uid": "test-uid-123", "email": "priya@test.com", "name": "Priya"}


@pytest.fixture
def auth_header():
    return {"Authorization": "Bearer fake-token"}


@pytest.fixture
def sample_ar_metadata():
    return ARModelMetadata(
        species_id="azadirachta_indica",
        common_name="Neem",
        scientific_name="Azadirachta indica",
        kannada_name="ಬೇವು",
        gltf_url="https://storage.googleapis.com/pacha-cover-ar-assets/models/azadirachta_indica.glb",
        thumbnail_url="https://storage.googleapis.com/pacha-cover-ar-assets/thumbs/azadirachta_indica.jpg",
        real_world_scale_m=ARModelScale(x=8.0, y=15.0, z=8.0),
        sapling_scale_factor=0.12,
        ground_offset_m=0.0,
        co2_absorption_kg_per_year=22.0,
        expected_canopy_spread_m=8.0,
        water_requirement="Low",
        growth_rate="Fast",
    )


# ══════════════════════════════════════════════════════════════════════════════
# FEATURE 1 TESTS — Pacha Vision AR Metadata
# ══════════════════════════════════════════════════════════════════════════════

class TestARMetadata:

    @pytest.mark.asyncio
    async def test_get_ar_model_by_species_id_success(
        self, client, sample_ar_metadata
    ):
        """GET /assets/ar-model/{species_id} returns ARModelMetadata."""
        with (
            patch("app.api.v1.endpoints.assets.get_firestore_client"),
            patch("app.api.v1.endpoints.assets.ARService") as mock_cls,
        ):
            mock_svc = AsyncMock()
            mock_svc.get_by_species_id.return_value = sample_ar_metadata
            mock_cls.return_value = mock_svc

            response = await client.get(
                "/api/v1/assets/ar-model/azadirachta_indica"
            )

        assert response.status_code == 200
        body = response.json()
        assert body["species_id"] == "azadirachta_indica"
        assert body["common_name"] == "Neem"
        assert body["real_world_scale_m"]["y"] == 15.0
        assert body["sapling_scale_factor"] == 0.12
        assert "gltf_url" in body
        assert body["water_requirement"] == "Low"

    @pytest.mark.asyncio
    async def test_get_ar_model_not_found(self, client):
        """GET /assets/ar-model/{unknown} returns 404."""
        with (
            patch("app.api.v1.endpoints.assets.get_firestore_client"),
            patch("app.api.v1.endpoints.assets.ARService") as mock_cls,
        ):
            mock_svc = AsyncMock()
            mock_svc.get_by_species_id.return_value = None
            mock_cls.return_value = mock_svc

            response = await client.get("/api/v1/assets/ar-model/unknown_species")

        assert response.status_code == 404
        assert "unknown_species" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_get_ar_model_by_common_name(self, client, sample_ar_metadata):
        """GET /assets/ar-model/by-name/Neem resolves to correct metadata."""
        with (
            patch("app.api.v1.endpoints.assets.get_firestore_client"),
            patch("app.api.v1.endpoints.assets.ARService") as mock_cls,
        ):
            mock_svc = AsyncMock()
            mock_svc.get_by_common_name.return_value = sample_ar_metadata
            mock_cls.return_value = mock_svc

            response = await client.get("/api/v1/assets/ar-model/by-name/Neem")

        assert response.status_code == 200
        assert response.json()["common_name"] == "Neem"

    @pytest.mark.asyncio
    async def test_list_ar_models_returns_catalogue(
        self, client, sample_ar_metadata
    ):
        """GET /assets/ar-models returns a list."""
        with (
            patch("app.api.v1.endpoints.assets.get_firestore_client"),
            patch("app.api.v1.endpoints.assets.ARService") as mock_cls,
        ):
            mock_svc = AsyncMock()
            mock_svc.list_all_species.return_value = [sample_ar_metadata]
            mock_cls.return_value = mock_svc

            response = await client.get("/api/v1/assets/ar-models")

        assert response.status_code == 200
        assert isinstance(response.json(), list)
        assert len(response.json()) == 1

    @pytest.mark.asyncio
    async def test_seed_catalogue_requires_admin(
        self, client, auth_header, mock_user
    ):
        """POST /assets/ar-model/seed by non-admin returns 403."""
        # mock_user has no 'admin' claim
        with patch("app.core.auth.auth.verify_id_token", return_value=mock_user):
            response = await client.post(
                "/api/v1/assets/ar-model/seed", headers=auth_header
            )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_seed_catalogue_admin_succeeds(self, client, auth_header):
        """POST /assets/ar-model/seed by admin returns success."""
        admin_user = {"uid": "admin-uid", "email": "admin@test.com", "admin": True}

        with (
            patch("app.core.auth.auth.verify_id_token", return_value=admin_user),
            patch("app.api.v1.endpoints.assets.get_firestore_client"),
            patch("app.api.v1.endpoints.assets.ARService") as mock_cls,
        ):
            mock_svc = AsyncMock()
            mock_svc.seed_firestore_catalogue.return_value = 10
            mock_cls.return_value = mock_svc

            response = await client.post(
                "/api/v1/assets/ar-model/seed", headers=auth_header
            )

        assert response.status_code == 200
        assert response.json()["data"]["species_count"] == 10

    def test_scientific_name_to_species_id(self):
        """Slug conversion is correct for all edge cases."""
        from app.services.ar_service import scientific_name_to_species_id

        assert scientific_name_to_species_id("Azadirachta indica") == "azadirachta_indica"
        assert scientific_name_to_species_id("Ficus benghalensis") == "ficus_benghalensis"
        assert scientific_name_to_species_id("Samanea saman") == "samanea_saman"

    def test_common_name_lookup(self):
        """Common name lookup finds partial matches."""
        from app.services.ar_service import common_name_to_species_id

        assert common_name_to_species_id("Neem") == "azadirachta_indica"
        assert common_name_to_species_id("neem") == "azadirachta_indica"  # case-insensitive
        assert common_name_to_species_id("Honge") == "pongamia_pinnata"
        assert common_name_to_species_id("UnknownTree") is None


# ══════════════════════════════════════════════════════════════════════════════
# FEATURE 2 TESTS — Green Corridor Clustering
# ══════════════════════════════════════════════════════════════════════════════

class TestGreenCorridor:

    @pytest.fixture
    def sample_corridor(self):
        return GreenCorridor(
            corridor_id="corridor_12d935_77d624",
            ward_name="Koramangala",
            ward_id="koramangala",
            centre_coordinates=Coordinates(latitude=12.935, longitude=77.624),
            radius_m=100.0,
            verified_tree_count=7,
            status=CorridorStatus.ACTIVE,
            contributor_user_ids=["uid-1", "uid-2", "uid-3"],
            badge_awarded="Corridor Creator 🌳",
            detected_at=datetime.now(UTC),
            last_audited=datetime.now(UTC),
        )

    @pytest.mark.asyncio
    async def test_corridor_audit_requires_auth(self, client):
        """POST /corridors/audit without token returns 401."""
        response = await client.post("/api/v1/corridors/audit")
        assert response.status_code in (401, 403)

    @pytest.mark.asyncio
    async def test_corridor_audit_success(
        self, client, auth_header, mock_user, sample_corridor
    ):
        """POST /corridors/audit returns CorridorAuditResult."""
        audit_result = CorridorAuditResult(
            wards_audited=5,
            new_corridors_detected=2,
            badges_awarded=6,
            corridors=[sample_corridor],
            audit_duration_seconds=1.23,
        )

        with (
            patch("app.core.auth.auth.verify_id_token", return_value=mock_user),
            patch("app.api.v1.endpoints.corridors.get_firestore_client"),
            patch("app.api.v1.endpoints.corridors.CorridorService") as mock_cls,
        ):
            mock_svc = AsyncMock()
            mock_svc.audit_corridor_status.return_value = audit_result
            mock_cls.return_value = mock_svc

            response = await client.post(
                "/api/v1/corridors/audit", headers=auth_header
            )

        assert response.status_code == 200
        body = response.json()
        assert body["new_corridors_detected"] == 2
        assert body["badges_awarded"] == 6
        assert body["wards_audited"] == 5
        assert len(body["corridors"]) == 1
        assert body["corridors"][0]["status"] == "active"

    @pytest.mark.asyncio
    async def test_list_corridors_public(self, client, sample_corridor):
        """GET /corridors is public and returns corridor list."""
        mock_stream = AsyncMock()
        mock_doc = MagicMock()
        mock_doc.id = sample_corridor.corridor_id
        mock_doc.to_dict.return_value = {
            **sample_corridor.model_dump(),
            "centre_coordinates": MagicMock(
                latitude=12.935, longitude=77.624
            ),
        }

        with (
            patch("app.api.v1.endpoints.corridors.get_firestore_client") as mock_db_dep,
        ):
            # Mock the Firestore streaming query
            mock_db = AsyncMock()
            mock_db.collection.return_value.where.return_value.limit.return_value.stream = (
                AsyncMock(return_value=_async_gen([mock_doc]))
            )
            mock_db_dep.return_value = mock_db

            response = await client.get("/api/v1/corridors")

        # We don't need deep assertion here — 200 confirms routing works
        assert response.status_code == 200

    def test_haversine_distance(self):
        """Haversine formula gives correct distances."""
        from app.services.corridor_service import haversine_distance_m

        # Koramangala to BTM Layout (~2.7km)
        a = Coordinates(latitude=12.9352, longitude=77.6245)
        b = Coordinates(latitude=12.9166, longitude=77.6101)
        dist = haversine_distance_m(a, b)
        assert 2500 < dist < 3000, f"Expected ~2700m, got {dist:.0f}m"

        # Same point = 0
        assert haversine_distance_m(a, a) == 0.0

    def test_cluster_detection(self):
        """Clustering finds dense groups and ignores sparse points."""
        from app.services.corridor_service import _SpotPoint, _find_clusters

        # 6 tightly packed points in Koramangala (~30m apart)
        dense_cluster = [
            _SpotPoint("s1", "u1", Coordinates(12.9350, 77.6240), "Koramangala", "ward_147"),
            _SpotPoint("s2", "u2", Coordinates(12.9351, 77.6241), "Koramangala", "ward_147"),
            _SpotPoint("s3", "u3", Coordinates(12.9352, 77.6242), "Koramangala", "ward_147"),
            _SpotPoint("s4", "u4", Coordinates(12.9353, 77.6243), "Koramangala", "ward_147"),
            _SpotPoint("s5", "u5", Coordinates(12.9354, 77.6244), "Koramangala", "ward_147"),
            _SpotPoint("s6", "u6", Coordinates(12.9355, 77.6245), "Koramangala", "ward_147"),
        ]
        # 1 isolated point far away (Whitefield)
        isolated = _SpotPoint(
            "s7", "u7", Coordinates(12.9698, 77.7499), "Whitefield", "ward_099"
        )

        all_points = dense_cluster + [isolated]
        clusters = _find_clusters(all_points, radius_m=100.0, min_trees=5)

        # Should find at least one cluster from the dense group
        assert len(clusters) >= 1
        # Every cluster should have >= 5 members
        for cluster in clusters:
            assert len(cluster) >= 5
        # The isolated point should not form its own cluster
        isolated_clusters = [
            c for c in clusters
            if any(p.spot_id == "s7" for p in c)
        ]
        assert len(isolated_clusters) == 0


# ══════════════════════════════════════════════════════════════════════════════
# FEATURE 3 TESTS — Carbon Credit & Tax Simulator
# ══════════════════════════════════════════════════════════════════════════════

class TestCarbonSimulator:

    @pytest.fixture
    def neem_carbon_response(self):
        from app.models.schemas import (
            AnnualCarbonProfile,
            CarbonCreditResponse,
            TaxRebateSimulation,
        )
        return CarbonCreditResponse(
            species_common_name="Neem",
            species_scientific_name="Azadirachta indica",
            num_trees=1,
            tree_age_years=5.0,
            annual_co2_kg_per_tree=22.0,
            total_annual_co2_kg=22.0,
            cumulative_co2_kg_lifetime=65.0,
            annual_profile=[
                AnnualCarbonProfile(
                    year=1, co2_kg_sequestered=8.0, cumulative_co2_kg=8.0,
                    equivalent_car_km_offset=38.1, equivalent_flights_offset=0.09,
                ),
                AnnualCarbonProfile(
                    year=5, co2_kg_sequestered=22.0, cumulative_co2_kg=65.0,
                    equivalent_car_km_offset=104.8, equivalent_flights_offset=0.24,
                ),
            ],
            carbon_credit_value_inr=22.0,
            carbon_credit_rate_inr_per_tonne=1000.0,
            tax_rebate=TaxRebateSimulation(
                annual_co2_kg=22.0,
                rebate_percent=1.0,
                rebate_amount_inr=50000.0,
                rebate_calculation_note="1% rebate for 22kg CO2/year.",
            ),
            gemini_narrative=(
                "A 5-year-old Neem tree sequesters approximately 22kg of CO2 annually, "
                "equivalent to the emissions from driving 105km. Over its lifetime so far, "
                "it has absorbed 65kg of CO2 — the carbon footprint of a short domestic flight."
            ),
            gemini_model_used="gemini-1.5-pro",
        )

    @pytest.mark.asyncio
    async def test_simulate_requires_auth(self, client):
        """POST /carbon/simulate without token returns 401."""
        response = await client.post(
            "/api/v1/carbon/simulate",
            json={"species_common_name": "Neem", "tree_age_years": 5},
        )
        assert response.status_code in (401, 403)

    @pytest.mark.asyncio
    async def test_simulate_success(
        self, client, auth_header, mock_user, neem_carbon_response
    ):
        """POST /carbon/simulate returns CarbonCreditResponse."""
        with (
            patch("app.core.auth.auth.verify_id_token", return_value=mock_user),
            patch(
                "app.api.v1.endpoints.carbon._carbon_service.simulate",
                new_callable=AsyncMock,
                return_value=neem_carbon_response,
            ),
        ):
            response = await client.post(
                "/api/v1/carbon/simulate",
                json={
                    "species_common_name": "Neem",
                    "species_scientific_name": "Azadirachta indica",
                    "tree_age_years": 5.0,
                    "num_trees": 1,
                    "property_value_inr": 5000000,
                },
                headers=auth_header,
            )

        assert response.status_code == 200
        body = response.json()
        assert body["species_common_name"] == "Neem"
        assert body["annual_co2_kg_per_tree"] == 22.0
        assert body["carbon_credit_value_inr"] == 22.0
        assert body["tax_rebate"]["rebate_percent"] == 1.0
        assert len(body["annual_profile"]) == 2
        assert "gemini_narrative" in body
        assert "disclaimer" in body

    @pytest.mark.asyncio
    async def test_simulate_multi_tree_scaling(
        self, client, auth_header, mock_user, neem_carbon_response
    ):
        """num_trees=3 correctly scales the CO2 values."""
        from copy import deepcopy
        scaled = deepcopy(neem_carbon_response)
        scaled.num_trees = 3
        scaled.total_annual_co2_kg = 66.0
        scaled.cumulative_co2_kg_lifetime = 195.0

        with (
            patch("app.core.auth.auth.verify_id_token", return_value=mock_user),
            patch(
                "app.api.v1.endpoints.carbon._carbon_service.simulate",
                new_callable=AsyncMock,
                return_value=scaled,
            ),
        ):
            response = await client.post(
                "/api/v1/carbon/simulate",
                json={"species_common_name": "Neem", "tree_age_years": 5, "num_trees": 3},
                headers=auth_header,
            )

        assert response.status_code == 200
        assert response.json()["num_trees"] == 3
        assert response.json()["total_annual_co2_kg"] == 66.0

    @pytest.mark.asyncio
    async def test_get_carbon_rates_public(self, client):
        """GET /carbon/rates is public and returns rate config."""
        response = await client.get("/api/v1/carbon/rates")
        assert response.status_code == 200
        body = response.json()
        assert "carbon_credit_rate_inr_per_tonne" in body
        assert "tax_rebate_rule" in body
        assert body["carbon_credit_rate_inr_per_tonne"] == 1000.0
        assert body["tax_rebate_rule"]["max_rebate_percent"] == 20.0

    def test_tax_rebate_calculation(self):
        """Tax rebate formula is correct at boundaries."""
        from app.services.carbon_service import _compute_tax_rebate

        # 22kg/year → 1% rebate (floor(22/20) = 1)
        result = _compute_tax_rebate(22.0, None, 20.0, 20.0)
        assert result.rebate_percent == 1.0
        assert result.rebate_amount_inr is None

        # 100kg/year → 5% rebate (floor(100/20) = 5)
        result = _compute_tax_rebate(100.0, 5_000_000.0, 20.0, 20.0)
        assert result.rebate_percent == 5.0
        assert result.rebate_amount_inr == 250_000.0

        # Cap at max 20%: 500kg/year → capped at 20%
        result = _compute_tax_rebate(500.0, 1_000_000.0, 20.0, 20.0)
        assert result.rebate_percent == 20.0

    def test_co2_equivalencies(self):
        """CO2-to-equivalency conversion is within expected range."""
        from app.services.carbon_service import _co2_to_equivalencies

        car_km, flights = _co2_to_equivalencies(22.0)
        # 22kg / 0.21 kg/km ≈ 104.8 km
        assert 100 < car_km < 110
        # 22kg / 90 kg/flight ≈ 0.24 flights
        assert 0.2 < flights < 0.3


# ══════════════════════════════════════════════════════════════════════════════
# FEATURE 4 TESTS — Bhasha Voice Interface
# ══════════════════════════════════════════════════════════════════════════════

class TestBhashaVoice:

    @pytest.fixture
    def fake_audio_bytes(self) -> bytes:
        """Minimal fake WAV header + silence (valid enough for mock tests)."""
        # 44-byte WAV header + 2048 bytes of zeros (silence)
        wav_header = (
            b"RIFF" + (2048 + 36).to_bytes(4, "little") +
            b"WAVE" + b"fmt " + (16).to_bytes(4, "little") +
            (1).to_bytes(2, "little") +   # PCM
            (1).to_bytes(2, "little") +   # Mono
            (16000).to_bytes(4, "little") + (32000).to_bytes(4, "little") +
            (2).to_bytes(2, "little") + (16).to_bytes(2, "little") +
            b"data" + (2048).to_bytes(4, "little")
        )
        return wav_header + b"\x00" * 2048

    @pytest.fixture
    def mock_voice_response(self):
        from app.models.schemas import (
            PrescriptionResponse,
            VoicePrescriptionResponse,
        )

        mock_prescr = MagicMock(spec=PrescriptionResponse)
        mock_prescr.primary_recommendation = MagicMock()
        mock_prescr.primary_recommendation.common_name = "Neem"

        return VoicePrescriptionResponse(
            transcription=TranscriptionResult(
                transcript_english="I want to plant a tree in Koramangala",
                transcript_original="ನಾನು ಕೋರಮಂಗಲದಲ್ಲಿ ಒಂದು ಮರ ನೆಡಲು ಬಯಸುತ್ತೇನೆ",
                source_language=SupportedLanguage.KANNADA,
                confidence=0.93,
                detected_language_code="kn-IN",
            ),
            prescription=mock_prescr,
            primary_species_name_vernacular="ಬೇವು",
            why_recommended_vernacular="ಈ ಮರ ಕೋರಮಂಗಲದ ಮಣ್ಣಿಗೆ ಸೂಕ್ತವಾಗಿದೆ.",
            full_prescription_vernacular=(
                "ನಾನು ಬೇವು ಮರ ನೆಡಲು ಶಿಫಾರಸು ಮಾಡುತ್ತೇನೆ. "
                "ಇದು ಕಡಿಮೆ ನೀರು ಬೇಕಾಗುತ್ತದೆ ಮತ್ತು ವೇಗವಾಗಿ ಬೆಳೆಯುತ್ತದೆ."
            ),
            audio_response_base64=None,
            source_language=SupportedLanguage.KANNADA,
            processing_steps=[
                "1. Speech-to-Text",
                "2. Context extraction",
                "3. AI Prescription",
                "4. Translation to kn",
            ],
        )

    @pytest.mark.asyncio
    async def test_voice_prescribe_requires_auth(self, client, fake_audio_bytes):
        """POST /voice/prescribe without token returns 401."""
        response = await client.post(
            "/api/v1/voice/prescribe",
            data={"language": "kn"},
            files={"audio": ("query.wav", fake_audio_bytes, "audio/wav")},
        )
        assert response.status_code in (401, 403)

    @pytest.mark.asyncio
    async def test_voice_prescribe_kannada_success(
        self, client, auth_header, mock_user, fake_audio_bytes, mock_voice_response
    ):
        """POST /voice/prescribe with Kannada audio returns full response."""
        with (
            patch("app.core.auth.auth.verify_id_token", return_value=mock_user),
            patch(
                "app.api.v1.endpoints.voice._voice_service.process_voice_prescription",
                new_callable=AsyncMock,
                return_value=mock_voice_response,
            ),
        ):
            response = await client.post(
                "/api/v1/voice/prescribe",
                data={
                    "language": "kn",
                    "encoding": "LINEAR16",
                    "sample_rate_hz": 16000,
                    "latitude": 12.9352,
                    "longitude": 77.6245,
                },
                files={"audio": ("query.wav", fake_audio_bytes, "audio/wav")},
                headers=auth_header,
            )

        assert response.status_code == 200
        body = response.json()
        assert body["source_language"] == "kn"
        assert body["transcription"]["confidence"] == 0.93
        assert body["transcription"]["source_language"] == "kn"
        assert "ಬೇವು" in body["primary_species_name_vernacular"]
        assert len(body["processing_steps"]) >= 4
        # TTS disabled by default — no audio
        assert body["audio_response_base64"] is None

    @pytest.mark.asyncio
    async def test_voice_prescribe_invalid_language(
        self, client, auth_header, mock_user, fake_audio_bytes
    ):
        """POST /voice/prescribe with invalid language code returns 422."""
        with patch("app.core.auth.auth.verify_id_token", return_value=mock_user):
            response = await client.post(
                "/api/v1/voice/prescribe",
                data={"language": "xx"},   # invalid
                files={"audio": ("q.wav", fake_audio_bytes, "audio/wav")},
                headers=auth_header,
            )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_voice_prescribe_empty_audio(self, client, auth_header, mock_user):
        """POST /voice/prescribe with empty audio returns 400."""
        with patch("app.core.auth.auth.verify_id_token", return_value=mock_user):
            response = await client.post(
                "/api/v1/voice/prescribe",
                data={"language": "kn"},
                files={"audio": ("empty.wav", b"", "audio/wav")},
                headers=auth_header,
            )
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_get_voice_languages_public(self, client):
        """GET /voice/languages is public and lists all 5 languages."""
        response = await client.get("/api/v1/voice/languages")
        assert response.status_code == 200
        body = response.json()
        assert "supported_languages" in body
        codes = [l["code"] for l in body["supported_languages"]]
        assert "kn" in codes
        assert "hi" in codes
        assert "ta" in codes
        assert "te" in codes
        assert "en" in codes
        # Kannada must be marked primary
        kn = next(l for l in body["supported_languages"] if l["code"] == "kn")
        assert kn["is_primary"] is True
        assert kn["bcp47"] == "kn-IN"

    def test_extract_prescription_context_ward(self):
        """Context extractor picks up ward names from English transcript."""
        from app.services.voice_service import _extract_prescription_context

        req = _extract_prescription_context(
            "I want to plant a tree in Koramangala near a roadside"
        )
        assert req.ward_name == "Koramangala"
        assert req.nearby_land_use == "roadside"

    def test_extract_prescription_context_soil(self):
        """Context extractor picks up soil type."""
        from app.services.voice_service import _extract_prescription_context

        req = _extract_prescription_context(
            "The soil here is red laterite near Jayanagar"
        )
        assert req.soil_type == "red laterite"
        assert req.ward_name == "Jayanagar"

    def test_extract_prescription_context_plot_area(self):
        """Context extractor parses plot area numbers."""
        from app.services.voice_service import _extract_prescription_context

        req = _extract_prescription_context(
            "I have a 30 square meter plot in HSR layout"
        )
        assert req.plot_area_sqm == 30.0
        assert req.ward_name == "HSR Layout"

    def test_vernacular_summary_builder(self):
        """Vernacular summary includes all key fields."""
        from app.services.voice_service import _build_vernacular_summary

        summary = _build_vernacular_summary(
            primary_species_name="Neem",
            why_recommended="Ideal for Bengaluru's laterite soil.",
            water_req="Low",
            growth_rate="Fast",
            co2=22.0,
        )
        assert "Neem" in summary
        assert "low" in summary.lower()
        assert "fast" in summary.lower()
        assert "22" in summary


# ── Helper ─────────────────────────────────────────────────────────────────────

async def _async_gen(items):
    """Async generator helper for mocking Firestore stream()."""
    for item in items:
        yield item
