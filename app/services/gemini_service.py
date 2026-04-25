# ============================================================
# app/services/gemini_service.py
#
# "Precision Prescription" engine & Sapling Verification — powered by Gemini 1.5 Pro.
#
# Given a location and optional context, Gemini recommends the
# most ecologically appropriate native tree species for planting
# in Bengaluru's specific microclimate.
#
# We also use Gemini 1.5 Pro's multimodal capabilities for zero-shot
# sapling image verification, acting as a strict fraud-prevention system.
# ============================================================

import asyncio
import json
import re
import uuid
from io import BytesIO

import google.generativeai as genai
from google.cloud import storage
from google.oauth2 import service_account
from tenacity import retry, stop_after_attempt, wait_exponential

from app.core.config import get_settings
from app.core.logging import get_logger
from app.models.schemas import PrescriptionRequest, TreeSpecies, VerificationStatus

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
    "expected_canopy_spread_m": 5.5,
    "water_requirement": "Low | Medium | High",
    "growth_rate": "Fast | Moderate | Slow",
    "co2_absorption_kg_per_year": 20.0,
    "rotary_focus": "Environment"
  },
  "alternatives": [
    {
      "common_name": "...",
      "scientific_name": "...",
      "kannada_name": "...",
      "why_recommended": "1-2 sentence explanation",
      "expected_canopy_spread_m": 4.0,
      "water_requirement": "Low | Medium | High",
      "growth_rate": "Fast | Moderate | Slow",
      "co2_absorption_kg_per_year": 15.0,
      "rotary_focus": "Environment"
    }
  ]
}
"""

_VISION_PROMPT = """
You are an expert botanist and a strict fraud-prevention system for an environmental "Green Ledger".
Your job is to analyze this photo uploaded by a citizen claiming to have planted a tree sapling.
Determine if the image clearly shows a newly planted tree sapling or plant in urban soil.

You MUST REJECT the image if it is:
- A mature, fully grown tree
- An indoor houseplant or potted ornamental plant (unless it's a valid sapling temporarily in a pot)
- A picture of a screen, drawing, or obviously fake
- Completely unrelated to plants (e.g. selfies, buildings)

Return a JSON object with this exact structure:
{
    "status": "approved",
    "confidence_score": 0.95,
    "detected_labels": ["soil", "leaves", "sapling", "greenery"],
    "reasoning": "Brief explanation of why it was approved or rejected"
}
Note: 'status' MUST be exactly either "approved" or "rejected".
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
    clean = re.sub(r"```(?:json)?|```", "", raw_text).strip()

    try:
        data = json.loads(clean)
    except json.JSONDecodeError as exc:
        log.error("gemini.json_parse_error", raw=raw_text[:200], error=str(exc))
        raise ValueError(f"Gemini returned non-JSON: {exc}") from exc

    primary = TreeSpecies(**data["primary"])
    alternatives = [TreeSpecies(**s) for s in data.get("alternatives", [])]

    return primary, alternatives

def _parse_vision_response(raw_text: str) -> dict:
    """Parse Gemini Vision JSON response."""
    clean = re.sub(r"```(?:json)?|```", "", raw_text).strip()
    try:
        return json.loads(clean)
    except json.JSONDecodeError as exc:
        log.error("gemini.vision.json_parse_error", raw=raw_text[:200], error=str(exc))
        raise ValueError(f"Gemini returned non-JSON: {exc}") from exc


class GeminiService:
    """
    Wraps the Gemini 1.5 Pro API for tree species prescription
    and sapling image verification.
    """

    def __init__(self) -> None:
        self._settings = get_settings()
        self._lock = asyncio.Lock()

        _safety_settings = [
            {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
        ]

        # Configure the text model for prescriptions
        self._model = genai.GenerativeModel(
            model_name=self._settings.gemini_model,
            system_instruction=_SYSTEM_CONTEXT,
            generation_config=genai.GenerationConfig(
                temperature=0.3,
                top_p=0.85,
                response_mime_type="application/json",
            ),
            safety_settings=_safety_settings,
        )
        
        # Configure the vision model for sapling verification
        self._vision_model = genai.GenerativeModel(
            model_name=self._settings.gemini_model,
            generation_config=genai.GenerationConfig(
                temperature=0.1,  # Strict, deterministic responses for fraud detection
                response_mime_type="application/json",
            ),
            safety_settings=_safety_settings,
        )

        credentials = service_account.Credentials.from_service_account_file(
            self._settings.firebase_service_account_path
        )
        self._gcs_client = storage.Client(
            project=self._settings.gcp_project_id,
            credentials=credentials
        )

        log.info("gemini.service_ready", model=self._settings.gemini_model)

    # ── GCS Upload ─────────────────────────────────────────────────────────────

    async def upload_image_to_gcs(
        self, image_bytes: bytes, spot_id: str, content_type: str = "image/jpeg"
    ) -> str:
        """
        Upload the verification photo to GCS.
        Returns the gs:// URI.
        """
        import asyncio

        bucket = self._gcs_client.bucket(self._settings.gcs_bucket_name)
        blob_name = f"verifications/{spot_id}/{uuid.uuid4().hex}.jpg"
        blob = bucket.blob(blob_name)

        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None,
            lambda: blob.upload_from_file(
                BytesIO(image_bytes), content_type=content_type
            ),
        )

        gcs_uri = f"gs://{self._settings.gcs_bucket_name}/{blob_name}"
        log.info("gcs.upload_complete", uri=gcs_uri, size_bytes=len(image_bytes))
        return gcs_uri

    # ── Text Prescriptions ─────────────────────────────────────────────────────

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
        """
        prompt = _build_user_prompt(request)

        log.info(
            "gemini.prescribing",
            lat=request.coordinates.latitude,
            lng=request.coordinates.longitude,
            ward=request.ward_name,
        )

        import asyncio
        loop = asyncio.get_event_loop()
        async with self._lock:
            genai.configure(api_key=self._settings.gemini_api_key_prescribe)
            response = await loop.run_in_executor(
                None, self._model.generate_content, prompt
            )

        primary, alternatives = _parse_gemini_response(response.text)

        log.info(
            "gemini.prescription_complete",
            primary=primary.common_name,
            alternatives=[s.common_name for s in alternatives],
        )

        return primary, alternatives

    # ── Multimodal Verification ────────────────────────────────────────────────

    async def verify_sapling_image(
        self, image_bytes: bytes, spot_id: str, content_type: str = "image/jpeg"
    ) -> dict:
        """
        Full verification pipeline using Gemini 1.5 Pro Vision:
          1. Upload image to GCS
          2. Ask Gemini to verify sapling
          3. Return structured result
        """
        import asyncio
        loop = asyncio.get_event_loop()

        # 1. Upload to GCS
        gcs_uri = await self.upload_image_to_gcs(image_bytes, spot_id, content_type)
        
        # 2. Call Gemini Vision
        image_part = {
            "mime_type": content_type,
            "data": image_bytes
        }
        
        log.info("gemini.vision.verifying", spot_id=spot_id)
        
        try:
            async with self._lock:
                genai.configure(api_key=self._settings.gemini_api_key_verify)
                response = await loop.run_in_executor(
                    None, 
                    lambda: self._vision_model.generate_content([_VISION_PROMPT, image_part])
                )
            
            result = _parse_vision_response(response.text)
            
            status_str = result.get("status", "").lower()
            status_enum = VerificationStatus.APPROVED if status_str == "approved" else VerificationStatus.REJECTED
            
            confidence = float(result.get("confidence_score", 0.0))
            labels = result.get("detected_labels", [])
            message = result.get("reasoning", "Processed by Gemini Vision.")
            
        except Exception as e:
            log.error("gemini.vision.error", error=str(e), spot_id=spot_id)
            # Fallback to rejected on error to be safe
            status_enum = VerificationStatus.REJECTED
            confidence = 0.0
            labels = []
            message = f"AI Analysis failed: {str(e)}"
            
        log.info(
            "gemini.vision.complete",
            spot_id=spot_id,
            status=status_enum.value,
            confidence=confidence,
        )
        
        return {
            "status": status_enum,
            "confidence_score": confidence,
            "detected_labels": labels,
            "gcs_uri": gcs_uri,
            "message": message,
        }
