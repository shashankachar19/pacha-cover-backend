# ============================================================
# app/services/earth_engine_service.py
#
# Fetches Normalised Difference Vegetation Index (NDVI) and
# Land Surface Temperature (LST) from Google Earth Engine.
#
# Data sources used:
#   • NDVI  → Landsat 8 OLI/TIRS (bands B5, B4)
#             or MODIS Terra (MOD13Q1)
#   • LST   → Landsat 8 Band 10 (thermal) / MODIS MOD11A2
#
# GEE requires the service account to be allowlisted at:
#   https://code.earthengine.google.com/register
#
# In "mock mode" (GEE creds absent), realistic synthetic data
# is returned so the rest of the stack stays fully functional
# during local development and CI.
# ============================================================

import random
from datetime import datetime, timedelta
from typing import Any

from tenacity import retry, stop_after_attempt, wait_exponential

from app.core.config import get_settings
from app.core.logging import get_logger
from app.models.schemas import HeatRiskLevel, WardHeatData

log = get_logger(__name__)

# ── Bengaluru BBMP ward reference data ────────────────────────────────────────
# In production this would be fetched from a GCS-hosted GeoJSON.
# 198 wards — we define a representative subset for the hackathon demo.
BENGALURU_WARDS: list[dict] = [
    {"ward_id": "ward_147", "ward_name": "Koramangala",     "lat": 12.9352, "lng": 77.6245},
    {"ward_id": "ward_068", "ward_name": "Jayanagar",       "lat": 12.9299, "lng": 77.5828},
    {"ward_id": "ward_150", "ward_name": "HSR Layout",      "lat": 12.9116, "lng": 77.6389},
    {"ward_id": "ward_034", "ward_name": "Rajajinagar",     "lat": 12.9902, "lng": 77.5540},
    {"ward_id": "ward_011", "ward_name": "Yelahanka",       "lat": 13.1007, "lng": 77.5963},
    {"ward_id": "ward_176", "ward_name": "BTM Layout",      "lat": 12.9166, "lng": 77.6101},
    {"ward_id": "ward_099", "ward_name": "Whitefield",      "lat": 12.9698, "lng": 77.7499},
    {"ward_id": "ward_023", "ward_name": "Hebbal",          "lat": 13.0355, "lng": 77.5970},
    {"ward_id": "ward_055", "ward_name": "Malleswaram",     "lat": 13.0035, "lng": 77.5651},
    {"ward_id": "ward_188", "ward_name": "Electronic City", "lat": 12.8399, "lng": 77.6770},
]


def _compute_risk_level(ndvi: float, lst: float) -> tuple[float, HeatRiskLevel]:
    """
    Derive a composite heat-risk score (0–100) from NDVI and LST.

    Logic:
      - High LST + low NDVI → critical heat island
      - Score = (LST_normalised * 0.6) + (NDVI_inverted_normalised * 0.4)
    """
    # Normalise LST: Bengaluru ranges roughly 20–45 °C
    lst_norm = max(0.0, min(1.0, (lst - 20) / 25))
    # Normalise NDVI: invert so high vegetation → low risk
    ndvi_norm = max(0.0, min(1.0, (1 - ndvi) / 2))

    score = round((lst_norm * 0.6 + ndvi_norm * 0.4) * 100, 2)

    if score >= 75:
        level = HeatRiskLevel.CRITICAL
    elif score >= 55:
        level = HeatRiskLevel.HIGH
    elif score >= 35:
        level = HeatRiskLevel.MODERATE
    else:
        level = HeatRiskLevel.LOW

    return score, level


class EarthEngineService:
    """
    Encapsulates all Google Earth Engine interactions.

    Usage:
        service = EarthEngineService()
        wards = await service.get_ward_heat_data()
    """

    def __init__(self) -> None:
        self._settings = get_settings()
        self._initialized = False

    def _init_gee(self) -> bool:
        """
        Initialise the GEE Python client with a service account.
        Returns True if successful, False if we should fall back to mock data.
        """
        if self._initialized:
            return True

        try:
            import ee  # earthengine-api

            credentials = ee.ServiceAccountCredentials(
                self._settings.gee_service_account,
                self._settings.gee_key_file_path,
            )
            ee.Initialize(credentials)
            self._initialized = True
            log.info("earth_engine.initialized")
            return True

        except Exception as exc:
            log.warning(
                "earth_engine.init_failed",
                error=str(exc),
                fallback="mock_data",
            )
            return False

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True,
    )
    def _fetch_ward_stats_gee(self, ward: dict) -> dict[str, float]:
        """
        Execute a GEE computation to get NDVI and LST for one ward centroid.

        In production, you would:
        1. Load a ward boundary FeatureCollection from Fusion Tables / GCS
        2. Clip Landsat image collection to the ward polygon
        3. Compute mean NDVI and mean LST over the polygon
        4. Export or .getInfo() the result

        This uses .getInfo() (synchronous) which is fine for < 1000 polygons.
        For city-scale batch jobs, use Export.table.toDrive() instead.
        """
        import ee

        # ── NDVI from Landsat 8 ──────────────────────────────
        # Filter to last 90 days, cloud mask, take median composite
        end_date = datetime.utcnow().strftime("%Y-%m-%d")
        start_date = (datetime.utcnow() - timedelta(days=90)).strftime("%Y-%m-%d")

        def mask_clouds(image):
            qa = image.select("QA_PIXEL")
            cloud_mask = qa.bitwiseAnd(1 << 3).eq(0)  # bit 3 = cloud shadow
            return image.updateMask(cloud_mask)

        def add_ndvi(image):
            return image.addBands(
                image.normalizedDifference(["SR_B5", "SR_B4"]).rename("NDVI")
            )

        point = ee.Geometry.Point([ward["lng"], ward["lat"]])
        region = point.buffer(1000)  # 1 km radius around ward centroid

        collection = (
            ee.ImageCollection("LANDSAT/LC08/C02/T1_L2")
            .filterBounds(region)
            .filterDate(start_date, end_date)
            .map(mask_clouds)
            .map(add_ndvi)
        )

        # Mean NDVI over the region
        ndvi_mean = (
            collection.select("NDVI")
            .mean()
            .reduceRegion(
                reducer=ee.Reducer.mean(),
                geometry=region,
                scale=30,
            )
            .getInfo()
        )

        # ── LST from MODIS ───────────────────────────────────
        lst_collection = (
            ee.ImageCollection("MODIS/061/MOD11A2")
            .filterBounds(region)
            .filterDate(start_date, end_date)
            .select("LST_Day_1km")
        )

        lst_mean = (
            lst_collection.mean()
            .reduceRegion(
                reducer=ee.Reducer.mean(),
                geometry=region,
                scale=1000,
            )
            .getInfo()
        )

        # MODIS LST is in Kelvin * 0.02 — convert to Celsius
        lst_kelvin = (lst_mean.get("LST_Day_1km") or 30125) * 0.02
        lst_celsius = lst_kelvin - 273.15

        ndvi = ndvi_mean.get("NDVI") or 0.2

        return {"ndvi": round(ndvi, 4), "lst_celsius": round(lst_celsius, 2)}

    def _mock_ward_stats(self, ward: dict) -> dict[str, float]:
        """
        Deterministic mock data for local dev / CI.
        Seeds random with ward_id for stable repeated results.
        """
        rng = random.Random(ward["ward_id"])
        # Commercial/dense wards run hotter
        hot_wards = {"ward_099", "ward_034", "ward_176", "ward_150"}
        base_lst = 36 if ward["ward_id"] in hot_wards else 29
        base_ndvi = 0.15 if ward["ward_id"] in hot_wards else 0.38

        return {
            "ndvi": round(base_ndvi + rng.uniform(-0.05, 0.1), 4),
            "lst_celsius": round(base_lst + rng.uniform(-2, 4), 2),
        }

    async def get_ward_heat_data(
        self, adopted_counts: dict[str, int] | None = None
    ) -> list[WardHeatData]:
        """
        Main public method — returns heat data for all configured wards.

        adopted_counts: optional dict of {ward_id: count} pre-fetched
        from Firestore so we don't do per-ward DB queries here.
        """
        use_gee = self._init_gee()
        results: list[WardHeatData] = []

        for ward in BENGALURU_WARDS:
            try:
                if use_gee:
                    stats = self._fetch_ward_stats_gee(ward)
                    log.debug("earth_engine.ward_fetched", ward=ward["ward_name"])
                else:
                    stats = self._mock_ward_stats(ward)

                ndvi = stats["ndvi"]
                lst = stats["lst_celsius"]
                green_cover = round(max(0, min(100, (ndvi + 0.2) * 100)), 1)
                score, level = _compute_risk_level(ndvi, lst)

                results.append(
                    WardHeatData(
                        ward_id=ward["ward_id"],
                        ward_name=ward["ward_name"],
                        avg_land_surface_temp=lst,
                        avg_ndvi=ndvi,
                        green_cover_percent=green_cover,
                        heat_risk_score=score,
                        heat_risk_level=level,
                        adopted_spots_count=(adopted_counts or {}).get(
                            ward["ward_id"], 0
                        ),
                    )
                )

            except Exception as exc:
                log.error(
                    "earth_engine.ward_error",
                    ward=ward["ward_name"],
                    error=str(exc),
                )
                # Skip this ward — partial response is better than a 500

        return results
