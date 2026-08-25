"""
Central configuration for the WILDLANDS Restoration Intelligence pipeline.

Everything that changes between environments (your real GEE project,
your real site list, your dashboard folder) lives here or in env vars —
never hardcoded inside the pipeline scripts themselves.
"""

import os
from pathlib import Path

# ----------------------------------------------------------------------
# Paths
# ----------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
REPORTS_DIR = BASE_DIR / "reports"
DASHBOARD_DIR = BASE_DIR / "dashboard"          # where index.html lives

for d in (DATA_DIR, REPORTS_DIR, DASHBOARD_DIR):
    d.mkdir(parents=True, exist_ok=True)

SITES_GPKG = DATA_DIR / "sites.gpkg"            # authoritative site registry
ESTIMATED_SITES_GPKG = DATA_DIR / "sites_estimated.gpkg"  # automated monitoring polygons
FIELD_SURVEY_CSV = DATA_DIR / "field_survey.csv"  # optional, from field teams
GEE_NDVI_CSV = DATA_DIR / "gee_ndvi_data.csv"
GEE_TRENDS_CSV = DATA_DIR / "gee_trends.csv"
DASHBOARD_JSON = DASHBOARD_DIR / "data.json"
QGIS_STYLE_QML = DATA_DIR / "site_status.qml"
REPORT_PDF = REPORTS_DIR / "restoration_report.pdf"
NDVI_IMAGES_DIR = DASHBOARD_DIR / "ndvi"
SITE_REPORTS_DIR = REPORTS_DIR / "sites"

NDVI_IMAGES_DIR.mkdir(parents=True, exist_ok=True)
SITE_REPORTS_DIR.mkdir(parents=True, exist_ok=True)

# ----------------------------------------------------------------------
# Google Earth Engine
# ----------------------------------------------------------------------
# Set this to your real GEE cloud project. Override with an env var so
# CI/scheduled runs don't need to touch code:
#   export GEE_PROJECT="my-real-project-id"
GEE_PROJECT = os.environ.get("GEE_PROJECT", "ee-sambanele860")

START_DATE = os.environ.get("GEE_START_DATE", "2025-08-01")
END_DATE = os.environ.get("GEE_END_DATE", "2026-08-23")
MAX_CLOUD_PCT = float(os.environ.get("GEE_MAX_CLOUD_PCT", 20))
BUFFER_METERS = float(os.environ.get("GEE_BUFFER_M", 500))
SCALE_METERS = float(os.environ.get("GEE_SCALE_M", 10))

# ----------------------------------------------------------------------
# Status thresholds (field/satellite blended health %, 0-100)
# ----------------------------------------------------------------------
CRITICAL_BELOW = 35
WARNING_BELOW = 60

# ----------------------------------------------------------------------
# Demo mode
# ----------------------------------------------------------------------
# If no sites.gpkg exists yet, sites_setup.py creates a demo one so the
# whole pipeline is runnable end-to-end before you have real data.
DEMO_SITE_COUNT = int(os.environ.get("DEMO_SITE_COUNT", 50))
