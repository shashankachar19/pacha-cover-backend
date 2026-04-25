# ============================================================
# app/services/gemini_service.py
#
# "Precision Prescription" engine — powered by Gemini 1.5 Pro.
#
# Given a location and optional context, Gemini recommends the
# most ecologically appropriate native tree species for planting
# in Bengaluru's specific microclimate.
#
# Prompt engineering notes:
#   • System prompt grounds the model in Bengaluru's ecology,
#     BBMP guidelines, and Rotary's Environment focus area.
#   • We request structured JSON output so the response can be
#     parsed directly into Pydantic models without fragile regex.
#   • tenacity retries on transient API errors (rate limits, 503).
# ============================================================

import json
import re

import google.generativeai as genai
from tenacity import retry, stop_after_attempt, wait_exponential

from app.core.config import get_settings
from app.core.logging import get_logger
from app.models.schemas import PrescriptionRequest, TreeSpecies

log = get_logger(__name__)

# ── Bengaluru-specific context injected into every Gemini prompt ───────────────
_SYSTEM_CONTEXT = """
You are an expert urban forestry advisor for Bengaluru (Bangalore), India.
Your role is to recommend the most suitable native and naturalised tree species
for planting in Bengaluru's specific conditions.

Key facts you must use:
- Bengaluru's altitude: 920m above sea level (cooler than coastal Karnataka)
- Climate: Tropical savanna (Köppen Aw), monsoons June–Sept & Oct–Nov
- Soil: Predominantly red laterite with some black cotton soil
- BBMP (municipal authority) prefers: Neem, Honge (Pongamia), Rain Tree,
  Gulmohar, Indian Laburnum (Cassia fistula), Arjuna, Peepal, Banyan,
  Jamun (Malabar plum), Copper Pod
- Avoid invasive species: Eucalyptus (water-hungry), Acacia (invasive),
  Casuarina (reduces biodiversity)

Your recommendations MUST align with Rotary International's
"Environment" Area of Focus: restoring natural ecosystems, reducing
pollution, and supporting community stewardship of the environment.

IMPORTANT: Respond ONLY with valid JSON. No markdown, no preamble.
"""

_SPECIES_SCHEMA = """
Return this exact JSON structure (fill all fields):
{
  "primary": {
    "common_name": "...",
    "scientific_name": "...",
    "kannada_name": "...",
    "why_recommended": "2-3 sentence plain-English explanation referencing the specific location context provided",
    "expected_canopy_spread_m": <number>,
    "water_requirement": "Low | Medium | High",
    "growth_rate": "Fast | Moderate | Slow",
    "co2_absorption_kg_per_year": <number>,
    "rotary_focus": "Environment"
  },
  "alternatives": [
    {
      "common_name": "...",
      "scientific_name": "...",
      "kannada_name": "...",
      "why_recommended": "1-2 sentence explanation",
      "expected_canopy_spread_m": <number>,
      "water_requirement": "Low | Medium | High",
      "growth_rate": "Fast | Moderate | Slow",
      "co2_absorption_kg_per_year": <number>,
      "rotary_focus": "Environment"
    }
  ]
}
"""


def _build_user_prompt(req: PrescriptionRequest) -> str:
    """Construct the user-facing part of the Gemini prompt."""
    parts = [
        f"Location: {req.coordinates.latitude:.4f}°N, "
        f"{req.coordinates.longitude:.4f}°E",
    ]

    if req.ward_name:
        parts.append(f"BBMP Ward: {req.ward_name}")
    if req.nearby_land_use:
        parts.append(f"Nearby land use: {req.nearby_land_use}")
    if req.soil_type:
        parts.append(f"Soil type: {req.soil_type}")
    if req.plot_area_sqm:
        parts.append(f"Available planting area: {req.plot_area_sqm} m²")

    context = "\n".join(parts)

    return (
        f"Given the following location context:\n{context}\n\n"
        "Recommend the SINGLE BEST native tree species and TWO alternatives "
        "for planting here to maximise urban cooling and biodiversity.\n\n"
        f"{_SPECIES_SCHEMA}"
    )


def _parse_gemini_response(raw_text: str) -> tuple[TreeSpecies, list[TreeSpecies]]:
    """
    Parse Gemini's JSON response into Pydantic models.
    Handles minor formatting issues (e.g. trailing commas).
    """
    # Strip any markdown code fences Gemini occasionally adds
    clean = re.sub(r"```(?:json)?|```", "", raw_text).strip()

    try:
        data = json.loads(clean)
    except json.JSONDecodeError as exc:
        log.error("gemini.json_parse_error", raw=raw_text[:200], error=str(exc))
        raise ValueError(f"Gemini returned non-JSON: {exc}") from exc

    primary = TreeSpecies(**data["primary"])
    alternatives = [TreeSpecies(**s) for s in data.get("alternatives", [])]

    return primary, alternatives


class GeminiService:
    """
    Wraps the Gemini 1.5 Pro API for tree species prescription.

    The model is configured once and reused across requests
    (thread-safe in the google-generativeai library).
    """

    def __init__(self) -> None:
        self._settings = get_settings()
        genai.configure(api_key=self._settings.gemini_api_key)

        # Configure the model — temperature low for factual/scientific output
        self._model = genai.GenerativeModel(
            model_name=self._settings.gemini_model,
            system_instruction=_SYSTEM_CONTEXT,
            generation_config=genai.GenerationConfig(
                temperature=0.3,        # Consistent, factual responses
                top_p=0.85,
                max_output_tokens=1024,
                response_mime_type="application/json",  # Force JSON mode
            ),
        )
        log.info("gemini.service_ready", model=self._settings.gemini_model)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=8),
        reraise=True,
    )
    async def prescribe_species(
        self, request: PrescriptionRequest
    ) -> tuple[TreeSpecies, list[TreeSpecies]]:
        """
        Call Gemini 1.5 Pro and return primary + alternative tree species.

        Returns:
            (primary_species, list_of_alternatives)

        Raises:
            ValueError: if Gemini's response cannot be parsed
            Exception: on API errors after retries
        """
        prompt = _build_user_prompt(request)

        log.info(
            "gemini.prescribing",
            lat=request.coordinates.latitude,
            lng=request.coordinates.longitude,
            ward=request.ward_name,
        )

        # generate_content is sync in v0.5 — run in threadpool for FastAPI
        import asyncio
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None, self._model.generate_content, prompt
        )

        log.debug(
            "gemini.response_received",
            tokens_used=response.usage_metadata.total_token_count
            if response.usage_metadata
            else "unknown",
        )

        primary, alternatives = _parse_gemini_response(response.text)

        log.info(
            "gemini.prescription_complete",
            primary=primary.common_name,
            alternatives=[s.common_name for s in alternatives],
        )

        return primary, alternatives
