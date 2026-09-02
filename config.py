"""
Central configuration for the WILDLANDS Restoration Intelligence pipeline.

Everything that changes between environments (your real GEE project,
your real site list, your dashboard folder) lives here or in environment
variables — never hardcoded inside the pipeline scripts themselves.
"""

import os
from datetime import date, timedelta
from pathlib import Path


# ----------------------------------------------------------------------
# Paths
# ----------------------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent

DATA_DIR = BASE_DIR / "data"
REPORTS_DIR = BASE_DIR / "reports"
DASHBOARD_DIR = BASE_DIR / "dashboard"  # where index.html lives

for d in (DATA_DIR, REPORTS_DIR, DASHBOARD_DIR):
    d.mkdir(parents=True, exist_ok=True)


SITES_GPKG = DATA_DIR / "sites.gpkg"
ESTIMATED_SITES_GPKG = DATA_DIR / "sites_estimated.gpkg"

FIELD_SURVEY_CSV = DATA_DIR / "field_survey.csv"

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

# Your real GEE Cloud project.
# Can be overridden with the GEE_PROJECT environment variable.

GEE_PROJECT = os.environ.get(
    "GEE_PROJECT",
    "ee-sambanele860",
)


# ----------------------------------------------------------------------
# Analysis dates
# ----------------------------------------------------------------------

# Keep the historical start date fixed so that your NDVI time series
# remains consistent between pipeline runs.

START_DATE = os.environ.get(
    "GEE_START_DATE",
    "2025-08-01",
)


# IMPORTANT:
#
# If GEE_END_DATE is explicitly supplied as an environment variable,
# use it.
#
# Otherwise, automatically search through tomorrow.
#
# Earth Engine filterDate() uses an EXCLUSIVE end date, so tomorrow
# allows the pipeline to include imagery acquired today.

DEFAULT_END_DATE = (
    date.today() + timedelta(days=1)
).isoformat()

END_DATE = os.environ.get(
    "GEE_END_DATE",
    DEFAULT_END_DATE,
)


# ----------------------------------------------------------------------
# Sentinel-2 quality settings
# ----------------------------------------------------------------------

# Maximum allowed scene-level cloud percentage.
#
# The pipeline will select the newest Sentinel-2 image that satisfies
# this threshold.

MAX_CLOUD_PCT = float(
    os.environ.get(
        "GEE_MAX_CLOUD_PCT",
        20,
    )
)


# ----------------------------------------------------------------------
# Monitoring geometry
# ----------------------------------------------------------------------

# Current monitoring buffer around each authoritative site.

BUFFER_METERS = float(
    os.environ.get(
        "GEE_BUFFER_M",
        500,
    )
)


# Sentinel-2 spatial resolution used for NDVI reduction.

SCALE_METERS = float(
    os.environ.get(
        "GEE_SCALE_M",
        10,
    )
)


# ----------------------------------------------------------------------
# Status thresholds
# ----------------------------------------------------------------------

# Field/satellite blended health percentage.

CRITICAL_BELOW = 35

WARNING_BELOW = 60


# ----------------------------------------------------------------------
# Demo mode
# ----------------------------------------------------------------------

# If no sites.gpkg exists yet, sites_setup.py creates a demo registry
# so the complete pipeline remains runnable before real site data exists.

DEMO_SITE_COUNT = int(
    os.environ.get(
        "DEMO_SITE_COUNT",
        50,
    )
)