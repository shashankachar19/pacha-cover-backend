# ============================================================
# app/core/firebase.py
#
# Firebase Admin SDK initialisation and Firestore client factory.
#
# Design:
#   • _initialize_firebase() is called once at startup in main.py
#   • get_firestore_client() is a FastAPI dependency that returns
#     a Firestore AsyncClient for each request
# ============================================================

from __future__ import annotations

import firebase_admin
from firebase_admin import credentials, firestore_async
from google.cloud.firestore import AsyncClient

from app.core.config import get_settings

_firebase_app: firebase_admin.App | None = None

def _initialize_firebase() -> firebase_admin.App:
    """
    Initialise the Firebase Admin SDK (idempotent).
    Called once during application startup.
    """
    global _firebase_app

    if _firebase_app is not None:
        return _firebase_app

    settings = get_settings()

    try:
        cred = credentials.Certificate(settings.firebase_service_account_path)
        _firebase_app = firebase_admin.initialize_app(cred, {
            "projectId": settings.gcp_project_id,
        })
    except (FileNotFoundError, ValueError):
        # Fallback: use Application Default Credentials (Cloud Run / GCE)
        _firebase_app = firebase_admin.initialize_app()

    return _firebase_app


def get_firestore_client() -> AsyncClient:
    """
    FastAPI dependency — returns a Firestore AsyncClient.
    The client is lightweight and safe to create per-request.
    """
    if _firebase_app is None:
        _initialize_firebase()
    return firestore_async.client()
