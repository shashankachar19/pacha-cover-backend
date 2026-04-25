# ============================================================
# app/services/voice_service.py
#
# Feature 4 — "Bhasha" Vernacular AI Voice Interface
#
# Full pipeline for voice-driven tree prescription in Kannada
# (and other Indian languages) — making the app accessible to
# citizens who prefer speaking over typing.
#
# Pipeline:
#   AUDIO IN (Kannada/Hindi/Tamil/Telugu)
#       ↓ Google Cloud Speech-to-Text
#   TRANSCRIPT (source language)
#       ↓ Google Cloud Translation API (→ English)
#   ENGLISH TEXT
#       ↓ Parse coordinates / context from text
#       ↓ Existing GeminiService.prescribe_species()
#   PRESCRIPTION (English)
#       ↓ Google Cloud Translation API (→ source language)
#   PRESCRIPTION (Kannada / source language)
#       ↓ [Optional] Google Cloud Text-to-Speech
#   AUDIO OUT (MP3, base64-encoded)
#
# Google Cloud APIs used:
#   • google-cloud-speech     — Speech-to-Text v1p1beta1
#   • google-cloud-translate  — Translation API v2 (Basic) or v3 (Advanced)
#   • google-cloud-texttospeech — Text-to-Speech (optional response audio)
#
# Language support:
#   • kn-IN  Kannada (India)  — PRIMARY
#   • hi-IN  Hindi (India)
#   • ta-IN  Tamil (India)
#   • te-IN  Telugu (India)
#   • en-IN  English (India)  — passthrough, no translation needed
#
# Speech-to-Text model:
#   Using "latest_long" model which handles:
#   - Bengaluru accent variations
#   - Code-switching (Kannada + English words)
#   - Background noise from outdoor environments
#
# Audio input formats accepted:
#   • LINEAR16 (WAV, 16kHz mono)  — Flutter AudioRecorder default
#   • OGG_OPUS (WebM/Opus)        — Browser MediaRecorder default
#   • MP3                          — Fallback
# ============================================================

import base64
import re
from dataclasses import dataclass

from google.cloud import speech, texttospeech, translate_v2 as translate
from tenacity import retry, stop_after_attempt, wait_exponential

from app.core.config import get_settings
from app.core.logging import get_logger
from app.models.schemas import (
    Coordinates,
    PrescriptionRequest,
    PrescriptionResponse,
    SupportedLanguage,
    TranscriptionResult,
    VoicePrescriptionResponse,
)
from app.services.gemini_service import GeminiService

log = get_logger(__name__)

# ── BCP-47 language code map ───────────────────────────────────────────────────
_LANG_TO_BCP47: dict[SupportedLanguage, str] = {
    SupportedLanguage.KANNADA: "kn-IN",
    SupportedLanguage.HINDI:   "hi-IN",
    SupportedLanguage.TAMIL:   "ta-IN",
    SupportedLanguage.TELUGU:  "te-IN",
    SupportedLanguage.ENGLISH: "en-IN",
}

# Text-to-Speech voice configs per language
_TTS_VOICES: dict[SupportedLanguage, dict] = {
    SupportedLanguage.KANNADA: {
        "language_code": "kn-IN",
        "name": "kn-IN-Standard-A",
        "ssml_gender": texttospeech.SsmlVoiceGender.FEMALE,
    },
    SupportedLanguage.HINDI: {
        "language_code": "hi-IN",
        "name": "hi-IN-Standard-D",
        "ssml_gender": texttospeech.SsmlVoiceGender.FEMALE,
    },
    SupportedLanguage.TAMIL: {
        "language_code": "ta-IN",
        "name": "ta-IN-Standard-A",
        "ssml_gender": texttospeech.SsmlVoiceGender.FEMALE,
    },
    SupportedLanguage.TELUGU: {
        "language_code": "te-IN",
        "name": "te-IN-Standard-A",
        "ssml_gender": texttospeech.SsmlVoiceGender.FEMALE,
    },
    SupportedLanguage.ENGLISH: {
        "language_code": "en-IN",
        "name": "en-IN-Standard-D",
        "ssml_gender": texttospeech.SsmlVoiceGender.FEMALE,
    },
}

# ── Coordinate extraction from transcripts ─────────────────────────────────────

# Default Bengaluru centre — used when user doesn't specify coordinates
_BENGALURU_CENTRE = Coordinates(latitude=12.9716, longitude=77.5946)

_WARD_HINTS: dict[str, str] = {
    "koramangala": "Koramangala",
    "jayanagar": "Jayanagar",
    "hsr": "HSR Layout",
    "whitefield": "Whitefield",
    "hebbal": "Hebbal",
    "malleswaram": "Malleswaram",
    "yelahanka": "Yelahanka",
    "rajajinagar": "Rajajinagar",
    "btm": "BTM Layout",
    "electronic city": "Electronic City",
}

_LAND_USE_HINTS: list[str] = [
    "roadside", "road", "park", "residential", "commercial",
    "footpath", "pavement", "compound", "garden",
]

_SOIL_HINTS: dict[str, str] = {
    "red": "red laterite",
    "laterite": "red laterite",
    "clay": "clay",
    "black": "black cotton soil",
    "sandy": "sandy",
}


def _extract_prescription_context(english_text: str) -> PrescriptionRequest:
    """
    Parse the English-translated transcript into a PrescriptionRequest.

    This is intentionally lightweight — the Gemini prescriber handles
    ambiguity well, so we just extract what we can and let Gemini fill gaps.

    In production, replace this with a Gemini-powered NLU extraction
    (send the transcript to Gemini and ask it to extract structured JSON).
    """
    text_lower = english_text.lower()

    # Ward detection
    ward_name: str | None = None
    for keyword, canonical in _WARD_HINTS.items():
        if keyword in text_lower:
            ward_name = canonical
            break

    # Land use detection
    nearby_land_use: str | None = None
    for use in _LAND_USE_HINTS:
        if use in text_lower:
            nearby_land_use = use
            break

    # Soil type detection
    soil_type: str | None = None
    for keyword, canonical_soil in _SOIL_HINTS.items():
        if keyword in text_lower:
            soil_type = canonical_soil
            break

    # Plot area — look for patterns like "25 square meters" or "50 sqm"
    plot_area: float | None = None
    area_match = re.search(r"(\d+(?:\.\d+)?)\s*(?:sq(?:uare)?\s*m(?:eter)?s?|sqm)", text_lower)
    if area_match:
        try:
            plot_area = float(area_match.group(1))
        except ValueError:
            pass

    return PrescriptionRequest(
        coordinates=_BENGALURU_CENTRE,  # GPS comes from device, not voice
        ward_name=ward_name,
        nearby_land_use=nearby_land_use,
        soil_type=soil_type,
        plot_area_sqm=plot_area,
    )


def _build_vernacular_summary(
    primary_species_name: str,
    why_recommended: str,
    water_req: str,
    growth_rate: str,
    co2: float | None,
) -> str:
    """
    Builds a concise English summary that will be translated to the
    source language for TTS readback.
    """
    co2_str = f", and sequesters approximately {co2:.0f} kg of CO2 per year" if co2 else ""
    return (
        f"I recommend planting a {primary_species_name}. "
        f"{why_recommended} "
        f"This tree has a {water_req.lower()} water requirement "
        f"and grows at a {growth_rate.lower()} rate{co2_str}. "
        f"This species is among the best choices for urban greening in Bengaluru."
    )


# ── Service class ──────────────────────────────────────────────────────────────

class VoiceService:
    """
    Bhasha Voice Interface — full speech-in / speech-out pipeline.

    Instantiated once per process. All Google Cloud clients are
    created lazily to avoid import-time credential errors in test envs.
    """

    def __init__(self) -> None:
        self._settings = get_settings()
        self._gemini_service = GeminiService()
        self._speech_client: speech.SpeechClient | None = None
        self._translate_client: translate.Client | None = None
        self._tts_client: texttospeech.TextToSpeechClient | None = None

    def _get_speech_client(self) -> speech.SpeechClient:
        if self._speech_client is None:
            self._speech_client = speech.SpeechClient()
        return self._speech_client

    def _get_translate_client(self) -> translate.Client:
        if self._translate_client is None:
            self._translate_client = translate.Client()
        return self._translate_client

    def _get_tts_client(self) -> texttospeech.TextToSpeechClient:
        if self._tts_client is None:
            self._tts_client = texttospeech.TextToSpeechClient()
        return self._tts_client

    # ── Step 1: Speech-to-Text ─────────────────────────────────────────────────

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=6))
    async def transcribe_audio(
        self,
        audio_bytes: bytes,
        source_language: SupportedLanguage,
        audio_encoding: str = "LINEAR16",
        sample_rate_hz: int = 16000,
    ) -> TranscriptionResult:
        """
        Transcribe audio bytes using Google Cloud Speech-to-Text.

        Supports Kannada, Hindi, Tamil, Telugu, and English.
        Uses the "latest_long" model for best accuracy with Indian accents
        and outdoor background noise.

        audio_encoding options: LINEAR16, OGG_OPUS, MP3, FLAC
        """
        import asyncio

        bcp47 = _LANG_TO_BCP47[source_language]

        # Map encoding string to Speech API enum
        encoding_map = {
            "LINEAR16": speech.RecognitionConfig.AudioEncoding.LINEAR16,
            "OGG_OPUS": speech.RecognitionConfig.AudioEncoding.OGG_OPUS,
            "MP3":      speech.RecognitionConfig.AudioEncoding.MP3,
            "FLAC":     speech.RecognitionConfig.AudioEncoding.FLAC,
            "WEBM_OPUS": speech.RecognitionConfig.AudioEncoding.WEBM_OPUS,
        }
        encoding_enum = encoding_map.get(
            audio_encoding.upper(),
            speech.RecognitionConfig.AudioEncoding.LINEAR16,
        )

        config = speech.RecognitionConfig(
            encoding=encoding_enum,
            sample_rate_hertz=sample_rate_hz,
            language_code=bcp47,
            # Alternative languages handle code-switching
            # e.g. Kannada speaker using English tree names
            alternative_language_codes=["en-IN"],
            model="latest_long",
            enable_automatic_punctuation=True,
            # Boost tree-related vocabulary for better recognition
            speech_contexts=[
                speech.SpeechContext(
                    phrases=[
                        "Neem", "Honge", "Peepal", "Banyan", "Gulmohar",
                        "Rain Tree", "Jamun", "Arjuna", "Copper Pod",
                        "BBMP", "ward", "Koramangala", "Jayanagar",
                        "HSR Layout", "Whitefield", "Bengaluru",
                        "ಬೇವು", "ಹೊಂಗೆ", "ಅಶ್ವತ್ಥ", "ಆಲದ ಮರ",  # Kannada names
                    ],
                    boost=15.0,
                )
            ],
        )

        audio = speech.RecognitionAudio(content=audio_bytes)
        client = self._get_speech_client()

        log.info(
            "voice.transcribing",
            language=source_language.value,
            encoding=audio_encoding,
            audio_size_bytes=len(audio_bytes),
        )

        # Speech client is sync — run in thread pool
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None, lambda: client.recognize(config=config, audio=audio)
        )

        if not response.results:
            raise ValueError(
                "Speech-to-Text returned no results. "
                "Please speak clearly and ensure the audio contains speech."
            )

        # Take the highest-confidence alternative from the first result
        best = response.results[0].alternatives[0]
        transcript_original = best.transcript
        confidence = round(best.confidence, 4)

        log.info(
            "voice.transcribed",
            transcript=transcript_original[:100],
            confidence=confidence,
        )

        # ── Translate to English if needed ─────────────────────────────────
        if source_language == SupportedLanguage.ENGLISH:
            transcript_english = transcript_original
        else:
            transcript_english = await self._translate_to_english(
                transcript_original, source_language
            )

        return TranscriptionResult(
            transcript_english=transcript_english,
            transcript_original=transcript_original,
            source_language=source_language,
            confidence=confidence,
            detected_language_code=bcp47,
        )

    # ── Step 2: Translation (source → English) ─────────────────────────────────

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=6))
    async def _translate_to_english(
        self, text: str, source_language: SupportedLanguage
    ) -> str:
        """Translate text to English using Cloud Translation API v2."""
        import asyncio

        client = self._get_translate_client()
        source_code = _LANG_TO_BCP47[source_language].split("-")[0]  # "kn" from "kn-IN"

        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda: client.translate(
                text,
                source_language=source_code,
                target_language="en",
            ),
        )

        translated = result["translatedText"]
        log.debug(
            "voice.translated_to_english",
            source=source_code,
            original=text[:80],
            translated=translated[:80],
        )
        return translated

    # ── Step 3: Translate prescription back to source language ────────────────

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=6))
    async def _translate_from_english(
        self, text: str, target_language: SupportedLanguage
    ) -> str:
        """Translate English text back to the source (vernacular) language."""
        if target_language == SupportedLanguage.ENGLISH:
            return text

        import asyncio

        client = self._get_translate_client()
        target_code = _LANG_TO_BCP47[target_language].split("-")[0]  # "kn"

        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda: client.translate(
                text,
                source_language="en",
                target_language=target_code,
            ),
        )

        translated = result["translatedText"]
        log.debug(
            "voice.translated_from_english",
            target=target_code,
            translated=translated[:80],
        )
        return translated

    # ── Step 4: Optional Text-to-Speech response audio ────────────────────────

    async def _synthesize_speech(
        self, text: str, language: SupportedLanguage
    ) -> bytes | None:
        """
        Synthesise MP3 audio from text using Cloud Text-to-Speech.
        Returns raw MP3 bytes, or None if TTS is disabled/fails.
        """
        if not self._settings.voice_enable_tts_response:
            return None

        import asyncio

        voice_config = _TTS_VOICES.get(language, _TTS_VOICES[SupportedLanguage.ENGLISH])

        synthesis_input = texttospeech.SynthesisInput(text=text)
        voice = texttospeech.VoiceSelectionParams(
            language_code=voice_config["language_code"],
            name=voice_config["name"],
            ssml_gender=voice_config["ssml_gender"],
        )
        audio_config = texttospeech.AudioConfig(
            audio_encoding=texttospeech.AudioEncoding.MP3,
            speaking_rate=0.9,    # Slightly slower for clarity
            pitch=0.0,
        )

        client = self._get_tts_client()
        loop = asyncio.get_event_loop()

        try:
            response = await loop.run_in_executor(
                None,
                lambda: client.synthesize_speech(
                    input=synthesis_input,
                    voice=voice,
                    audio_config=audio_config,
                ),
            )
            log.info(
                "voice.tts_complete",
                language=language.value,
                audio_bytes=len(response.audio_content),
            )
            return response.audio_content
        except Exception as exc:
            log.warning("voice.tts_failed", error=str(exc))
            return None

    # ── Main pipeline ──────────────────────────────────────────────────────────

    async def process_voice_prescription(
        self,
        audio_bytes: bytes,
        source_language: SupportedLanguage = SupportedLanguage.KANNADA,
        audio_encoding: str = "LINEAR16",
        sample_rate_hz: int = 16000,
        coordinates: Coordinates | None = None,
    ) -> VoicePrescriptionResponse:
        """
        Full Bhasha pipeline:
          Audio → STT → Translate → Prescribe → Translate Back → [TTS]

        Parameters:
          audio_bytes     — Raw audio bytes from the client
          source_language — Language spoken by the user
          audio_encoding  — Audio format (LINEAR16, OGG_OPUS, MP3)
          sample_rate_hz  — Audio sample rate in Hz
          coordinates     — GPS coordinates from device (preferred over extracted)

        Returns VoicePrescriptionResponse with all fields populated.
        """
        steps: list[str] = []

        # ── 1. Speech-to-Text ──────────────────────────────────────────────
        steps.append("1. Speech-to-Text (Google Cloud Speech API)")
        transcription = await self.transcribe_audio(
            audio_bytes=audio_bytes,
            source_language=source_language,
            audio_encoding=audio_encoding,
            sample_rate_hz=sample_rate_hz,
        )

        # ── 2. Extract prescription context ───────────────────────────────
        steps.append("2. Context extraction from transcript")
        prescription_req = _extract_prescription_context(
            transcription.transcript_english
        )

        # If the caller provided explicit GPS coords (from device sensor),
        # override the default Bengaluru centre with the real location.
        if coordinates is not None:
            prescription_req = prescription_req.model_copy(
                update={"coordinates": coordinates}
            )

        # ── 3. Gemini prescription ─────────────────────────────────────────
        steps.append("3. AI Tree Prescription (Gemini 1.5 Pro)")
        primary, alternatives = await self._gemini_service.prescribe_species(
            prescription_req
        )

        from app.core.config import get_settings
        settings = get_settings()

        prescription = PrescriptionResponse(
            coordinates=prescription_req.coordinates,
            primary_recommendation=primary,
            alternative_recommendations=alternatives,
            gemini_model_used=settings.gemini_model,
        )

        # ── 4. Build vernacular summary ────────────────────────────────────
        steps.append(f"4. Translation to {source_language.value} (Cloud Translation API)")

        english_summary = _build_vernacular_summary(
            primary_species_name=primary.common_name,
            why_recommended=primary.why_recommended,
            water_req=primary.water_requirement or "moderate",
            growth_rate=primary.growth_rate or "moderate",
            co2=primary.co2_absorption_kg_per_year,
        )

        # Translate key fields back to source language
        species_name_vernacular = primary.kannada_name or primary.common_name
        why_vernacular, full_vernacular = primary.why_recommended, english_summary

        if source_language != SupportedLanguage.ENGLISH:
            why_vernacular = await self._translate_from_english(
                primary.why_recommended, source_language
            )
            full_vernacular = await self._translate_from_english(
                english_summary, source_language
            )

        # ── 5. Optional TTS audio response ────────────────────────────────
        audio_b64: str | None = None
        if self._settings.voice_enable_tts_response:
            steps.append("5. Text-to-Speech audio synthesis (Cloud TTS API)")
            audio_bytes_out = await self._synthesize_speech(
                full_vernacular, source_language
            )
            if audio_bytes_out:
                audio_b64 = base64.b64encode(audio_bytes_out).decode("utf-8")
        else:
            steps.append("5. TTS disabled (set VOICE_ENABLE_TTS_RESPONSE=true to enable)")

        log.info(
            "voice.pipeline_complete",
            language=source_language.value,
            primary_species=primary.common_name,
            steps_count=len(steps),
        )

        return VoicePrescriptionResponse(
            transcription=transcription,
            prescription=prescription,
            primary_species_name_vernacular=species_name_vernacular,
            why_recommended_vernacular=why_vernacular,
            full_prescription_vernacular=full_vernacular,
            audio_response_base64=audio_b64,
            source_language=source_language,
            processing_steps=steps,
        )
