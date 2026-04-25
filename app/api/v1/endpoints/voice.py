# ============================================================
# app/api/v1/endpoints/voice.py
#
# Feature 4 — "Bhasha" Vernacular Voice Interface
#
# POST /api/v1/voice/prescribe
#     → Full voice pipeline: audio in → Kannada prescription out
#
# GET  /api/v1/voice/languages
#     → Supported languages and BCP-47 codes
#
# POST /api/v1/voice/translate
#     → Lightweight text-only translation (for UI testing)
#
# Audio input:
#   multipart/form-data with:
#     - audio     : binary audio file (WAV/OGG/MP3)
#     - language  : "kn" | "hi" | "ta" | "te" | "en" (default: "kn")
#     - encoding  : "LINEAR16" | "OGG_OPUS" | "MP3" (default: LINEAR16)
#     - sample_rate_hz : integer (default: 16000)
#     - latitude  : float (optional GPS from device)
#     - longitude : float (optional GPS from device)
#
# Auth: Required (Firebase Auth token).
# Max audio size: 60 seconds / 10MB — enforced by multipart limit.
#
# Scalability note:
#   Speech-to-Text and Translation API are both pay-per-use with
#   no concurrency limits — scales automatically with Cloud Run.
# ============================================================

from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    UploadFile,
    status,
)

from app.core.auth import get_current_user
from app.core.logging import get_logger
from app.models.schemas import (
    APIResponse,
    Coordinates,
    SupportedLanguage,
    VoicePrescriptionResponse,
)
from app.services.voice_service import VoiceService

router = APIRouter(prefix="/voice", tags=["Bhasha — Vernacular Voice Interface"])
log = get_logger(__name__)

# Module-level singleton
_voice_service = VoiceService()

# Supported audio encoding values
_VALID_ENCODINGS = {"LINEAR16", "OGG_OPUS", "MP3", "FLAC", "WEBM_OPUS"}

# Max audio file size: 10MB
_MAX_AUDIO_SIZE_BYTES = 10 * 1024 * 1024


# ── POST /voice/prescribe ──────────────────────────────────────────────────────

@router.post(
    "/prescribe",
    response_model=VoicePrescriptionResponse,
    status_code=status.HTTP_200_OK,
    summary="Voice-driven tree prescription in Kannada / Indian languages",
    description=(
        "Upload a voice recording asking about tree planting. The pipeline:\n\n"
        "1. **Speech-to-Text** — Google Cloud STT transcribes the audio "
        "(Kannada, Hindi, Tamil, Telugu, or English).\n"
        "2. **Translation** — Transcript translated to English as pivot language.\n"
        "3. **AI Prescription** — Gemini 1.5 Pro recommends the best native "
        "tree species for Bengaluru.\n"
        "4. **Back-Translation** — Prescription translated back to the user's language.\n"
        "5. **[Optional] TTS** — Audio response synthesised if enabled.\n\n"
        "**Example Kannada query:** *'ನಾನು ಕೋರಮಂಗಲದಲ್ಲಿ ಒಂದು ಮರ ನೆಡಲು ಬಯಸುತ್ತೇನೆ'*\n"
        "('I want to plant a tree in Koramangala')\n\n"
        "Audio: multipart/form-data, max 10MB (WAV/OGG/MP3)."
    ),
)
async def voice_prescribe(
    # ── Audio file ──────────────────────────────────────────────────────────
    audio: Annotated[
        UploadFile,
        File(description="Audio recording (LINEAR16 WAV preferred, or OGG/MP3)"),
    ],
    # ── Language settings ───────────────────────────────────────────────────
    language: Annotated[
        str,
        Form(description="Language code: kn (Kannada), hi, ta, te, en"),
    ] = "kn",
    encoding: Annotated[
        str,
        Form(description="Audio encoding: LINEAR16 | OGG_OPUS | MP3 | WEBM_OPUS"),
    ] = "LINEAR16",
    sample_rate_hz: Annotated[
        int,
        Form(description="Sample rate in Hz (e.g. 16000, 44100, 48000)"),
    ] = 16000,
    # ── Optional GPS from device ────────────────────────────────────────────
    latitude: Annotated[
        float | None,
        Form(description="GPS latitude from device sensor"),
    ] = None,
    longitude: Annotated[
        float | None,
        Form(description="GPS longitude from device sensor"),
    ] = None,
    current_user: dict = Depends(get_current_user),
) -> VoicePrescriptionResponse:
    """
    Full Bhasha voice prescription pipeline.

    The Flutter app should:
    1. Record audio with AudioRecorder (16kHz mono LINEAR16 WAV)
    2. Send with encoding=LINEAR16 and sample_rate_hz=16000
    3. Include latitude/longitude from GPS sensor for best recommendations
    4. Display `full_prescription_vernacular` as text
    5. If `audio_response_base64` is non-null, play it via AudioPlayer
    """
    uid = current_user.get("uid", "unknown")

    # ── Validate language ──────────────────────────────────────────────────
    language_map = {
        "kn": SupportedLanguage.KANNADA,
        "hi": SupportedLanguage.HINDI,
        "ta": SupportedLanguage.TAMIL,
        "te": SupportedLanguage.TELUGU,
        "en": SupportedLanguage.ENGLISH,
    }
    source_lang = language_map.get(language.lower())
    if source_lang is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Unsupported language code '{language}'. "
                f"Supported: {list(language_map.keys())}"
            ),
        )

    # ── Validate encoding ──────────────────────────────────────────────────
    if encoding.upper() not in _VALID_ENCODINGS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Unsupported audio encoding '{encoding}'. "
                f"Supported: {sorted(_VALID_ENCODINGS)}"
            ),
        )

    # ── Read and validate audio ────────────────────────────────────────────
    audio_bytes = await audio.read()

    if len(audio_bytes) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Audio file is empty.",
        )

    if len(audio_bytes) > _MAX_AUDIO_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Audio file exceeds 10MB limit. Please record a shorter clip (max 60s).",
        )

    # ── Build optional coordinates from GPS params ─────────────────────────
    coords: Coordinates | None = None
    if latitude is not None and longitude is not None:
        try:
            coords = Coordinates(latitude=latitude, longitude=longitude)
        except Exception:
            log.warning(
                "voice.invalid_coords",
                uid=uid,
                lat=latitude,
                lng=longitude,
            )
            # Non-fatal — falls back to Bengaluru centre

    log.info(
        "voice.prescribe_request",
        uid=uid,
        language=source_lang.value,
        encoding=encoding,
        sample_rate=sample_rate_hz,
        audio_size_bytes=len(audio_bytes),
        has_gps=coords is not None,
    )

    # ── Run the full pipeline ──────────────────────────────────────────────
    try:
        result = await _voice_service.process_voice_prescription(
            audio_bytes=audio_bytes,
            source_language=source_lang,
            audio_encoding=encoding.upper(),
            sample_rate_hz=sample_rate_hz,
            coordinates=coords,
        )

    except ValueError as exc:
        # STT returned no results (silent audio, background noise, etc.)
        log.warning("voice.stt_no_results", uid=uid, error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        )
    except Exception as exc:
        log.error("voice.pipeline_error", uid=uid, error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Voice processing pipeline temporarily unavailable. "
                "Please try again or use the text-based /prescribe endpoint."
            ),
        )

    log.info(
        "voice.prescribe_complete",
        uid=uid,
        primary=result.prescription.primary_recommendation.common_name,
        confidence=result.transcription.confidence,
        has_audio_response=result.audio_response_base64 is not None,
    )
    return result


# ── GET /voice/languages ───────────────────────────────────────────────────────

@router.get(
    "/languages",
    summary="List supported languages for voice interface",
    description="Returns supported language codes, names, and BCP-47 codes.",
)
async def list_supported_languages() -> dict:
    """Public endpoint — no auth required."""
    return {
        "supported_languages": [
            {
                "code": "kn",
                "name": "Kannada",
                "native_name": "ಕನ್ನಡ",
                "bcp47": "kn-IN",
                "is_primary": True,
                "tts_available": True,
            },
            {
                "code": "hi",
                "name": "Hindi",
                "native_name": "हिन्दी",
                "bcp47": "hi-IN",
                "is_primary": False,
                "tts_available": True,
            },
            {
                "code": "ta",
                "name": "Tamil",
                "native_name": "தமிழ்",
                "bcp47": "ta-IN",
                "is_primary": False,
                "tts_available": True,
            },
            {
                "code": "te",
                "name": "Telugu",
                "native_name": "తెలుగు",
                "bcp47": "te-IN",
                "is_primary": False,
                "tts_available": True,
            },
            {
                "code": "en",
                "name": "English",
                "native_name": "English",
                "bcp47": "en-IN",
                "is_primary": False,
                "tts_available": True,
            },
        ],
        "recommended_audio_format": {
            "encoding": "LINEAR16",
            "sample_rate_hz": 16000,
            "channels": 1,
            "note": (
                "Mono 16kHz LINEAR16 WAV gives best accuracy. "
                "OGG_OPUS (from browser MediaRecorder) also works well."
            ),
        },
    }


# ── POST /voice/translate ──────────────────────────────────────────────────────

@router.post(
    "/translate",
    summary="Translate text between Kannada and English (for UI testing)",
    description=(
        "Lightweight text translation endpoint. "
        "Primarily used for testing the translation layer without audio. "
        "Requires auth."
    ),
)
async def translate_text(
    text: Annotated[str, Form(description="Text to translate")],
    source_language: Annotated[
        str,
        Form(description="Source language code: kn | hi | ta | te | en"),
    ] = "kn",
    target_language: Annotated[
        str,
        Form(description="Target language code: kn | hi | ta | te | en"),
    ] = "en",
    current_user: dict = Depends(get_current_user),
) -> APIResponse:
    """
    Direct text translation for UI development and testing.
    Uses Cloud Translation API v2 under the hood.
    """
    from google.cloud import translate_v2 as translate

    lang_map = {"kn": "kn", "hi": "hi", "ta": "ta", "te": "te", "en": "en"}

    src = lang_map.get(source_language.lower())
    tgt = lang_map.get(target_language.lower())

    if not src or not tgt:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unsupported language. Supported: {list(lang_map.keys())}",
        )

    if src == tgt:
        return APIResponse(message="No translation needed.", data={"translated_text": text})

    try:
        client = translate.Client()
        result = client.translate(text, source_language=src, target_language=tgt)
        translated = result["translatedText"]
    except Exception as exc:
        log.error("voice.translate_error", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Translation service temporarily unavailable.",
        )

    return APIResponse(
        message="Translation successful.",
        data={
            "original_text": text,
            "translated_text": translated,
            "source_language": source_language,
            "target_language": target_language,
        },
    )
