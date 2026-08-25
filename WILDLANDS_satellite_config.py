"""
WILDLANDS — production satellite configuration.

This file contains only environment-specific settings for the Sentinel-2
NDVI pipeline. No demo/synthetic satellite values are generated.
"""
import os
from datetime import date
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DASHBOARD_DIR = BASE_DIR / "dashboard"
FRONTEND_DIR = DASHBOARD_DIR / "frontend"
NDVI_IMAGES_DIR = FRONTEND_DIR / "ndvi"

SITES_GPKG = DATA_DIR / "sites.gpkg"
GEE_NDVI_CSV = DATA_DIR / "gee_ndvi_data.csv"
GEE_TRENDS_CSV = DATA_DIR / "gee_trends.csv"
SATELLITE_JSON = FRONTEND_DIR / "satellite_data.json"

GEE_PROJECT = os.environ.get("GEE_PROJECT", "ee-sambanele860")
START_DATE = os.environ.get("GEE_START_DATE", "2023-01-01")
END_DATE = os.environ.get("GEE_END_DATE", date.today().isoformat())

MAX_CLOUD_PCT = float(os.environ.get("GEE_MAX_CLOUD_PCT", 20))
BUFFER_METERS = float(os.environ.get("GEE_BUFFER_M", 500))
SCALE_METERS = float(os.environ.get("GEE_SCALE_M", 10))

# Trend classification used by the dashboard.
IMPROVING_RATE = 0.60
STABLE_RATE = 0.40

DATA_DIR.mkdir(parents=True, exist_ok=True)
FRONTEND_DIR.mkdir(parents=True, exist_ok=True)
NDVI_IMAGES_DIR.mkdir(parents=True, exist_ok=True)
