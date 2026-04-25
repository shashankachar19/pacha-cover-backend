# ============================================================
# app/services/ar_service.py
#
# Feature 1 — "Pacha Vision" AR Metadata Service
#
# Maps tree species recommended by Gemini to 3D model metadata
# stored in Firestore (ar_models collection) and hosted on GCS.
#
# Design:
#   • A static species catalogue is seeded into Firestore once via
#     the /scripts/seed_ar_catalogue.py script.
#   • The service first checks Firestore for a live override
#     (allows updating scale/URL without a redeploy).
#   • Falls back to the hardcoded SPECIES_CATALOGUE if the doc
#     is absent — ensuring zero downtime on a fresh deployment.
#   • species_id is the slugified scientific name:
#       "Azadirachta indica" → "azadirachta_indica"
#
# AR asset pipeline (production):
#   1. Designer exports .glb from Blender/Maya per species
#   2. Upload to gs://pacha-cover-ar-assets/models/{species_id}.glb
#   3. Thumbnail to gs://pacha-cover-ar-assets/thumbs/{species_id}.jpg
#   4. Seed/update Firestore doc in ar_models/{species_id}
# ============================================================

import re
from datetime import datetime, timezone

from google.cloud.firestore import AsyncClient

from app.core.config import get_settings
from app.core.logging import get_logger
from app.models.firestore_collections import Collections
from app.models.schemas import ARModelMetadata, ARModelScale

log = get_logger(__name__)
UTC = timezone.utc

# ── Static species catalogue ──────────────────────────────────────────────────
# Provides sensible defaults for every BBMP-preferred species.
# All measurements are for a mature adult tree; the sapling_scale_factor
# (0.12–0.18) is applied at render time for newly planted adoptions.
#
# Real-world dimensions sourced from:
#   • BBMP Urban Forestry Division species data sheets
#   • FAO Forestry Paper 37 (tropical tree growth rates)
#   • India State of Forest Report 2021 (CO2 sequestration)

_SPECIES_CATALOGUE: dict[str, dict] = {
    "azadirachta_indica": {
        "common_name": "Neem",
        "scientific_name": "Azadirachta indica",
        "kannada_name": "ಬೇವು",
        "real_world_scale_m": {"x": 8.0,  "y": 15.0, "z": 8.0},
        "sapling_scale_factor": 0.12,
        "ground_offset_m": 0.0,
        "co2_absorption_kg_per_year": 22.0,
        "expected_canopy_spread_m": 8.0,
        "water_requirement": "Low",
        "growth_rate": "Fast",
    },
    "pongamia_pinnata": {
        "common_name": "Honge (Pongamia)",
        "scientific_name": "Pongamia pinnata",
        "kannada_name": "ಹೊಂಗೆ",
        "real_world_scale_m": {"x": 9.0,  "y": 18.0, "z": 9.0},
        "sapling_scale_factor": 0.13,
        "ground_offset_m": 0.0,
        "co2_absorption_kg_per_year": 28.0,
        "expected_canopy_spread_m": 9.0,
        "water_requirement": "Low",
        "growth_rate": "Moderate",
    },
    "samanea_saman": {
        "common_name": "Rain Tree",
        "scientific_name": "Samanea saman",
        "kannada_name": "ಮಳೆ ಮರ",
        "real_world_scale_m": {"x": 30.0, "y": 25.0, "z": 30.0},
        "sapling_scale_factor": 0.10,
        "ground_offset_m": 0.0,
        "co2_absorption_kg_per_year": 48.0,
        "expected_canopy_spread_m": 30.0,
        "water_requirement": "Medium",
        "growth_rate": "Fast",
    },
    "delonix_regia": {
        "common_name": "Gulmohar",
        "scientific_name": "Delonix regia",
        "kannada_name": "ಗುಲ್ಮೊಹರ್",
        "real_world_scale_m": {"x": 12.0, "y": 12.0, "z": 12.0},
        "sapling_scale_factor": 0.13,
        "ground_offset_m": 0.0,
        "co2_absorption_kg_per_year": 18.0,
        "expected_canopy_spread_m": 12.0,
        "water_requirement": "Medium",
        "growth_rate": "Fast",
    },
    "cassia_fistula": {
        "common_name": "Indian Laburnum",
        "scientific_name": "Cassia fistula",
        "kannada_name": "ಕಕ್ಕೆ",
        "real_world_scale_m": {"x": 7.0,  "y": 15.0, "z": 7.0},
        "sapling_scale_factor": 0.14,
        "ground_offset_m": 0.0,
        "co2_absorption_kg_per_year": 16.0,
        "expected_canopy_spread_m": 7.0,
        "water_requirement": "Low",
        "growth_rate": "Moderate",
    },
    "terminalia_arjuna": {
        "common_name": "Arjuna",
        "scientific_name": "Terminalia arjuna",
        "kannada_name": "ಅರ್ಜುನ",
        "real_world_scale_m": {"x": 10.0, "y": 20.0, "z": 10.0},
        "sapling_scale_factor": 0.12,
        "ground_offset_m": 0.0,
        "co2_absorption_kg_per_year": 30.0,
        "expected_canopy_spread_m": 10.0,
        "water_requirement": "Medium",
        "growth_rate": "Moderate",
    },
    "ficus_religiosa": {
        "common_name": "Peepal",
        "scientific_name": "Ficus religiosa",
        "kannada_name": "ಅಶ್ವತ್ಥ",
        "real_world_scale_m": {"x": 15.0, "y": 30.0, "z": 15.0},
        "sapling_scale_factor": 0.10,
        "ground_offset_m": 0.0,
        "co2_absorption_kg_per_year": 100.0,
        "expected_canopy_spread_m": 15.0,
        "water_requirement": "Low",
        "growth_rate": "Slow",
    },
    "ficus_benghalensis": {
        "common_name": "Banyan",
        "scientific_name": "Ficus benghalensis",
        "kannada_name": "ಆಲದ ಮರ",
        "real_world_scale_m": {"x": 40.0, "y": 30.0, "z": 40.0},
        "sapling_scale_factor": 0.08,
        "ground_offset_m": 0.0,
        "co2_absorption_kg_per_year": 80.0,
        "expected_canopy_spread_m": 40.0,
        "water_requirement": "Medium",
        "growth_rate": "Slow",
    },
    "syzygium_cumini": {
        "common_name": "Jamun (Malabar Plum)",
        "scientific_name": "Syzygium cumini",
        "kannada_name": "ನೇರಳೆ",
        "real_world_scale_m": {"x": 8.0,  "y": 20.0, "z": 8.0},
        "sapling_scale_factor": 0.13,
        "ground_offset_m": 0.0,
        "co2_absorption_kg_per_year": 25.0,
        "expected_canopy_spread_m": 8.0,
        "water_requirement": "Low",
        "growth_rate": "Moderate",
    },
    "peltophorum_pterocarpum": {
        "common_name": "Copper Pod",
        "scientific_name": "Peltophorum pterocarpum",
        "kannada_name": "ತಾಮ್ರ ಕಾಯಿ",
        "real_world_scale_m": {"x": 12.0, "y": 15.0, "z": 12.0},
        "sapling_scale_factor": 0.13,
        "ground_offset_m": 0.0,
        "co2_absorption_kg_per_year": 20.0,
        "expected_canopy_spread_m": 12.0,
        "water_requirement": "Low",
        "growth_rate": "Fast",
    },
}

# ── Helpers ────────────────────────────────────────────────────────────────────

def scientific_name_to_species_id(scientific_name: str) -> str:
    """
    Convert a scientific name to a Firestore-safe species_id slug.
    "Azadirachta indica" → "azadirachta_indica"
    "Ficus benghalensis var. krishnae" → "ficus_benghalensis_var_krishnae"
    """
    slug = scientific_name.lower().strip()
    slug = re.sub(r"[^a-z0-9\s]", "", slug)
    slug = re.sub(r"\s+", "_", slug)
    return slug


def common_name_to_species_id(common_name: str) -> str | None:
    """
    Best-effort reverse lookup: common name → species_id.
    Case-insensitive, ignores punctuation.
    Returns None if no match found.
    """
    target = re.sub(r"[^a-z0-9]", "", common_name.lower())
    for sid, data in _SPECIES_CATALOGUE.items():
        candidate = re.sub(r"[^a-z0-9]", "", data["common_name"].lower())
        if target == candidate or target in candidate:
            return sid
    return None


def _build_asset_urls(species_id: str, base_url: str) -> tuple[str, str]:
    """Construct the GCS/CDN URLs for the .glb model and thumbnail."""
    gltf_url = f"{base_url.rstrip('/')}/models/{species_id}.glb"
    thumb_url = f"{base_url.rstrip('/')}/thumbs/{species_id}.jpg"
    return gltf_url, thumb_url


def _catalogue_to_metadata(
    species_id: str, data: dict, base_url: str
) -> ARModelMetadata:
    """Convert a catalogue dict → ARModelMetadata Pydantic model."""
    gltf_url, thumb_url = _build_asset_urls(species_id, base_url)
    return ARModelMetadata(
        species_id=species_id,
        common_name=data["common_name"],
        scientific_name=data["scientific_name"],
        kannada_name=data.get("kannada_name"),
        gltf_url=gltf_url,
        thumbnail_url=thumb_url,
        real_world_scale_m=ARModelScale(**data["real_world_scale_m"]),
        sapling_scale_factor=data.get("sapling_scale_factor", 0.15),
        ground_offset_m=data.get("ground_offset_m", 0.0),
        co2_absorption_kg_per_year=data["co2_absorption_kg_per_year"],
        expected_canopy_spread_m=data["expected_canopy_spread_m"],
        water_requirement=data["water_requirement"],
        growth_rate=data["growth_rate"],
        last_updated=datetime.now(UTC),
    )


# ── Service class ──────────────────────────────────────────────────────────────

class ARService:
    """
    Resolves AR model metadata for a given tree species.

    Lookup priority:
      1. Firestore ar_models/{species_id}  ← live overrides from admin panel
      2. In-process _SPECIES_CATALOGUE     ← always-available fallback

    The Firestore path lets the design team update scales/URLs without
    re-deploying the API.
    """

    def __init__(self, db: AsyncClient) -> None:
        self._db = db
        self._settings = get_settings()

    async def get_by_species_id(
        self, species_id: str
    ) -> ARModelMetadata | None:
        """
        Fetch AR metadata for a species_id slug.
        Returns None if the species is unknown.
        """
        # ── 1. Check Firestore for live override ──────────────────────────
        try:
            doc = await (
                self._db.collection(Collections.AR_MODELS)
                .document(species_id)
                .get()
            )
            if doc.exists:
                data = doc.to_dict()
                log.debug("ar.firestore_hit", species_id=species_id)
                # Firestore doc overrides base_url if gltf_url is stored
                return ARModelMetadata(**data)
        except Exception as exc:
            log.warning(
                "ar.firestore_lookup_failed",
                species_id=species_id,
                error=str(exc),
            )

        # ── 2. Fallback to hardcoded catalogue ───────────────────────────
        data = _SPECIES_CATALOGUE.get(species_id)
        if data:
            log.debug("ar.catalogue_hit", species_id=species_id)
            return _catalogue_to_metadata(
                species_id, data, self._settings.ar_assets_base_url
            )

        log.info("ar.species_not_found", species_id=species_id)
        return None

    async def get_by_scientific_name(
        self, scientific_name: str
    ) -> ARModelMetadata | None:
        """Convenience wrapper that converts scientific name to species_id first."""
        sid = scientific_name_to_species_id(scientific_name)
        return await self.get_by_species_id(sid)

    async def get_by_common_name(
        self, common_name: str
    ) -> ARModelMetadata | None:
        """Convenience wrapper using common name lookup."""
        sid = common_name_to_species_id(common_name)
        if sid is None:
            return None
        return await self.get_by_species_id(sid)

    async def list_all_species(self) -> list[ARModelMetadata]:
        """
        Returns metadata for all species in the catalogue.
        Used by the AR asset preloader in the Flutter app.
        """
        results = []
        base = self._settings.ar_assets_base_url
        for sid, data in _SPECIES_CATALOGUE.items():
            results.append(_catalogue_to_metadata(sid, data, base))
        return results

    async def seed_firestore_catalogue(self) -> int:
        """
        Admin utility — writes all catalogue entries to Firestore.
        Call once via the /scripts/seed_ar_catalogue.py script.
        Returns the number of documents written.
        """
        base = self._settings.ar_assets_base_url
        batch = self._db.batch()
        count = 0

        for sid, data in _SPECIES_CATALOGUE.items():
            meta = _catalogue_to_metadata(sid, data, base)
            ref = self._db.collection(Collections.AR_MODELS).document(sid)
            batch.set(ref, meta.model_dump(), merge=True)
            count += 1

        await batch.commit()
        log.info("ar.catalogue_seeded", count=count)
        return count
