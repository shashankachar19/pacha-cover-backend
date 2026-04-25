# 🌿 Pacha Cover — AI-Powered Urban Canopy Restorer

**Built for the Build for Bengaluru Hackathon**

> *"Pacha" (ಪಚ್ಚ) means Green in Kannada.*

Pacha Cover uses satellite data, AI, and citizen science to identify urban heat islands across Bengaluru's 198 BBMP wards and mobilise residents to restore the city's disappearing tree canopy — one adopted spot at a time.

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        CLIENT LAYER                             │
│         Flutter Mobile App  ←→  React Web Dashboard             │
└───────────────────────────┬─────────────────────────────────────┘
                            │ HTTPS / Firebase Auth JWT
┌───────────────────────────▼─────────────────────────────────────┐
│                    FASTAPI BACKEND (Cloud Run)                   │
│  ┌──────────────┐ ┌─────────────┐ ┌──────────┐ ┌────────────┐  │
│  │  Heat Map    │ │  Prescribe  │ │  Ledger  │ │  Verify    │  │
│  │  /heatmap    │ │  /prescribe │ │  /ledger │ │  /verify-  │  │
│  │  (GEE Data)  │ │  (Gemini)   │ │  (CRUD)  │ │  growth    │  │
│  └──────┬───────┘ └──────┬──────┘ └────┬─────┘ └─────┬──────┘  │
└─────────┼────────────────┼─────────────┼─────────────┼──────────┘
          │                │             │             │
     ┌────▼───┐      ┌─────▼────┐  ┌────▼─────┐ ┌────▼──────┐
     │ Google │      │  Gemini  │  │Firestore │ │ Vertex AI │
     │ Earth  │      │  1.5 Pro │  │(NoSQL DB)│ │  Vision   │
     │ Engine │      │  (AI)    │  │          │ │  + GCS    │
     └────────┘      └──────────┘  └──────────┘ └───────────┘
                                        │
                              ┌─────────▼──────────┐
                              │ Firebase Cloud Fns  │
                              │ • on_user_created   │
                              │ • update_leaderboard│
                              │ • award_badges      │
                              └────────────────────┘
```

---

## 📁 Directory Structure

```
pacha-cover/
├── app/
│   ├── main.py                         # FastAPI app factory + middleware
│   ├── api/
│   │   └── v1/
│   │       ├── router.py               # Aggregates all endpoint routers
│   │       └── endpoints/
│   │           ├── heatmap.py          # GET  /heatmap
│   │           ├── prescribe.py        # POST /prescribe
│   │           ├── ledger.py           # CRUD /ledger
│   │           ├── verify.py           # POST /verify-growth
│   │           └── users.py            # GET  /users/me, /leaderboard
│   ├── core/
│   │   ├── config.py                   # Pydantic settings (12-factor)
│   │   ├── logging.py                  # Structlog → Cloud Logging JSON
│   │   ├── firebase.py                 # Firebase Admin SDK init
│   │   └── auth.py                     # Firebase JWT verification dep
│   ├── models/
│   │   ├── schemas.py                  # All Pydantic request/response models
│   │   └── firestore_collections.py    # Collection name constants
│   └── services/
│       ├── earth_engine_service.py     # GEE NDVI + LST satellite data
│       ├── gemini_service.py           # Gemini 1.5 Pro prescription engine
│       ├── ledger_service.py           # Firestore CRUD for adopted spots
│       └── vertex_ai_service.py        # Vertex AI sapling verification
├── functions/
│   └── main.py                         # Firebase Cloud Functions
├── tests/
│   └── test_api.py                     # pytest integration tests
├── Dockerfile                          # Multi-stage Cloud Run image
├── cloudbuild.yaml                     # Cloud Build CI/CD pipeline
├── firestore.indexes.json              # Composite index definitions
├── firestore.rules                     # Client-side security rules
├── requirements.txt
└── .env.example
```

---

## 🚀 Quick Start (Local Development)

### Prerequisites
- Python 3.12+
- A Google Cloud project with billing enabled
- Firebase project (can be the same GCP project)

### 1. Clone and set up environment

```bash
git clone https://github.com/your-org/pacha-cover.git
cd pacha-cover

python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure environment variables

```bash
cp .env.example .env
# Edit .env with your real values
```

### 3. Set up Firebase credentials

```bash
# Download your service account key from Firebase Console:
# Project Settings → Service Accounts → Generate New Private Key
# Save as serviceAccountKey.json in the project root
```

### 4. Run the development server

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8080 --reload
```

Visit http://localhost:8080/docs for the interactive Swagger UI.

---

## 🌐 API Endpoints

### Heat Map
| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/api/v1/heatmap` | Optional | All BBMP wards with NDVI, LST, heat risk |
| GET | `/api/v1/heatmap/{ward_id}` | Optional | Single ward data |

**Query params:** `?risk_level=high`, `?ward_name=Koramangala`

### Precision Prescription (Gemini AI)
| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/api/v1/prescribe` | ✅ Required | AI tree species recommendation |

```json
// Request
{
  "coordinates": { "latitude": 12.9352, "longitude": 77.6245 },
  "ward_name": "Koramangala",
  "nearby_land_use": "roadside",
  "soil_type": "red laterite",
  "plot_area_sqm": 25
}

// Response
{
  "primary_recommendation": {
    "common_name": "Neem",
    "scientific_name": "Azadirachta indica",
    "kannada_name": "ಬೇವು",
    "why_recommended": "Neem thrives in Bengaluru's laterite soil...",
    "water_requirement": "Low",
    "growth_rate": "Fast",
    "co2_absorption_kg_per_year": 22.0
  },
  "alternative_recommendations": [...]
}
```

### Green Ledger (Adopt a Spot)
| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/api/v1/ledger/adopt` | ✅ | Pledge to plant a tree |
| GET | `/api/v1/ledger/my-spots` | ✅ | My adopted spots |
| GET | `/api/v1/ledger/community` | Optional | Public community map |
| GET | `/api/v1/ledger/{spot_id}` | Optional | Single spot details |
| PATCH | `/api/v1/ledger/{spot_id}` | ✅ Owner | Update spot |
| DELETE | `/api/v1/ledger/{spot_id}` | ✅ Owner | Abandon spot |

### Verification Pipeline (Vertex AI)
| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/api/v1/verify-growth` | ✅ | Submit sapling photo for AI verification |

```bash
# multipart/form-data upload
curl -X POST https://api.pacha-cover.app/api/v1/verify-growth \
  -H "Authorization: Bearer <firebase-token>" \
  -F "spot_id=abc-123" \
  -F "image=@sapling.jpg"
```

### Users & Leaderboard
| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/api/v1/users/me` | ✅ | Create/sync profile |
| GET | `/api/v1/users/me` | ✅ | My profile + green stats |
| GET | `/api/v1/users/leaderboard` | Optional | City-wide rankings |

---

## 🌱 Green Points System

| Action | Points |
|--------|--------|
| Adopt a spot (pledge) | +10 |
| First sapling verification | +50 |
| Second verification (3 months) | +50 |
| Third verification (completed lifecycle) | +50 |

### Badges
| Points | Badge |
|--------|-------|
| 10 | 🌱 Sapling Starter |
| 50 | 🌿 Urban Gardener |
| 150 | 🌳 Tree Whisperer |
| 300 | 💚 Green Guardian |
| 500 | 🏆 Canopy Champion |
| 1000 | 🌲 Bengaluru's Forest Hero |

---

## ☁️ Cloud Deployment

### Deploy to Cloud Run

```bash
# Authenticate
gcloud auth login
gcloud config set project YOUR_PROJECT_ID

# Build and deploy via Cloud Build
gcloud builds submit --config cloudbuild.yaml

# Or deploy directly
gcloud run deploy pacha-cover-api \
  --source . \
  --region asia-south1 \
  --allow-unauthenticated
```

### Deploy Firebase Functions & Rules

```bash
npm install -g firebase-tools
firebase login
firebase deploy --only functions,firestore:rules,firestore:indexes
```

---

## 🧪 Running Tests

```bash
pytest tests/ -v --asyncio-mode=auto

# With coverage
pytest tests/ --cov=app --cov-report=html
```

---

## 🔑 Required GCP APIs

Enable these in your Google Cloud project:

```bash
gcloud services enable \
  run.googleapis.com \
  firestore.googleapis.com \
  storage.googleapis.com \
  aiplatform.googleapis.com \
  earthengine.googleapis.com \
  cloudbuild.googleapis.com \
  artifactregistry.googleapis.com \
  cloudscheduler.googleapis.com
```

---

## 🎯 Rotary Areas of Focus Alignment

| Feature | Rotary Focus |
|---------|-------------|
| Heat island identification | **Environment** — Ecosystem restoration |
| Native species prescription | **Environment** — Biodiversity |
| Community adoption | **Community Economic Development** |
| Green Points leaderboard | **Basic Education & Literacy** — Awareness |
| Citizen verification | **Community Economic Development** — Stewardship |

---

## 📊 Hackathon Judging Criteria Coverage

| Criterion | Implementation |
|-----------|----------------|
| **Innovation** | Gemini 1.5 Pro + GEE satellite fusion for hyperlocal prescriptions |
| **Impact** | 198-ward coverage, citizen gamification via Green Points |
| **Scalability** | Cloud Run autoscaling (1–20 instances), Firestore NoSQL, GEE batch API |
| **Google Tech** | Gemini, Vertex AI, Firestore, GEE, Cloud Run, Cloud Functions, GCS |
| **Completeness** | Full backend with auth, AI, storage, CI/CD, tests, and security rules |

---

*Built with 💚 for Bengaluru — India's Garden City*
