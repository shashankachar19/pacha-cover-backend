# ============================================================
# app/api/v1/router.py
#
# Top-level v1 API router.
# Adding a new feature = create its router file + add one line here.
#
# Route summary:
#   Original features:
#     GET/          /heatmap, /heatmap/{ward_id}
#     POST          /prescribe
#     POST/GET/...  /ledger/*
#     POST          /verify-growth
#
#   Extended features (v1.1):
#     GET  /assets/ar-model/{species_id}   Feature 1: Pacha Vision AR
#     GET  /assets/ar-models               Feature 1: AR catalogue
#     POST /corridors/audit                Feature 2: Green Corridor
#     GET  /corridors, /corridors/ward/*   Feature 2: Corridor queries
#     POST /carbon/simulate                Feature 3: Carbon Simulator
#     GET  /carbon/rates                   Feature 3: Rate config
#     POST /voice/prescribe                Feature 4: Bhasha voice
#     GET  /voice/languages                Feature 4: Language list
#     POST /voice/translate                Feature 4: Text translation
# ============================================================

from fastapi import APIRouter

from app.api.v1.endpoints import (
    heatmap,
    ledger,
    prescribe,
    verify,
    verify_image,
    assets,
    corridors,
    carbon,
    voice,
    auth,
    communities,
)

api_router = APIRouter(prefix="/api/v1")

# Original features
api_router.include_router(heatmap.router)
api_router.include_router(prescribe.router)
api_router.include_router(ledger.router)
api_router.include_router(verify.router)
api_router.include_router(verify_image.router)  # stateless demo endpoint

# Extended features (v1.1)
api_router.include_router(assets.router)
api_router.include_router(corridors.router)
api_router.include_router(carbon.router)
api_router.include_router(voice.router)
api_router.include_router(auth.router)
api_router.include_router(communities.router)
