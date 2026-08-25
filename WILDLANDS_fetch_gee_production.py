"""
WILDLANDS — production Sentinel-2 NDVI extraction.

Input:
    data/sites.gpkg
        Must contain site_id and point/polygon geometry.

Output:
    data/gee_ndvi_data.csv
    data/gee_trends.csv
    dashboard/frontend/ndvi/<site_id>.png

No synthetic/demo NDVI values are generated.
"""
import urllib.request
from pathlib import Path

import ee
import geopandas as gpd
import numpy as np
import pandas as pd

import WILDLANDS_satellite_config as config


def init_ee():
    try:
        ee.Initialize(project=config.GEE_PROJECT)
        print(f"Earth Engine initialized: {config.GEE_PROJECT}")
    except Exception as exc:
        raise RuntimeError(
            "Google Earth Engine could not be initialized. "
            "Run `earthengine authenticate` first and verify GEE_PROJECT.\n"
            f"Original error: {exc}"
        ) from exc


def load_sites():
    if not config.SITES_GPKG.exists():
        raise FileNotFoundError(
            f"Missing authoritative site registry: {config.SITES_GPKG}\n"
            "Create/import data/sites.gpkg before running the satellite pipeline."
        )

    gdf = gpd.read_file(config.SITES_GPKG)

    required = {"site_id"}
    missing = required - set(gdf.columns)
    if missing:
        raise ValueError(
            f"sites.gpkg is missing required field(s): {', '.join(sorted(missing))}"
        )

    if gdf.empty:
        raise ValueError("sites.gpkg contains no monitoring areas.")

    if gdf.crs is None:
        raise ValueError("sites.gpkg has no CRS. Define its CRS in QGIS first.")

    gdf = gdf.to_crs("EPSG:4326")
    gdf = gdf[gdf.geometry.notna() & ~gdf.geometry.is_empty].copy()

    if gdf.empty:
        raise ValueError("No valid geometries remain in sites.gpkg.")

    return gdf


def geometry_to_ee(geom):
    geojson = gpd.GeoSeries([geom], crs="EPSG:4326").__geo_interface__
    return ee.Geometry(geojson["features"][0]["geometry"])


def site_buffers(gdf):
    features = []

    for _, row in gdf.iterrows():
        geom = geometry_to_ee(row.geometry)
        # For points this creates the monitoring footprint directly.
        # For polygons it preserves the supplied monitoring geometry.
        if row.geometry.geom_type.lower() in {"polygon", "multipolygon"}:
            region = geom
        else:
            region = geom.buffer(config.BUFFER_METERS)

        features.append(
            ee.Feature(
                region,
                {
                    "site_id": str(row["site_id"]),
                },
            )
        )

    return ee.FeatureCollection(features)


def add_ndvi(image):
    ndvi = image.normalizedDifference(["B8", "B4"]).rename("NDVI")
    return image.addBands(ndvi)


def build_monthly_collection(buffers):
    sentinel = (
        ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
        .filterBounds(buffers)
        .filterDate(config.START_DATE, config.END_DATE)
        .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", config.MAX_CLOUD_PCT))
        .map(add_ndvi)
    )

    start = ee.Date(config.START_DATE)
    end = ee.Date(config.END_DATE)
    n_months = end.difference(start, "month").floor()

    offsets = ee.List.sequence(0, n_months.subtract(1))

    def composite(offset):
        month_start = start.advance(offset, "month")
        month_end = month_start.advance(1, "month")
        monthly = sentinel.filterDate(month_start, month_end)

        return (
            monthly.select("NDVI")
            .median()
            .rename("NDVI")
            .set("date", month_start.format("YYYY-MM"))
        )

    return ee.ImageCollection(offsets.map(composite))


def extract_monthly_ndvi(buffers, monthly):
    def reduce_month(image):
        image = ee.Image(image)
        reduced = image.reduceRegions(
            collection=buffers,
            reducer=ee.Reducer.mean(),
            scale=config.SCALE_METERS,
        )
        return reduced.map(
            lambda feature: feature.set("date", image.get("date"))
        )

    flattened = ee.FeatureCollection(
        monthly.map(reduce_month)
    ).flatten()

    info = flattened.getInfo()

    rows = []
    for feature in info.get("features", []):
        props = feature.get("properties", {})
        value = props.get("mean")

        if value is None:
            continue

        rows.append(
            {
                "site_id": str(props.get("site_id")),
                "date": str(props.get("date")),
                "NDVI": round(float(value), 4),
            }
        )

    df = pd.DataFrame(rows)

    if df.empty:
        raise RuntimeError(
            "Earth Engine returned no NDVI measurements. "
            "Check site locations, date range, cloud threshold and Sentinel-2 coverage."
        )

    return df.sort_values(["site_id", "date"])


def calculate_trends(df):
    rows = []

    for site_id, group in df.groupby("site_id"):
        group = group.sort_values("date")
        values = group["NDVI"].astype(float).to_numpy()

        latest = float(values[-1])
        average = float(values.mean())

        if len(values) < 3:
            rows.append(
                {
                    "site_id": site_id,
                    "trend": "Insufficient Data",
                    "improvement_rate": None,
                    "change_percent": None,
                    "latest_ndvi": round(latest, 4),
                    "avg_ndvi": round(average, 4),
                }
            )
            continue

        changes = np.diff(values)
        improvement_rate = float((changes > 0).sum()) / len(changes)

        first_avg = float(values[:3].mean())
        last_avg = float(values[-3:].mean())

        change_percent = (
            ((last_avg - first_avg) / abs(first_avg)) * 100
            if first_avg != 0
            else None
        )

        if improvement_rate >= config.IMPROVING_RATE:
            trend = "Improving"
        elif improvement_rate >= config.STABLE_RATE:
            trend = "Stable"
        else:
            trend = "Declining"

        rows.append(
            {
                "site_id": site_id,
                "trend": trend,
                "improvement_rate": round(improvement_rate * 100, 1),
                "change_percent": (
                    round(change_percent, 1)
                    if change_percent is not None
                    else None
                ),
                "latest_ndvi": round(latest, 4),
                "avg_ndvi": round(average, 4),
            }
        )

    return pd.DataFrame(rows)


def export_latest_images(gdf):
    collection = (
        ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
        .filterDate(config.START_DATE, config.END_DATE)
        .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", config.MAX_CLOUD_PCT))
        .sort("system:time_start", False)
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

    exported = 0

    for _, row in gdf.iterrows():
        site_id = str(row["site_id"])
        geometry = geometry_to_ee(row.geometry)

        if row.geometry.geom_type.lower() not in {"polygon", "multipolygon"}:
            geometry = geometry.buffer(config.BUFFER_METERS)

        site_collection = collection.filterBounds(geometry)

        if site_collection.size().getInfo() == 0:
            print(f"{site_id}: no Sentinel-2 scene — image skipped")
            continue

        latest = ee.Image(site_collection.first())
        latest_date = ee.Date(
            latest.get("system:time_start")
        ).format("YYYY-MM-dd").getInfo()

        ndvi = (
            latest.normalizedDifference(["B8", "B4"])
            .rename("NDVI")
            .clip(geometry)
        )

        url = ndvi.getThumbURL(
            {
                "region": geometry.bounds(),
                "dimensions": 900,
                "format": "png",
                "min": -0.2,
                "max": 0.8,
                "palette": palette,
            }
        )

        output = config.NDVI_IMAGES_DIR / f"{site_id}.png"
        urllib.request.urlretrieve(url, output)

        print(f"{site_id}: NDVI image saved — {latest_date}")
        exported += 1

    print(f"Saved {exported} site NDVI images.")


def run():
    init_ee()
    sites = load_sites()
    buffers = site_buffers(sites)

    print(f"Loaded {len(sites)} monitoring areas.")
    print(f"Date range: {config.START_DATE} → {config.END_DATE}")
    print(f"Cloud threshold: < {config.MAX_CLOUD_PCT}%")
    print(f"Spatial scale: {config.SCALE_METERS} m")

    monthly = build_monthly_collection(buffers)
    print(f"Monthly periods: {monthly.size().getInfo()}")

    ndvi = extract_monthly_ndvi(buffers, monthly)
    ndvi.to_csv(config.GEE_NDVI_CSV, index=False)
    print(f"Saved {len(ndvi)} NDVI records → {config.GEE_NDVI_CSV}")

    trends = calculate_trends(ndvi)
    trends.to_csv(config.GEE_TRENDS_CSV, index=False)
    print(f"Saved {len(trends)} trend records → {config.GEE_TRENDS_CSV}")

    export_latest_images(sites)

    return ndvi, trends


if __name__ == "__main__":
    run()
