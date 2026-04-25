# ============================================================
# app/api/v1/endpoints/carbon.py
#
# Feature 3 — AI Carbon Credit & Property Tax Rebate Simulator
#
# POST /api/v1/carbon/simulate
#     → Full simulation: CO2 profile + credit value + tax rebate
#
# GET  /api/v1/carbon/rates
#     → Returns the current carbon credit and rebate rate config
#       (useful for the UI to explain the calculation to users)
#
# Auth:
#   POST /simulate → Requires Firebase Auth.
#   GET  /rates    → Public.
# ============================================================

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.auth import get_current_user
from app.core.config import get_settings
from app.core.logging import get_logger
from app.models.schemas import CarbonCreditRequest, CarbonCreditResponse

router = APIRouter(prefix="/carbon", tags=["Carbon Credit & Tax Simulator"])
log = get_logger(__name__)

# Singleton — same pattern as GeminiService
from app.services.carbon_service import CarbonService
_carbon_service = CarbonService()


# ── POST /carbon/simulate ──────────────────────────────────────────────────────

@router.post(
    "/simulate",
    response_model=CarbonCreditResponse,
    status_code=status.HTTP_200_OK,
    summary="Simulate carbon credits and property tax rebate for planted trees",
    description=(
        "Uses **Gemini 1.5 Pro** to compute a scientifically grounded CO2 "
        "sequestration profile for a given tree species and age, then:\n\n"
        "1. Calculates the **voluntary carbon credit value** in INR "
        "(at India VCM rate of ₹1,000/tonne CO2).\n"
        "2. Simulates a **BBMP property tax rebate** — 1% per 20kg CO2/year, "
        "capped at 20%.\n"
        "3. Returns a year-by-year CO2 profile with relatable equivalencies "
        "(car km, flights).\n\n"
        "Supports multi-tree simulation via `num_trees` parameter.\n\n"
        "**Example:** A 5-year-old Neem tree sequesters ~22kg CO2/year → "
        "₹22 carbon credit value + 1% tax rebate."
    ),
)
async def simulate_carbon_credit(
    request: CarbonCreditRequest,
    current_user: dict = Depends(get_current_user),
) -> CarbonCreditResponse:
    """
    Full environmental ROI simulation.

    Example request:
    ```json
    {
      "species_common_name": "Neem",
      "species_scientific_name": "Azadirachta indica",
      "tree_age_years": 5,
      "num_trees": 3,
      "property_value_inr": 5000000
    }
    ```
    """
    uid = current_user.get("uid", "unknown")
    log.info(
        "carbon.simulate_request",
        uid=uid,
        species=request.species_common_name,
        age=request.tree_age_years,
        num_trees=request.num_trees,
    )

    try:
        result = await _carbon_service.simulate(request)

    except ValueError as exc:
        log.error("carbon.parse_error", uid=uid, error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="AI carbon model returned an unexpected response. Please retry.",
        )
    except Exception as exc:
        log.error("carbon.service_error", uid=uid, error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Carbon simulation service temporarily unavailable.",
        )

    log.info(
        "carbon.simulation_complete",
        uid=uid,
        annual_co2=result.total_annual_co2_kg,
        credit_inr=result.carbon_credit_value_inr,
        rebate_pct=result.tax_rebate.rebate_percent,
    )
    return result


# ── GET /carbon/rates ──────────────────────────────────────────────────────────

@router.get(
    "/rates",
    summary="Get current carbon credit and tax rebate configuration",
    description=(
        "Returns the rates used in simulations — helpful for the UI to "
        "display explanation tooltips without hard-coding values."
    ),
)
async def get_carbon_rates(settings=Depends(get_settings)) -> dict:
    """
    Public endpoint — no auth required.
    Returns current simulation parameters.
    """
    return {
        "carbon_credit_rate_inr_per_tonne": settings.carbon_credit_rate_inr_per_tonne,
        "tax_rebate_rule": {
            "rebate_percent_per_co2_kg": round(
                1 / settings.tax_rebate_co2_per_percent, 4
            ),
            "co2_kg_per_percent_rebate": settings.tax_rebate_co2_per_percent,
            "max_rebate_percent": settings.tax_rebate_max_percent,
            "description": (
                f"1% property tax rebate for every "
                f"{settings.tax_rebate_co2_per_percent:.0f} kg CO2 sequestered "
                f"per year, capped at {settings.tax_rebate_max_percent:.0f}%."
            ),
        },
        "carbon_equivalencies": {
            "co2_kg_per_car_km": 0.21,
            "co2_kg_per_short_flight": 90,
            "note": "Based on avg petrol car (0.21 kg CO2/km) and 1000km flight.",
        },
        "disclaimer": (
            "Carbon credit rates are based on India's voluntary carbon market "
            "(2024). Tax rebates are illustrative simulations — not current "
            "BBMP policy. Actual credits/rebates require certified auditing."
        ),
    }
