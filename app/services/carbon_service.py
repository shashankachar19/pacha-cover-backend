# ============================================================
# app/services/carbon_service.py
#
# Feature 3 — AI Carbon Credit & Property Tax Rebate Simulator
#
# This service EXTENDS gemini_service.py with a new prompt chain
# for environmental ROI calculation — keeping concerns separated
# without modifying the existing GeminiService class.
#
# Pipeline:
#   1. Build a carbon-focused Gemini prompt using species + age data
#   2. Gemini returns a structured JSON with year-by-year CO2 profile
#   3. We compute:
#        a. Total lifetime CO2 sequestration
#        b. Voluntary carbon credit value (India VCM rate)
#        c. Simulated BBMP property tax rebate
#           Rule: 1% rebate per 20kg CO2/year, capped at 20%
#   4. Return the full CarbonCreditResponse
#
# Key scientific notes:
#   • CO2 sequestration is non-linear: saplings fix less carbon
#     than mature trees. Gemini models this as a growth curve.
#   • India VCM rate: ~₹800–₹1,200 per tonne CO2 (mid: ₹1,000)
#   • 1 tonne CO2 ≈ 2,800 km driven in a typical petrol car
#   • 1 tonne CO2 ≈ 2.5 short-haul flights (1,000 km each)
#
# Gemini prompt strategy:
#   • Separate GenerativeModel instance with higher temperature (0.5)
#     to allow more nuanced ecological narrative in the explanation.
#   • Strict JSON schema enforced — same pattern as prescribe_species.
# ============================================================

import json
import math
import re
import uuid
from datetime import datetime, timezone

import google.generativeai as genai
from tenacity import retry, stop_after_attempt, wait_exponential

from app.core.config import get_settings
from app.core.logging import get_logger
from app.models.schemas import (
    AnnualCarbonProfile,
    CarbonCreditRequest,
    CarbonCreditResponse,
    TaxRebateSimulation,
)

log = get_logger(__name__)
UTC = timezone.utc

# ── Gemini system prompt for carbon analysis ───────────────────────────────────

_CARBON_SYSTEM_CONTEXT = """
You are an expert urban ecology and carbon accounting scientist specialising
in tropical tree species in South Indian cities.

Your task is to estimate the annual and cumulative CO2 sequestration for a
given tree species at a given age, using published scientific data on:
  - Biomass growth rates for South Indian tropical species
  - Carbon content fraction (~50% of dry biomass is carbon)
  - IPCC carbon accounting methodologies for urban forestry (IPCC 2006, Tier 2)
  - India-specific growth studies from ICFRE (Indian Council of Forestry Research)

IMPORTANT: Respond ONLY with valid JSON. No markdown, no preamble, no units outside the JSON.
"""

_CARBON_SCHEMA = """
Return this exact JSON structure (fill all numeric fields; use realistic values):
{
  "annual_co2_kg_per_tree": <number — CO2 kg sequestered per year at the given age>,
  "cumulative_co2_kg_lifetime": <number — total CO2 kg sequestered from year 1 to given age>,
  "annual_profile": [
    {
      "year": 1,
      "co2_kg_sequestered": <number>,
      "cumulative_co2_kg": <number>
    },
    ... (include years 1 through min(tree_age, 10))
  ],
  "gemini_narrative": "<2-3 sentence plain-English explanation of the environmental impact, suitable for a citizen app. Mention the species name, the total CO2, and a relatable comparison.>"
}
"""


def _build_carbon_prompt(req: CarbonCreditRequest) -> str:
    parts = [
        f"Tree species: {req.species_common_name}",
    ]
    if req.species_scientific_name:
        parts.append(f"Scientific name: {req.species_scientific_name}")

    parts.extend([
        f"Tree age to evaluate: {req.tree_age_years} year(s)",
        f"Number of trees: {req.num_trees}",
        "Location context: Bengaluru, Karnataka, India (920m altitude, "
        "tropical savanna climate, red laterite soil)",
    ])

    context = "\n".join(parts)
    return (
        f"Given the following tree data:\n{context}\n\n"
        "Calculate the CO2 sequestration profile for ONE tree of this species "
        "at the given age. Include realistic year-by-year data reflecting the "
        "non-linear growth curve (saplings fix less carbon than mature trees).\n\n"
        f"{_CARBON_SCHEMA}"
    )


def _parse_carbon_response(raw_text: str) -> dict:
    clean = re.sub(r"```(?:json)?|```", "", raw_text).strip()
    try:
        return json.loads(clean)
    except json.JSONDecodeError as exc:
        log.error("carbon.json_parse_error", raw=raw_text[:300], error=str(exc))
        raise ValueError(f"Gemini returned non-JSON carbon data: {exc}") from exc


def _compute_tax_rebate(
    annual_co2_kg: float,
    property_value_inr: float | None,
    co2_per_percent: float,
    max_percent: float,
) -> TaxRebateSimulation:
    """
    Simulate BBMP property tax rebate.

    Rule (illustrative — not current BBMP policy):
      rebate_percent = floor(annual_co2_kg / co2_per_percent)
      capped at max_percent

    e.g. 22kg CO2/year (Neem) → floor(22/20) = 1% rebate
         100kg CO2/year (Peepal) → floor(100/20) = 5% rebate
    """
    rebate_percent = min(
        math.floor(annual_co2_kg / co2_per_percent),
        max_percent,
    )

    rebate_amount: float | None = None
    if property_value_inr is not None:
        rebate_amount = round(property_value_inr * rebate_percent / 100, 2)

    note = (
        f"Your {annual_co2_kg:.1f} kg/year CO2 sequestration qualifies for "
        f"a {rebate_percent:.0f}% property tax rebate "
        f"(₹1 rebate per {co2_per_percent:.0f} kg CO2/year, max {max_percent:.0f}%). "
    )
    if rebate_amount is not None:
        note += (
            f"On a property valued at ₹{property_value_inr:,.0f}, "
            f"this equals ₹{rebate_amount:,.2f} annual savings. "
        )
    note += "Note: This is a simulation — not current BBMP policy."

    return TaxRebateSimulation(
        annual_co2_kg=annual_co2_kg,
        rebate_percent=float(rebate_percent),
        rebate_amount_inr=rebate_amount,
        rebate_calculation_note=note,
    )


def _co2_to_equivalencies(co2_kg: float) -> tuple[float, float]:
    """
    Convert CO2 kg to relatable equivalencies.
    Returns (car_km_offset, flights_offset).
    """
    # Avg petrol car: ~0.21 kg CO2/km
    car_km = round(co2_kg / 0.21, 1)
    # Short-haul flight (1000km): ~90 kg CO2 per passenger
    flights = round(co2_kg / 90, 2)
    return car_km, flights


# ── Service class ──────────────────────────────────────────────────────────────

class CarbonService:
    """
    Carbon Credit & Tax Rebate simulation powered by Gemini 1.5 Pro.

    Instantiated once per process (same pattern as GeminiService).
    """

    def __init__(self) -> None:
        import asyncio
        self._settings = get_settings()
        self._lock = asyncio.Lock()

        _safety_settings = [
            {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
        ]

        # Slightly higher temperature than prescription — we want
        # a more engaging narrative section while keeping numbers grounded.
        self._model = genai.GenerativeModel(
            model_name=self._settings.gemini_model,
            system_instruction=_CARBON_SYSTEM_CONTEXT,
            generation_config=genai.GenerationConfig(
                temperature=0.4,
                top_p=0.9,
                response_mime_type="application/json",
            ),
            safety_settings=_safety_settings,
        )
        log.info("carbon.service_ready", model=self._settings.gemini_model)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=8),
        reraise=True,
    )
    async def simulate(self, req: CarbonCreditRequest) -> CarbonCreditResponse:
        """
        Run the full carbon + tax rebate simulation.

        Returns a CarbonCreditResponse with:
          - Year-by-year CO2 profile (up to 10 years)
          - Lifetime cumulative sequestration
          - Carbon credit market value in INR
          - BBMP property tax rebate simulation
          - Gemini narrative for citizen communication
        """
        import asyncio

        prompt = _build_carbon_prompt(req)
        log.info(
            "carbon.simulating",
            species=req.species_common_name,
            age=req.tree_age_years,
            num_trees=req.num_trees,
        )

        loop = asyncio.get_event_loop()
        async with self._lock:
            genai.configure(api_key=self._settings.gemini_api_key_prescribe)
            response = await loop.run_in_executor(
                None, self._model.generate_content, prompt
            )

        raw = _parse_carbon_response(response.text)

        # ── Extract Gemini values ──────────────────────────────────────────
        annual_co2_per_tree: float = float(raw["annual_co2_kg_per_tree"])
        cumulative_per_tree: float = float(raw["cumulative_co2_kg_lifetime"])
        gemini_narrative: str = raw.get("gemini_narrative", "")

        # Scale to all trees
        total_annual = round(annual_co2_per_tree * req.num_trees, 2)
        total_cumulative = round(cumulative_per_tree * req.num_trees, 2)

        # ── Build annual profile ───────────────────────────────────────────
        profile_raw: list[dict] = raw.get("annual_profile", [])
        annual_profile: list[AnnualCarbonProfile] = []

        for entry in profile_raw:
            yr = int(entry["year"])
            yr_co2 = float(entry["co2_kg_sequestered"]) * req.num_trees
            cum_co2 = float(entry["cumulative_co2_kg"]) * req.num_trees
            car_km, flights = _co2_to_equivalencies(yr_co2)
            annual_profile.append(
                AnnualCarbonProfile(
                    year=yr,
                    co2_kg_sequestered=round(yr_co2, 2),
                    cumulative_co2_kg=round(cum_co2, 2),
                    equivalent_car_km_offset=car_km,
                    equivalent_flights_offset=flights,
                )
            )

        # ── Carbon credit value ────────────────────────────────────────────
        rate = self._settings.carbon_credit_rate_inr_per_tonne
        # Annual value (per year at current age)
        credit_value = round((total_annual / 1000) * rate, 2)

        # ── Tax rebate simulation ──────────────────────────────────────────
        tax_rebate = _compute_tax_rebate(
            annual_co2_kg=total_annual,
            property_value_inr=req.property_value_inr,
            co2_per_percent=self._settings.tax_rebate_co2_per_percent,
            max_percent=self._settings.tax_rebate_max_percent,
        )

        log.info(
            "carbon.simulation_complete",
            species=req.species_common_name,
            annual_co2=total_annual,
            credit_value_inr=credit_value,
            rebate_percent=tax_rebate.rebate_percent,
        )

        return CarbonCreditResponse(
            species_common_name=req.species_common_name,
            species_scientific_name=req.species_scientific_name,
            num_trees=req.num_trees,
            tree_age_years=req.tree_age_years,
            annual_co2_kg_per_tree=round(annual_co2_per_tree, 2),
            total_annual_co2_kg=total_annual,
            cumulative_co2_kg_lifetime=total_cumulative,
            annual_profile=annual_profile,
            carbon_credit_value_inr=credit_value,
            carbon_credit_rate_inr_per_tonne=rate,
            tax_rebate=tax_rebate,
            gemini_narrative=gemini_narrative,
            gemini_model_used=self._settings.gemini_model,
        )
