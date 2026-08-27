"""
WILDLANDS — production Sentinel-2 NDVI extraction.

Bi-weekly Sentinel-2 NDVI pipeline.

Input:
    data/sites.gpkg
        Must contain site_id and point/polygon geometry.

Output:
    data/gee_ndvi_data.csv
    data/gee_trends.csv
    dashboard/frontend/ndvi/<site_id>.png

No synthetic/demo NDVI values are generated.
Weeks with no valid Sentinel-2 imagery are skipped.
"""

import urllib.request

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
            f"sites.gpkg is missing required field(s): "
            f"{', '.join(sorted(missing))}"
        )

    if gdf.empty:
        raise ValueError("sites.gpkg contains no monitoring areas.")

    if gdf.crs is None:
        raise ValueError(
            "sites.gpkg has no CRS. Define its CRS in QGIS first."
        )

    gdf = gdf.to_crs("EPSG:4326")
    gdf = gdf[
        gdf.geometry.notna() & ~gdf.geometry.is_empty
    ].copy()

    if gdf.empty:
        raise ValueError("No valid geometries remain in sites.gpkg.")

    return gdf


def geometry_to_ee(geom):
    geojson = gpd.GeoSeries(
        [geom], crs="EPSG:4326"
    ).__geo_interface__

    return ee.Geometry(
        geojson["features"][0]["geometry"]
    )


def site_buffers(gdf):
    features = []

    for _, row in gdf.iterrows():
        geom = geometry_to_ee(row.geometry)

        if row.geometry.geom_type.lower() in {
            "polygon",
            "multipolygon",
        }:
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
    ndvi = image.normalizedDifference(
        ["B8", "B4"]
    ).rename("NDVI")

    return image.addBands(ndvi)


def build_biweekly_ranges():
    """
    Build 14-day monitoring period start dates.

    The returned list may contain weeks with no imagery.
    Those empty weeks are explicitly skipped later rather than
    creating no-band Earth Engine images.
    """
    start = ee.Date(config.START_DATE)
    end = ee.Date(config.END_DATE)

    n_weeks = end.difference(
        start, "week"
    ).ceil()

    n_periods = end.difference(
        start, "day"
    ).divide(14).ceil()

    return ee.List.sequence(
        0,
        ee.Number(n_periods).subtract(1)
    ).map(
        lambda offset: start.advance(
            ee.Number(offset).multiply(14), "day"
        )
    )


def build_sentinel_collection(buffers):
    return (
        ee.ImageCollection(
            "COPERNICUS/S2_SR_HARMONIZED"
        )
        .filterBounds(buffers)
        .filterDate(
            config.START_DATE,
            config.END_DATE
        )
        .filter(
            ee.Filter.lt(
                "CLOUDY_PIXEL_PERCENTAGE",
                config.MAX_CLOUD_PCT,
            )
        )
        .map(add_ndvi)
    )


def extract_biweekly_ndvi(buffers):
    """
    Extract one median NDVI value per available 14-day period.

    Each period is evaluated independently. Periods with no valid
    Sentinel-2 imagery are skipped instead of creating empty images.
    This avoids Earth Engine's "Image has no bands" error and keeps
    the workload manageable.
    """

    sentinel = build_sentinel_collection(buffers)
    period_starts = build_biweekly_ranges()

    total_periods = period_starts.size().getInfo()
    all_rows = []

    print(
        f"Processing {total_periods} bi-weekly periods..."
    )

    for index in range(total_periods):
        period_start = ee.Date(
            period_starts.get(index)
        )
        period_end = period_start.advance(
            14, "day"
        )

        period_label = period_start.format(
            "YYYY-MM-dd"
        ).getInfo()

        period_collection = sentinel.filterDate(
            period_start,
            period_end
        )

        scene_count = period_collection.size().getInfo()

        if scene_count == 0:
            print(
                f"Period {index + 1}/{total_periods} "
                f"({period_label}): no Sentinel-2 scenes — skipped"
            )
            continue

        composite = (
            period_collection
            .select("NDVI")
            .median()
            .rename("NDVI")
        )

        reduced = composite.reduceRegions(
            collection=buffers,
            reducer=ee.Reducer.mean(),
            scale=config.SCALE_METERS,
        )

        info = reduced.getInfo()

        period_records = 0

        for feature in info.get("features", []):
            props = feature.get("properties", {})
            value = props.get("mean")
            site_id = props.get("site_id")

            if value is None or site_id is None:
                continue

            all_rows.append(
                {
                    "site_id": str(site_id),
                    "date": period_label,
                    "NDVI": round(float(value), 4),
                }
            )

            period_records += 1

        print(
            f"Period {index + 1}/{total_periods} "
            f"({period_label}): {scene_count} scene(s), "
            f"{period_records} site record(s)"
        )

    df = pd.DataFrame(all_rows)

    if df.empty:
        raise RuntimeError(
            "Earth Engine returned no bi-weekly NDVI measurements. "
            "Check site locations, date range, cloud threshold "
            "and Sentinel-2 coverage."
        )

    df["date"] = pd.to_datetime(
        df["date"],
        errors="coerce",
    )

    df = df.dropna(
        subset=["site_id", "date", "NDVI"]
    ).copy()

    df["date"] = df["date"].dt.strftime(
        "%Y-%m-%d"
    )

    df = (
        df.drop_duplicates(
            subset=["site_id", "date"]
        )
        .sort_values(["site_id", "date"])
        .reset_index(drop=True)
    )

    print(
        f"Bi-weekly extraction complete: "
        f"{len(df)} records"
    )

    return df


def calculate_trends(df):
    """
    Classify monitoring areas using bi-weekly NDVI change.

    The classification is based primarily on the magnitude of the
    change between the average NDVI of the first three available
    periods and the average NDVI of the last three available periods.

    Classification:
        change >= +10%  -> Improving
        change <= -10%  -> Declining
        otherwise       -> Stable

    improvement_rate is retained as supporting evidence and is the
    percentage of bi-weekly transitions where NDVI increased.

    This avoids labelling an area "Stable" merely because a fixed
    percentage of individual periods increased when the overall
    vegetation signal has materially declined.
    """

    rows = []

    for site_id, group in df.groupby("site_id", sort=True):
        group = group.copy()

        group["date"] = pd.to_datetime(
            group["date"],
            errors="coerce",
        )
        group["NDVI"] = pd.to_numeric(
            group["NDVI"],
            errors="coerce",
        )

        group = (
            group.dropna(subset=["date", "NDVI"])
            .sort_values("date")
        )

        values = group["NDVI"].to_numpy(dtype=float)

        if len(values) == 0:
            continue

        latest = float(values[-1])
        average = float(values.mean())

        if len(values) < 3:
            rows.append(
                {
                    "site_id": str(site_id),
                    "trend": "Insufficient Data",
                    "improvement_rate": None,
                    "change_percent": None,
                    "latest_ndvi": round(latest, 4),
                    "avg_ndvi": round(average, 4),
                }
            )
            continue

        changes = np.diff(values)

        improvement_rate = (
            float((changes > 0).sum()) / len(changes)
        )

        # Compare the beginning and end of the monitoring history
        # using three-period averages to reduce sensitivity to one
        # unusually high or low satellite observation.
        first_avg = float(values[:3].mean())
        last_avg = float(values[-3:].mean())

        if first_avg != 0:
            change_percent = (
                (last_avg - first_avg)
                / abs(first_avg)
            ) * 100
        else:
            change_percent = None

        if change_percent is None:
            trend = "Insufficient Data"
        elif change_percent >= config.TREND_CHANGE_THRESHOLD:
            trend = "Improving"
        elif change_percent <= -config.TREND_CHANGE_THRESHOLD:
            trend = "Declining"
        else:
            trend = "Stable"

        rows.append(
            {
                "site_id": str(site_id),
                "trend": trend,
                "improvement_rate": round(
                    improvement_rate * 100,
                    1,
                ),
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
        ee.ImageCollection(
            "COPERNICUS/S2_SR_HARMONIZED"
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

        geometry = geometry_to_ee(
            row.geometry
        )

        if row.geometry.geom_type.lower() not in {
            "polygon",
            "multipolygon",
        }:
            geometry = geometry.buffer(
                config.BUFFER_METERS
            )

        site_collection = collection.filterBounds(
            geometry
        )

        if (
            site_collection.size()
            .getInfo()
            == 0
        ):
            print(
                f"{site_id}: no Sentinel-2 scene "
                "— image skipped"
            )
            continue

        latest = ee.Image(
            site_collection.first()
        )

        latest_date = ee.Date(
            latest.get(
                "system:time_start"
            )
        ).format(
            "YYYY-MM-dd"
        ).getInfo()

        ndvi = (
            latest.normalizedDifference(
                ["B8", "B4"]
            )
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

        output = (
            config.NDVI_IMAGES_DIR
            / f"{site_id}.png"
        )

        urllib.request.urlretrieve(
            url,
            output,
        )

        print(
            f"{site_id}: NDVI image saved "
            f"— {latest_date}"
        )

        exported += 1

    print(
        f"Saved {exported} site NDVI images."
    )


def run():
    init_ee()

    sites = load_sites()
    buffers = site_buffers(sites)

    print(
        f"Loaded {len(sites)} monitoring areas."
    )

    print(
        f"Date range: {config.START_DATE} "
        f"→ {config.END_DATE}"
    )

    print(
        f"Cloud threshold: "
        f"< {config.MAX_CLOUD_PCT}%"
    )

    print(
        f"Spatial scale: "
        f"{config.SCALE_METERS} m"
    )

    biweekly_ranges = build_biweekly_ranges()

    print(
        f"Bi-weekly periods: "
        f"{biweekly_ranges.size().getInfo()}"
    )

    ndvi = extract_biweekly_ndvi(
        buffers
    )

    ndvi.to_csv(
        config.GEE_NDVI_CSV,
        index=False,
    )

    print(
        f"Saved {len(ndvi)} bi-weekly NDVI records "
        f"→ {config.GEE_NDVI_CSV}"
    )

    trends = calculate_trends(
        ndvi
    )

    if trends.empty:
        raise RuntimeError(
            "No trend records were produced "
            "from the bi-weekly NDVI dataset."
        )

    trends.to_csv(
        config.GEE_TRENDS_CSV,
        index=False,
    )

    print(
        f"Saved {len(trends)} trend records "
        f"→ {config.GEE_TRENDS_CSV}"
    )

    print("\nTrend summary:")

    print(
        trends[
            [
                "site_id",
                "trend",
                "improvement_rate",
                "change_percent",
                "latest_ndvi",
            ]
        ].to_string(index=False)
    )

    export_latest_images(
        sites
    )

    return ndvi, trends


if __name__ == "__main__":
    run()
