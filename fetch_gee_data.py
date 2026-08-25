"""
STAGE 1 — GEE NDVI extraction + latest Sentinel-2 NDVI image.

This version keeps the existing monthly site-level NDVI pipeline but also
creates a spatial PNG for the latest available monthly composite.
"""
from datetime import date, timedelta
import urllib.request

import ee
import geopandas as gpd
import numpy as np
import pandas as pd

import config
from sites_setup import ensure_sites


def init_ee():
    try:
        ee.Initialize(project=config.GEE_PROJECT)
        print(f"Earth Engine initialized (project={config.GEE_PROJECT})")
    except Exception as e:
        raise SystemExit(
            f"Earth Engine auth/init failed: {e}\n"
            "Run `earthengine authenticate` and set GEE_PROJECT."
        )


def sites_to_buffers(gdf: gpd.GeoDataFrame) -> ee.FeatureCollection:
    features = []
    for _, row in gdf.iterrows():
        pt = ee.Geometry.Point([row.geometry.x, row.geometry.y])
        features.append(ee.Feature(pt, {
            "site_id": row["site_id"],
            "site_name": row["site_name"],
        }))
    fc = ee.FeatureCollection(features)
    return fc.map(lambda f: f.buffer(config.BUFFER_METERS).copyProperties(f))


def add_ndvi(image):
    ndvi = image.normalizedDifference(["B8", "B4"]).rename("NDVI")
    return image.addBands(ndvi)


def build_monthly_composites(buffers):
    # Harmonized Sentinel-2 surface reflectance collection.
    sentinel2 = (
        ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
        .filterBounds(buffers)
        .filterDate(config.START_DATE, config.END_DATE)
        .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", config.MAX_CLOUD_PCT))
        .map(add_ndvi)
    )

    start = ee.Date(config.START_DATE)
    end = ee.Date(config.END_DATE)
    n_months = end.difference(start, "month").round()
    month_offsets = ee.List.sequence(0, n_months.subtract(1))

    def _composite(offset):
        month_start = start.advance(offset, "month")
        month_end = month_start.advance(1, "month")
        monthly = sentinel2.filterDate(month_start, month_end)
        # A masked median is acceptable when a month has no clear scenes;
        # extraction will skip sites whose mean is null.
        return (
            monthly.select("NDVI")
            .median()
            .rename("NDVI")
            .set({"date": month_start.format("YYYY-MM")})
        )

    return ee.ImageCollection(month_offsets.map(_composite))


def extract_ndvi_values(buffers, monthly_images):
    def _reduce_one_month(image):
        image = ee.Image(image)
        date_value = image.get("date")
        reduced = image.reduceRegions(
            collection=buffers,
            reducer=ee.Reducer.mean(),
            scale=config.SCALE_METERS,
        )
        return reduced.map(lambda f: f.set("date", date_value))

    flattened = ee.FeatureCollection(monthly_images.map(_reduce_one_month)).flatten()
    print("Pulling site × month NDVI records from Earth Engine...")
    info = flattened.getInfo()

    rows = []
    for feat in info["features"]:
        props = feat["properties"]
        ndvi = props.get("mean")
        if ndvi is None:
            continue
        rows.append({
            "site_id": props.get("site_id"),
            "date": props.get("date"),
            "NDVI": round(float(ndvi), 4),
        })
    return pd.DataFrame(rows)


def export_latest_ndvi_image(buffers):
    """
    Create the programme-wide latest NDVI image and one current NDVI image
    for every authoritative WILDLANDS site.

    Site geometry comes from data/sites.gpkg. Existing polygon boundaries
    are preserved. Point sites receive a configurable analysis buffer.
    """
    collection = (
        ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
        .filterBounds(buffers)
        .filterDate(config.START_DATE, config.END_DATE)
        .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", config.MAX_CLOUD_PCT))
        .sort("system:time_start", False)
    )

    count = collection.size().getInfo()
    if not count:
        print("WARNING: No Sentinel-2 scenes matched the current filters; NDVI images not created.")
        return None

    latest = ee.Image(collection.first())
    latest_date = ee.Date(
        latest.get("system:time_start")
    ).format("YYYY-MM-dd").getInfo()
    ndvi = latest.normalizedDifference(["B8", "B4"]).rename("NDVI")

    palette = [
        "#8c510a", "#d8b365", "#f6e8c3", "#f5f5f5",
        "#c7eae5", "#5ab4ac", "#01665e",
    ]

    # Keep the programme-wide image for the overview report.
    region = buffers.geometry().bounds()
    params = {
        "region": region,
        "dimensions": 1600,
        "format": "png",
        "min": -0.2,
        "max": 0.8,
        "palette": palette,
    }
    url = ndvi.getThumbURL(params)
    output = config.DATA_DIR / "latest_ndvi.png"
    urllib.request.urlretrieve(url, output)
    (config.DATA_DIR / "latest_ndvi_date.txt").write_text(
        str(latest_date), encoding="utf-8"
    )

    # Use the ACTUAL WILDLANDS site registry as the authoritative spatial source.
    # Do not use sites_estimated.gpkg for the site-specific NDVI rasters.
    site_gdf = gpd.read_file(config.SITES_GPKG).to_crs("EPSG:4326")
    print(f"Using AUTHORITATIVE WILDLANDS sites from {config.SITES_GPKG}")

    # The registry may contain points or polygons.
    # If a site is a point, create a small analysis area around that point.
    # If it is already a polygon, preserve the actual polygon geometry.
    if site_gdf.empty:
        raise RuntimeError(f"No sites found in {config.SITES_GPKG}")

    for idx, row in site_gdf.iterrows():
        geom = row.geometry
        if geom is None or geom.is_empty:
            continue
        if geom.geom_type == "Point":
            site_gdf.at[idx, "geometry"] = geom.buffer(
                config.BUFFER_METERS / 111320.0
            )

    config.NDVI_IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    date_rows = []

    for _, row in site_gdf.iterrows():
        site_id = str(row["site_id"])
        geom = row.geometry

        if geom is None or geom.is_empty:
            print(f"  {site_id}: EMPTY GEOMETRY — skipped")
            continue

        # Convert the polygon to an Earth Engine geometry.
        geom_json = gpd.GeoSeries(
            [geom], crs="EPSG:4326"
        ).__geo_interface__["features"][0]["geometry"]
        site_geometry = ee.Geometry(geom_json)

        # Find the most recent Sentinel-2 scene intersecting THIS site.
        site_collection = (
            ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
            .filterBounds(site_geometry)
            .filterDate(config.START_DATE, config.END_DATE)
            .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", config.MAX_CLOUD_PCT))
            .sort("system:time_start", False)
        )

        site_count = site_collection.size().getInfo()
        if not site_count:
            print(f"  {site_id}: no Sentinel-2 scene — skipped")
            continue

        site_latest = ee.Image(site_collection.first())
        site_date = ee.Date(
            site_latest.get("system:time_start")
        ).format("YYYY-MM-dd").getInfo()

        site_ndvi = (
            site_latest.normalizedDifference(["B8", "B4"])
            .rename("NDVI")
            .clip(site_geometry)
        )

        site_params = {
            "region": site_geometry.bounds(),
            "dimensions": 900,
            "format": "png",
            "min": -0.2,
            "max": 0.8,
            "palette": palette,
        }

        site_url = site_ndvi.getThumbURL(site_params)
        site_output = config.NDVI_IMAGES_DIR / f"{site_id}.png"
        urllib.request.urlretrieve(site_url, site_output)

        date_rows.append({
            "site_id": site_id,
            "date": site_date,
            "ndvi_image_date": site_date,
            "boundary_type": row.get(
                "boundary_type",
                "Estimated monitoring area"
            ),
        })

        print(
            f"  {site_id}: polygon NDVI saved | "
            f"date={site_date} | area={row.get('area_hectares', 'n/a')} ha"
        )

    pd.DataFrame(date_rows).to_csv(
        config.DATA_DIR / "site_ndvi_dates.csv",
        index=False
    )
    print(
        f"Saved latest Sentinel-2 NDVI image ({latest_date}) to {output}"
    )
    print(
        f"Saved {len(date_rows)} polygon-specific site NDVI images "
        f"to {config.NDVI_IMAGES_DIR}"
    )
    return latest_date

def calculate_trends(df):
    trends = []
    for site_id, site_data in df.groupby("site_id"):
        site_data = site_data.sort_values("date")
        values = site_data["NDVI"].values

        if len(values) < 3:
            trends.append({
                "site_id": site_id,
                "trend": "Insufficient Data",
                "improvement_rate": 0,
                "change_percent": 0,
                "latest_ndvi": values[-1] if len(values) else None,
                "avg_ndvi": values.mean() if len(values) else None,
            })
            continue

        changes = np.diff(values)
        improvement_rate = float((changes > 0).sum()) / len(changes)
        first_avg = values[:3].mean()
        last_avg = values[-3:].mean()
        change_percent = ((last_avg - first_avg) / first_avg * 100) if first_avg > 0 else 0

        if improvement_rate >= 0.6:
            trend = "Improving"
        elif improvement_rate >= 0.4:
            trend = "Stable"
        else:
            trend = "Declining"

        trends.append({
            "site_id": site_id,
            "trend": trend,
            "improvement_rate": round(improvement_rate * 100, 1),
            "change_percent": round(change_percent, 1),
            "latest_ndvi": round(float(values[-1]), 4),
            "avg_ndvi": round(float(values.mean()), 4),
        })
    return pd.DataFrame(trends)


def run():
    init_ee()
    gdf = ensure_sites()
    buffers = sites_to_buffers(gdf)
    print(f"Loaded {buffers.size().getInfo()} sites with buffers")

    monthly_images = build_monthly_composites(buffers)
    print(f"Generated {monthly_images.size().getInfo()} monthly composite periods")

    ndvi_df = extract_ndvi_values(buffers, monthly_images)
    ndvi_df.to_csv(config.GEE_NDVI_CSV, index=False)
    print(f"Saved {len(ndvi_df)} records to {config.GEE_NDVI_CSV}")

    export_latest_ndvi_image(buffers)

    trend_df = calculate_trends(ndvi_df)
    trend_df.to_csv(config.GEE_TRENDS_CSV, index=False)
    print(f"Saved trends for {len(trend_df)} sites to {config.GEE_TRENDS_CSV}")
    return ndvi_df, trend_df

if __name__ == "__main__":
    run()