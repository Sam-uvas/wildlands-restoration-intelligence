"""
Build the browser-ready satellite dataset from the real GEE outputs.

This script intentionally fails if the GEE CSVs do not exist.
It never creates demo/synthetic satellite values.
"""
import json
from datetime import datetime, timezone

import geopandas as gpd
import pandas as pd

import WILDLANDS_satellite_config as config


def run():
    if not config.GEE_NDVI_CSV.exists():
        raise FileNotFoundError(
            f"{config.GEE_NDVI_CSV} does not exist. "
            "Run WILDLANDS_fetch_gee_production.py first."
        )

    if not config.GEE_TRENDS_CSV.exists():
        raise FileNotFoundError(
            f"{config.GEE_TRENDS_CSV} does not exist. "
            "Run WILDLANDS_fetch_gee_production.py first."
        )

    sites = gpd.read_file(config.SITES_GPKG).to_crs("EPSG:4326")
    ndvi = pd.read_csv(config.GEE_NDVI_CSV)
    trends = pd.read_csv(config.GEE_TRENDS_CSV)

    history = {}
    for site_id, group in ndvi.groupby("site_id"):
        group = group.sort_values("date")
        history[str(site_id)] = [
            {
                "date": str(row["date"]),
                "ndvi": round(float(row["NDVI"]), 4),
            }
            for _, row in group.iterrows()
        ]

    trend_lookup = {
        str(row["site_id"]): row.to_dict()
        for _, row in trends.iterrows()
    }

    records = []

    for _, site in sites.iterrows():
        site_id = str(site["site_id"])
        trend = trend_lookup.get(site_id, {})
        series = history.get(site_id, [])

        latest = series[-1]["ndvi"] if series else None
        change = trend.get("change_percent")

        if pd.notna(change):
            change = float(change) / 100.0
        else:
            change = None

        project_id = site.get("project_id")
        if pd.isna(project_id):
            project_id = None

        project_name = site.get("project_name")
        if pd.isna(project_name):
            project_name = None

        records.append(
            {
                "site_id": site_id,
                "site_name": (
                    str(site.get("site_name"))
                    if pd.notna(site.get("site_name"))
                    else site_id
                ),
                "project_id": (
                    str(project_id) if project_id is not None else None
                ),
                "project_name": (
                    str(project_name) if project_name is not None else None
                ),
                "latitude": round(float(site.geometry.centroid.y), 6),
                "longitude": round(float(site.geometry.centroid.x), 6),
                "latest_ndvi": latest,
                "avg_ndvi": trend.get("avg_ndvi"),
                "change": change,
                "change_percent": trend.get("change_percent"),
                "trend": trend.get("trend"),
                "improvement_rate": trend.get("improvement_rate"),
                "ndvi_history": series,
                "ndvi_image_url": f"ndvi/{site_id}.png",
                "source": "Sentinel-2 SR Harmonized via Google Earth Engine",
            }
        )

    payload = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "source": "Sentinel-2 SR Harmonized via Google Earth Engine",
        "start_date": config.START_DATE,
        "end_date": config.END_DATE,
        "cloud_threshold_percent": config.MAX_CLOUD_PCT,
        "scale_meters": config.SCALE_METERS,
        "sites": records,
    }

    config.SATELLITE_JSON.write_text(
        json.dumps(payload, indent=2, allow_nan=False),
        encoding="utf-8",
    )

    print(f"Wrote {len(records)} satellite records → {config.SATELLITE_JSON}")
    return payload


if __name__ == "__main__":
    run()
