# ============================================================
# app/models/firestore_collections.py
#
# Canonical Firestore collection/document path constants.
# Centralising these prevents typos that cause silent failures
# (Firestore happily creates a new collection on misspelled names).
#
# Schema overview:
#
#   users/{uid}
#       display_name, email, total_green_points, ...
#
#   adopted_spots/{spot_id}
#       user_id, coordinates, status, species, ...
#
#   verifications/{verification_id}
#       spot_id, user_id, image_gcs_uri, status, ...
#
#   ward_heat_data/{ward_id}
#       avg_lst, avg_ndvi, heat_risk_score, ...
#
#   leaderboard/{uid}          ← written by Cloud Function
#       rank, total_green_points, display_name
# ============================================================


class Collections:
    USERS = "users"
    ADOPTED_SPOTS = "adopted_spots"
    VERIFICATIONS = "verifications"
    COMMUNITIES = "communities"
    WARD_HEAT_DATA = "ward_heat_data"
    LEADERBOARD = "leaderboard"
    # ── Feature 1: AR metadata (static catalogue, rarely written) ─────────────
    AR_MODELS = "ar_models"
    # ── Feature 2: Green Corridor clusters ────────────────────────────────────
    GREEN_CORRIDORS = "green_corridors"
    # ── Feature 3: Carbon simulations (optional audit log) ────────────────────
    CARBON_SIMULATIONS = "carbon_simulations"
    # ── Feature 4: Voice session logs (for analytics / replay) ────────────────
    VOICE_SESSIONS = "voice_sessions"


class FirestoreFields:
    """Field name constants to prevent magic-string bugs."""

    # ── users ──────────────────────────────────────────────────────────────────
    TOTAL_GREEN_POINTS = "total_green_points"
    TOTAL_TREES_ADOPTED = "total_trees_adopted"
    TOTAL_TREES_VERIFIED = "total_trees_verified"
    BADGES = "badges"

    # ── adopted_spots ──────────────────────────────────────────────────────────
    USER_ID = "user_id"
    STATUS = "status"
    VERIFICATION_COUNT = "verification_count"
    GREEN_POINTS_EARNED = "green_points_earned"
    IS_PUBLIC = "is_public"
    WARD_NAME = "ward_name"
    LAST_UPDATED = "last_updated"
    COORDINATES = "coordinates"          # GeoPoint — used for geospatial queries
    SPECIES_COMMON_NAME = "species_common_name"
    SPOT_NAME = "spot_name"

    # ── ward_heat_data ─────────────────────────────────────────────────────────
    HEAT_RISK_SCORE = "heat_risk_score"
    AVG_NDVI = "avg_ndvi"
    AVG_LAND_SURFACE_TEMP = "avg_land_surface_temp"
    ADOPTED_SPOTS_COUNT = "adopted_spots_count"
    # Feature 2: corridor status written back to the ward document
    CORRIDOR_STATUS = "corridor_status"
    CORRIDOR_ID = "corridor_id"

    # communities
    COMMUNITY_ID = "community_id"
    GOAL_TYPE = "goal_type"
    TARGET_VALUE = "target_value"
    CURRENT_VALUE = "current_value"
    MEMBERS = "members"
    GEOFENCE = "geofence"
    CENTER = "center"
    RADIUS_KM = "radius_km"

    # ── green_corridors ────────────────────────────────────────────────────────
    CENTRE_COORDINATES = "centre_coordinates"
    VERIFIED_TREE_COUNT = "verified_tree_count"
    CONTRIBUTOR_USER_IDS = "contributor_user_ids"
    DETECTED_AT = "detected_at"
    LAST_AUDITED = "last_audited"

    # ── ar_models ──────────────────────────────────────────────────────────────
    SPECIES_ID = "species_id"
    GLTF_URL = "gltf_url"
    THUMBNAIL_URL = "thumbnail_url"
    REAL_WORLD_SCALE = "real_world_scale_m"

    # ── carbon_simulations ─────────────────────────────────────────────────────
    SIMULATED_AT = "simulated_at"
    ANNUAL_CO2_KG = "annual_co2_kg_per_tree"
    REBATE_PERCENT = "rebate_percent"
