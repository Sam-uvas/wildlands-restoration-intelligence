"""
STAGE 1 — GEE NDVI extraction + latest Sentinel-2 NDVI imagery.

GitHub Actions compatible:
- Uses a Google Earth Engine service account.
- Does NOT use ee.Authenticate().
- Does NOT require an interactive login.
- Uses GOOGLE_APPLICATION_CREDENTIALS /
  GOOGLE_APPLICATION_CREDENTIALS as provided by GitHub Actions.
- Produces monthly site-level NDVI.
- Produces programme-wide latest NDVI PNG.
- Produces current NDVI PNG for each WILDLANDS site.
"""

from datetime import date, timedelta
import json
import os
import urllib.request

import ee
import geopandas as gpd
import numpy as np
import pandas as pd

import config
from sites_setup import ensure_sites


# ============================================================
# EARTH ENGINE INITIALIZATION
# ============================================================

def init_ee():
    """
    Initialize Google Earth Engine non-interactively using
    a Google service-account JSON key.

    IMPORTANT:
    This function deliberately does NOT call:
        ee.Authenticate()

    GitHub Actions cannot perform interactive authentication.
    """

    credentials_path = os.environ.get(
        "GOOGLE_APPLICATION_CREDENTIALS"
    )

    project = os.environ.get(
        "GEE_PROJECT"
    )

    # --------------------------------------------------------
    # Validate environment
    # --------------------------------------------------------

    if not credentials_path:
        raise RuntimeError(
            "GOOGLE_APPLICATION_CREDENTIALS is not set."
        )

    if not project:
        raise RuntimeError(
            "GEE_PROJECT is not set."
        )

    if not os.path.isfile(credentials_path):
        raise RuntimeError(
            "Earth Engine credentials file does not exist: "
            f"{credentials_path}"
        )

    # --------------------------------------------------------
    # Read service-account JSON
    # --------------------------------------------------------

    try:
        with open(
            credentials_path,
            "r",
            encoding="utf-8",
        ) as f:
            key_data = json.load(f)

    except Exception as exc:
        raise RuntimeError(
            "Unable to read Earth Engine service-account "
            "credentials JSON."
        ) from exc

    # --------------------------------------------------------
    # Validate required fields
    # --------------------------------------------------------

    required_fields = [
        "type",
        "project_id",
        "private_key",
        "client_email",
    ]

    missing = [
        field
        for field in required_fields
        if not key_data.get(field)
    ]

    if missing:
        raise RuntimeError(
            "Invalid Earth Engine service-account JSON. "
            "Missing fields: "
            + ", ".join(missing)
        )

    if key_data.get("type") != "service_account":
        raise RuntimeError(
            "The supplied GEE credentials are not a "
            "service-account JSON key."
        )

    # --------------------------------------------------------
    # Authenticate with Google service-account credentials
    # --------------------------------------------------------

    try:
        from google.oauth2 import service_account

        credentials = (
            service_account.Credentials.from_service_account_file(
                credentials_path,
                scopes=[
                    "https://www.googleapis.com/auth/earthengine",
                    "https://www.googleapis.com/auth/cloud-platform",
                ],
            )
        )

    except Exception as exc:
        raise RuntimeError(
            "Could not create Google service-account "
            "credentials."
        ) from exc

    # --------------------------------------------------------
    # Initialize Earth Engine
    # --------------------------------------------------------

    try:
        ee.Initialize(
            credentials=credentials,
            project=project,
        )

    except Exception as exc:
        raise RuntimeError(
            "Earth Engine initialization failed. "
            f"Project: {project}. "
            f"Service account: "
            f"{key_data.get('client_email')}. "
            f"Error: {exc}"
        ) from exc

    # --------------------------------------------------------
    # Force an actual Earth Engine API request
    # --------------------------------------------------------

    try:
        test_value = ee.Number(1).getInfo()

    except Exception as exc:
        raise RuntimeError(
            "Earth Engine authentication succeeded locally, "
            "but the service account cannot access the "
            "Earth Engine API. "
            f"Project: {project}. "
            f"Service account: "
            f"{key_data.get('client_email')}. "
            f"Error: {exc}"
        ) from exc

    # --------------------------------------------------------
    # Success
    # --------------------------------------------------------

    print(
        "Earth Engine initialized successfully."
    )

    print(
        f"Earth Engine project: {project}"
    )

    print(
        "Service account: "
        f"{key_data['client_email']}"
    )

    print(
        f"Earth Engine API test result: {test_value}"
    )

    print(
        "Earth Engine authentication: OK"
    )


# ============================================================
# SITE GEOMETRY
# ============================================================

def sites_to_buffers(
    gdf: gpd.GeoDataFrame,
) -> ee.FeatureCollection:

    features = []

    for _, row in gdf.iterrows():

        geometry = row.geometry

        if geometry is None or geometry.is_empty:
            continue

        # ----------------------------------------------------
        # Convert geometry to point
        # ----------------------------------------------------

        if geometry.geom_type == "Point":

            coordinates = [
                geometry.x,
                geometry.y,
            ]

            point = ee.Geometry.Point(
                coordinates
            )

            feature = ee.Feature(
                point,
                {
                    "site_id": str(
                        row["site_id"]
                    ),
                    "site_name": str(
                        row["site_name"]
                    ),
                },
            )

            features.append(feature)

        else:

            # For polygon geometries use the geometry
            # directly.

            geometry_json = (
                gpd.GeoSeries(
                    [geometry],
                    crs=gdf.crs,
                )
                .__geo_interface__["features"][0]["geometry"]
            )

            feature = ee.Feature(
                ee.Geometry(geometry_json),
                {
                    "site_id": str(
                        row["site_id"]
                    ),
                    "site_name": str(
                        row["site_name"]
                    ),
                },
            )

            features.append(feature)

    if not features:
        raise RuntimeError(
            "No valid site geometries were found."
        )

    fc = ee.FeatureCollection(
        features
    )

    return fc.map(
        lambda feature: feature.buffer(
            config.BUFFER_METERS
        ).copyProperties(feature)
    )


# ============================================================
# NDVI
# ============================================================

def add_ndvi(image):

    ndvi = (
        image
        .normalizedDifference(
            ["B8", "B4"]
        )
        .rename("NDVI")
    )

    return image.addBands(ndvi)


# ============================================================
# SENTINEL-2 COLLECTION
# ============================================================

def get_sentinel_collection(
    geometry,
):

    return (
        ee.ImageCollection(
            "COPERNICUS/S2_SR_HARMONIZED"
        )
        .filterBounds(geometry)
        .filterDate(
            config.START_DATE,
            config.END_DATE,
        )
        .filter(
            ee.Filter.lt(
                "CLOUDY_PIXEL_PERCENTAGE",
                config.MAX_CLOUD_PCT,
            )
        )
    )


# ============================================================
# MONTHLY COMPOSITES
# ============================================================

def build_monthly_composites(
    buffers,
):

    sentinel2 = (
        get_sentinel_collection(
            buffers
        )
        .map(add_ndvi)
    )

    start = ee.Date(
        config.START_DATE
    )

    end = ee.Date(
        config.END_DATE
    )

    n_months = (
        end
        .difference(
            start,
            "month",
        )
        .round()
    )

    month_offsets = ee.List.sequence(
        0,
        n_months.subtract(1),
    )

    def composite(offset):

        month_start = start.advance(
            offset,
            "month",
        )

        month_end = month_start.advance(
            1,
            "month",
        )

        monthly = (
            sentinel2
            .filterDate(
                month_start,
                month_end,
            )
        )

        return (
            monthly
            .select("NDVI")
            .median()
            .rename("NDVI")
            .set(
                "date",
                month_start.format(
                    "YYYY-MM"
                ),
            )
        )

    return ee.ImageCollection(
        month_offsets.map(
            composite
        )
    )


# ============================================================
# EXTRACT NDVI VALUES
# ============================================================

def extract_ndvi_values(
    buffers,
    monthly_images,
):

    def reduce_one_month(image):

        image = ee.Image(
            image
        )

        date_value = image.get(
            "date"
        )

        reduced = image.reduceRegions(
            collection=buffers,
            reducer=ee.Reducer.mean(),
            scale=config.SCALE_METERS,
        )

        return reduced.map(
            lambda feature: feature.set(
                "date",
                date_value,
            )
        )

    flattened = (
        ee.FeatureCollection(
            monthly_images.map(
                reduce_one_month
            )
        )
        .flatten()
    )

    print(
        "Pulling site × month NDVI records "
        "from Earth Engine..."
    )

    info = flattened.getInfo()

    rows = []

    for feature in info.get(
        "features",
        [],
    ):

        properties = feature.get(
            "properties",
            {},
        )

        ndvi = properties.get(
            "mean"
        )

        if ndvi is None:
            continue

        rows.append(
            {
                "site_id": properties.get(
                    "site_id"
                ),
                "date": properties.get(
                    "date"
                ),
                "NDVI": round(
                    float(ndvi),
                    4,
                ),
            }
        )

    return pd.DataFrame(
        rows
    )


# ============================================================
# LATEST NDVI IMAGE
# ============================================================

def export_latest_ndvi_image(
    buffers,
):

    """
    Create:

    1. Programme-wide latest NDVI image.
    2. Current NDVI image for every WILDLANDS site.
    """

    collection = (
        ee.ImageCollection(
            "COPERNICUS/S2_SR_HARMONIZED"
        )
        .filterBounds(buffers)
        .filterDate(
            config.START_DATE,
            config.END_DATE,
        )
        .filter(
            ee.Filter.lt(
                "CLOUDY_PIXEL_PERCENTAGE",
                config.MAX_CLOUD_PCT,
            )
        )
        .sort(
            "system:time_start",
            False,
        )
    )

    count = (
        collection
        .size()
        .getInfo()
    )

    if not count:

        print(
            "WARNING: No Sentinel-2 scenes "
            "matched the current filters."
        )

        return None

    latest = ee.Image(
        collection.first()
    )

    latest_date = (
        ee.Date(
            latest.get(
                "system:time_start"
            )
        )
        .format(
            "YYYY-MM-dd"
        )
        .getInfo()
    )

    ndvi = (
        latest
        .normalizedDifference(
            ["B8", "B4"]
        )
        .rename("NDVI")
    )

    palette = [
        "#8c510a",
        "#d8b365",
        "#f6e8c3",
        "#f5f5f5",
        "#c7eae5",
        "#5ab4ac",
        "#01665e",
    ]

    # --------------------------------------------------------
    # PROGRAMME-WIDE IMAGE
    # --------------------------------------------------------

    region = (
        buffers
        .geometry()
        .bounds()
    )

    params = {
        "region": region,
        "dimensions": 1600,
        "format": "png",
        "min": -0.2,
        "max": 0.8,
        "palette": palette,
    }

    url = ndvi.getThumbURL(
        params
    )

    output = (
        config.DATA_DIR
        / "latest_ndvi.png"
    )

    urllib.request.urlretrieve(
        url,
        output,
    )

    date_file = (
        config.DATA_DIR
        / "latest_ndvi_date.txt"
    )

    date_file.write_text(
        str(latest_date),
        encoding="utf-8",
    )

    # --------------------------------------------------------
    # AUTHORITATIVE SITE REGISTRY
    # --------------------------------------------------------

    site_gdf = (
        gpd.read_file(
            config.SITES_GPKG
        )
        .to_crs("EPSG:4326")
    )

    print(
        "Using AUTHORITATIVE WILDLANDS sites from "
        f"{config.SITES_GPKG}"
    )

    if site_gdf.empty:

        raise RuntimeError(
            f"No sites found in "
            f"{config.SITES_GPKG}"
        )

    # --------------------------------------------------------
    # PREPARE SITE GEOMETRIES
    # --------------------------------------------------------

    config.NDVI_IMAGES_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    date_rows = []

    # --------------------------------------------------------
    # SITE-BY-SITE NDVI
    # --------------------------------------------------------

    for _, row in site_gdf.iterrows():

        site_id = str(
            row["site_id"]
        )

        geometry = row.geometry

        if (
            geometry is None
            or geometry.is_empty
        ):

            print(
                f"{site_id}: EMPTY GEOMETRY — skipped"
            )

            continue

        # ----------------------------------------------------
        # Convert geometry to GeoJSON
        # ----------------------------------------------------

        geometry_json = (
            gpd.GeoSeries(
                [geometry],
                crs=site_gdf.crs,
            )
            .__geo_interface__["features"][0]["geometry"]
        )

        site_geometry = ee.Geometry(
            geometry_json
        )

        # ----------------------------------------------------
        # Site Sentinel-2 collection
        # ----------------------------------------------------

        site_collection = (
            ee.ImageCollection(
                "COPERNICUS/S2_SR_HARMONIZED"
            )
            .filterBounds(
                site_geometry
            )
            .filterDate(
                config.START_DATE,
                config.END_DATE,
            )
            .filter(
                ee.Filter.lt(
                    "CLOUDY_PIXEL_PERCENTAGE",
                    config.MAX_CLOUD_PCT,
                )
            )
            .sort(
                "system:time_start",
                False,
            )
        )

        site_count = (
            site_collection
            .size()
            .getInfo()
        )

        if not site_count:

            print(
                f"{site_id}: "
                "no Sentinel-2 scene — skipped"
            )

            continue

        # ----------------------------------------------------
        # Latest site image
        # ----------------------------------------------------

        site_latest = ee.Image(
            site_collection.first()
        )

        site_date = (
            ee.Date(
                site_latest.get(
                    "system:time_start"
                )
            )
            .format(
                "YYYY-MM-dd"
            )
            .getInfo()
        )

        # ----------------------------------------------------
        # Site NDVI
        # ----------------------------------------------------
        site_ndvi = (
            site_latest
            .normalizedDifference(
                ["B8", "B4"]
            )
            .rename("NDVI")
        )

        # Use the site geometry only as the thumbnail region.
        # Do NOT clip the image before getThumbURL().
        site_params = {
            "region": site_geometry.bounds(1),
            "dimensions": 900,
            "format": "png",
            "min": -0.2,
            "max": 0.8,
            "palette": palette,
        }

        site_url = site_ndvi.getThumbURL(site_params)

        site_output = (
            config.NDVI_IMAGES_DIR
            / f"{site_id}.png"
        )

        urllib.request.urlretrieve(
            site_url,
            site_output,
        )

        date_rows.append(
            {
                "site_id": site_id,
                "date": site_date,
                "ndvi_image_date": site_date,
                "boundary_type": row.get(
                    "boundary_type",
                    "Estimated monitoring area",
                ),
            }
        )

        print(
            f"{site_id}: NDVI saved | "
            f"date={site_date} | "
            f"area={row.get('area_hectares', 'n/a')} ha"
        )

    # --------------------------------------------------------
    # SAVE SITE NDVI DATES
    # --------------------------------------------------------

    pd.DataFrame(
        date_rows
    ).to_csv(
        config.DATA_DIR
        / "site_ndvi_dates.csv",
        index=False,
    )

    print(
        "Saved latest Sentinel-2 NDVI image "
        f"({latest_date}) to {output}"
    )

    print(
        f"Saved {len(date_rows)} "
        "site NDVI images to "
        f"{config.NDVI_IMAGES_DIR}"
    )

    return latest_date


# ============================================================
# TREND CALCULATION
# ============================================================

def calculate_trends(
    df,
):

    trends = []

    for site_id, site_data in df.groupby(
        "site_id"
    ):

        site_data = (
            site_data
            .sort_values(
                "date"
            )
        )

        values = (
            site_data["NDVI"]
            .astype(float)
            .values
        )

        # ----------------------------------------------------
        # Insufficient data
        # ----------------------------------------------------

        if len(values) < 3:

            trends.append(
                {
                    "site_id": site_id,
                    "trend": "Insufficient Data",
                    "improvement_rate": 0,
                    "change_percent": 0,
                    "latest_ndvi": (
                        values[-1]
                        if len(values)
                        else None
                    ),
                    "avg_ndvi": (
                        values.mean()
                        if len(values)
                        else None
                    ),
                }
            )

            continue

        # ----------------------------------------------------
        # Month-to-month changes
        # ----------------------------------------------------

        changes = np.diff(
            values
        )

        improvement_rate = (
            float(
                (changes > 0).sum()
            )
            / len(changes)
        )

        # ----------------------------------------------------
        # First three vs last three
        # ----------------------------------------------------

        first_avg = (
            values[:3].mean()
        )

        last_avg = (
            values[-3:].mean()
        )

        if first_avg > 0:

            change_percent = (
                (
                    (
                        last_avg
                        - first_avg
                    )
                    / first_avg
                )
                * 100
            )

        else:

            change_percent = 0

        # ----------------------------------------------------
        # Classification
        # ----------------------------------------------------

        if improvement_rate >= 0.6:

            trend = "Improving"

        elif improvement_rate >= 0.4:

            trend = "Stable"

        else:

            trend = "Declining"

        trends.append(
            {
                "site_id": site_id,
                "trend": trend,
                "improvement_rate": round(
                    improvement_rate * 100,
                    1,
                ),
                "change_percent": round(
                    change_percent,
                    1,
                ),
                "latest_ndvi": round(
                    float(values[-1]),
                    4,
                ),
                "avg_ndvi": round(
                    float(values.mean()),
                    4,
                ),
            }
        )

    return pd.DataFrame(
        trends
    )


# ============================================================
# MAIN GEE STAGE
# ============================================================

def run():

    print(
        "--- Initializing Earth Engine ---"
    )

    init_ee()

    print(
        "--- Loading WILDLANDS sites ---"
    )

    gdf = ensure_sites()

    if gdf.empty:

        raise RuntimeError(
            "The WILDLANDS site registry is empty."
        )

    buffers = sites_to_buffers(
        gdf
    )

    site_count = (
        buffers
        .size()
        .getInfo()
    )

    print(
        f"Loaded {site_count} "
        "sites with buffers"
    )

    # --------------------------------------------------------
    # MONTHLY NDVI
    # --------------------------------------------------------

    print(
        "--- Building monthly NDVI composites ---"
    )

    monthly_images = (
        build_monthly_composites(
            buffers
        )
    )

    monthly_count = (
        monthly_images
        .size()
        .getInfo()
    )

    print(
        f"Generated {monthly_count} "
        "monthly composite periods"
    )

    # --------------------------------------------------------
    # EXTRACT NDVI
    # --------------------------------------------------------

    ndvi_df = extract_ndvi_values(
        buffers,
        monthly_images,
    )

    if ndvi_df.empty:

        raise RuntimeError(
            "No NDVI records were returned "
            "from Earth Engine."
        )

    ndvi_df.to_csv(
        config.GEE_NDVI_CSV,
        index=False,
    )

    print(
        f"Saved {len(ndvi_df)} "
        "NDVI records to "
        f"{config.GEE_NDVI_CSV}"
    )

    # --------------------------------------------------------
    # LATEST IMAGERY
    # --------------------------------------------------------

    print(
        "--- Exporting latest NDVI imagery ---"
    )

    export_latest_ndvi_image(
        buffers
    )

    # --------------------------------------------------------
    # TRENDS
    # --------------------------------------------------------

    print(
        "--- Calculating NDVI trends ---"
    )

    trend_df = calculate_trends(
        ndvi_df
    )

    trend_df.to_csv(
        config.GEE_TRENDS_CSV,
        index=False,
    )

    print(
        f"Saved trends for "
        f"{len(trend_df)} sites to "
        f"{config.GEE_TRENDS_CSV}"
    )

    print(
        "--- GEE STAGE COMPLETE ---"
    )

    return (
        ndvi_df,
        trend_df,
    )


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":

    run()