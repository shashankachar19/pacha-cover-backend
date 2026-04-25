# ============================================================
# app/core/config.py
#
# Unified application settings — merged from original Pacha Cover
# and extended features (AR, Corridors, Carbon/Tax, Voice).
#
# Uses pydantic-settings to load from environment variables
# and/or a .env file. All values have sensible defaults for
# local development.
# ============================================================

from __future__ import annotations

from functools import lru_cache
from typing import List

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Application configuration loaded from environment variables.
    Copy .env.example → .env and fill in real values.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Application ────────────────────────────────────────────────────────
    app_env: str = "development"
    app_version: str = "1.1.0"
    secret_key: str = "change-me-to-a-long-random-string"

    # ── CORS ───────────────────────────────────────────────────────────────
    allowed_origins: str = "http://localhost:3000,https://pacha-cover.web.app"

    @property
    def cors_origins(self) -> List[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]

    # ── Google Cloud ───────────────────────────────────────────────────────
    gcp_project_id: str = "your-gcp-project-id"
    gcp_region: str = "asia-south1"

    # ── Firebase / Firestore ───────────────────────────────────────────────
    firebase_service_account_path: str = "./serviceAccountKey.json"
    firestore_database_id: str = "(default)"

    # ── Gemini API ─────────────────────────────────────────────────────────
    gemini_api_key_prescribe: str = "your-gemini-api-key-prescribe"
    gemini_api_key_verify: str = "your-gemini-api-key-verify"
    gemini_model: str = "gemini-2.5-flash"



    # ── Google Earth Engine ────────────────────────────────────────────────
    gee_service_account: str = ""
    gee_key_file_path: str = "./gee_key.json"

    # ── Google Cloud Storage ───────────────────────────────────────────────
    gcs_bucket_name: str = "pacha-cover-images"

    # ── Green Points ───────────────────────────────────────────────────────
    points_per_verification: int = 50
    points_per_adoption: int = 10

    # ══════════════════════════════════════════════════════════════════════
    # FEATURE 1 — Pacha Vision AR
    # ══════════════════════════════════════════════════════════════════════
    ar_assets_base_url: str = "https://storage.googleapis.com/pacha-cover-ar-assets"
    ar_assets_bucket: str = "pacha-cover-ar-assets"

    # ══════════════════════════════════════════════════════════════════════
    # FEATURE 2 — Green Corridor Clustering
    # ══════════════════════════════════════════════════════════════════════
    corridor_min_trees: int = 5
    corridor_radius_m: float = 100.0
    points_corridor_badge: int = 200

    # ══════════════════════════════════════════════════════════════════════
    # FEATURE 3 — Carbon Credit & Tax Simulator
    # ══════════════════════════════════════════════════════════════════════
    carbon_credit_rate_inr_per_tonne: float = 1000.0
    tax_rebate_co2_per_percent: float = 20.0
    tax_rebate_max_percent: float = 20.0

    # ══════════════════════════════════════════════════════════════════════
    # FEATURE 4 — Bhasha Vernacular Voice Interface
    # ══════════════════════════════════════════════════════════════════════
    speech_default_language_code: str = "kn-IN"
    translation_pivot_language: str = "en"
    voice_enable_tts_response: bool = False
    voice_audio_bucket: str = "pacha-cover-voice-audio"


@lru_cache()
def get_settings() -> Settings:
    """Cached singleton — re-use across the entire application."""
    return Settings()
