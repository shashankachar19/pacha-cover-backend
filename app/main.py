# ============================================================
# app/main.py
#
# FastAPI Application Factory — Pacha (Green) Cover v1.1
#
# Responsibilities:
#   • Creates and configures the FastAPI app instance
#   • Registers all middleware (CORS, logging, error handling)
#   • Mounts the versioned API router (8 feature modules)
#   • Exposes health check and root endpoints
#   • Handles application lifecycle (startup / shutdown hooks)
#
# Entry point:
#   uvicorn app.main:app --host 0.0.0.0 --port 8080 --reload
#
# Cloud Run deployment:
#   The Dockerfile sets CMD ["uvicorn", "app.main:app",
#   "--host", "0.0.0.0", "--port", "8080", "--workers", "4"]
# ============================================================

import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.firebase import get_firestore_client, _initialize_firebase
from app.core.logging import get_logger, setup_logging

# ── Bootstrap logging immediately ─────────────────────────────────────────────
setup_logging()
log = get_logger(__name__)
settings = get_settings()


# ── Lifespan (startup / shutdown) ─────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Runs once on startup (before serving requests) and once on shutdown.
    Used for expensive one-time initialisation:
      - Firebase Admin SDK
      - GEE auth (lazy, in EarthEngineService)
      - Vertex AI SDK (lazy, in VertexAIService)
    """
    log.info(
        "pacha_cover.starting",
        version=settings.app_version,
        env=settings.app_env,
        project=settings.gcp_project_id,
    )

    # Initialise Firebase Admin SDK at startup so the first
    # authenticated request doesn't bear the init overhead.
    try:
        _initialize_firebase()
        log.info("pacha_cover.firebase_ready")
    except Exception as exc:
        log.error("pacha_cover.firebase_init_failed", error=str(exc))
        # Don't crash — Firebase might not be needed for public endpoints.

    log.info("pacha_cover.ready", host="0.0.0.0", port=8080)

    yield  # ← Application is live and serving requests

    log.info("pacha_cover.shutting_down")


# ── Application factory ────────────────────────────────────────────────────────

def create_app() -> FastAPI:
    """
    Creates and configures the FastAPI application.
    Separated into a factory function to make testing easier
    (pytest can call create_app() with overridden settings).
    """
    app = FastAPI(
        title="Pacha Cover API",
        description=(
            "🌿 **Pacha (Green) Cover** — AI-powered urban canopy restorer for Bengaluru.\n\n"
            "Built for the **Build for Bengaluru** hackathon.\n\n"
            "### Core Features\n"
            "- **Heat Map** — Ward-level NDVI & Land Surface Temperature from Google Earth Engine\n"
            "- **Precision Prescription** — Gemini 1.5 Pro native tree species recommender\n"
            "- **Green Ledger** — Citizen 'Adopt a Spot' tree planting tracker\n"
            "- **Verification Pipeline** — Vertex AI sapling photo verification & Green Points\n\n"
            "### Extended Features (v1.1)\n"
            "- **Pacha Vision AR** — 3D tree models for ARCore visualisation\n"
            "- **Green Corridors** — Geospatial clustering of verified plantings\n"
            "- **Carbon & Tax Simulator** — AI-powered CO₂ sequestration & BBMP tax rebate\n"
            "- **Bhasha Voice** — Vernacular voice interface (Kannada, Hindi, Tamil, Telugu)\n\n"
            "### Rotary Areas of Focus\n"
            "Environment · Community Economic Development · Basic Education & Literacy"
        ),
        version=settings.app_version,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )

    # ── CORS ───────────────────────────────────────────────────────────────
    # Allows the Flutter/React frontend and Web dashboard to call the API.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Request Timing Middleware ──────────────────────────────────────────
    @app.middleware("http")
    async def add_process_time_header(request: Request, call_next):
        """
        Adds X-Process-Time header to every response.
        Useful for performance monitoring in Cloud Logging.
        """
        start = time.perf_counter()
        response = await call_next(request)
        duration_ms = round((time.perf_counter() - start) * 1000, 2)
        response.headers["X-Process-Time"] = f"{duration_ms}ms"

        log.debug(
            "http.request",
            method=request.method,
            path=request.url.path,
            status=response.status_code,
            duration_ms=duration_ms,
        )
        return response

    # ── Global Exception Handler ───────────────────────────────────────────
    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        """
        Catch-all for unhandled exceptions.
        Returns a clean JSON error instead of a raw Python traceback.
        In production, also logs to Cloud Error Reporting.
        """
        log.error(
            "http.unhandled_exception",
            method=request.method,
            path=request.url.path,
            error=str(exc),
            exc_info=True,
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "success": False,
                "message": "An unexpected error occurred. Please try again.",
                "data": None,
            },
        )

    # ── Routes ─────────────────────────────────────────────────────────────
    app.include_router(api_router)

    # ── Health Check (required by Cloud Run / load balancer) ──────────────
    @app.get(
        "/health",
        tags=["Infrastructure"],
        summary="Health check — used by Cloud Run",
    )
    async def health_check():
        """
        Returns 200 if the service is running.
        Cloud Run's liveness probe hits this endpoint every 30s.
        """
        return {
            "status": "healthy",
            "service": "pacha-cover-api",
            "version": settings.app_version,
            "environment": settings.app_env,
        }

    @app.get("/", tags=["Infrastructure"], include_in_schema=False)
    async def root():
        return {
            "message": "🌿 Pacha Cover API v1.1 is running. Visit /docs for the API reference.",
            "docs": "/docs",
        }

    return app


# ── Module-level app instance ──────────────────────────────────────────────────
# uvicorn imports this directly: uvicorn app.main:app
app = create_app()
