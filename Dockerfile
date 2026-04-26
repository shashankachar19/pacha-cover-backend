# ============================================================
# Dockerfile — Pacha Cover Unified (Frontend + Backend)
# Optimised for Google Cloud Run
# ============================================================

# ── Stage 1: Frontend Builder ──────────────────────────────────────────────────
FROM node:20-slim AS frontend-builder
WORKDIR /build-frontend
COPY frontend/package*.json ./
RUN npm install
COPY frontend/ .
# Note: Ensure VITE_ API URLs are handled if not using relative paths
RUN npm run build

# ── Stage 2: Backend Builder ───────────────────────────────────────────────────
FROM python:3.12-slim AS backend-builder
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1
WORKDIR /build-backend
RUN apt-get update && apt-get install -y --no-install-recommends build-essential && rm -rf /var/lib/apt/lists/*
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

# ── Stage 3: Runtime ───────────────────────────────────────────────────────────
FROM python:3.12-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    PORT=8080

WORKDIR /app

# Copy virtualenv from backend-builder
COPY --from=backend-builder /opt/venv /opt/venv

# Copy backend source
COPY app/ ./app/

# Copy compiled frontend from frontend-builder to 'static' folder
COPY --from=frontend-builder /build-frontend/dist ./static

# Optional: Copy service account keys if they are required to be local 
# (Better to use Secret Manager in production)
COPY serviceAccountKey.json .
COPY gee_key.json .

# Cloud Run sets PORT env var automatically
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port $PORT --workers 4"]
