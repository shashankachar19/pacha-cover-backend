# ============================================================
# Dockerfile — Pacha Cover API v1.1
# Optimised for Google Cloud Run (asia-south1)
#
# Multi-stage build:
#   Stage 1 (builder) — installs dependencies in a venv
#   Stage 2 (runtime) — copies only the venv + app code
#   Result: ~250MB image vs ~900MB naive build
# ============================================================

# ── Stage 1: Builder ───────────────────────────────────────────────────────────
FROM python:3.12-slim AS builder

# Prevents Python from writing .pyc files and enables stdout/stderr logging
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /build

# Install build tools needed for some C extensions (e.g. grpcio)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libssl-dev \
    && rm -rf /var/lib/apt/lists/*

# Create and activate a virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Install Python dependencies (layer-cached unless requirements.txt changes)
COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt


# ── Stage 2: Runtime ───────────────────────────────────────────────────────────
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    PORT=8080

WORKDIR /app

# Copy the venv from the builder stage (no build tools needed at runtime)
COPY --from=builder /opt/venv /opt/venv

# Copy application source code
COPY app/ ./app/

# Cloud Run sets PORT env var — uvicorn reads it via shell expansion
# Workers = 4 is suitable for Cloud Run's default 2 vCPU allocation
CMD ["sh", "-c", \
     "uvicorn app.main:app --host 0.0.0.0 --port $PORT --workers 4 --log-level info"]
