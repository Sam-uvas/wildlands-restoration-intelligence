"""
STAGE 2 — MERGE INTO DASHBOARD data.json
==========================================
Combines:
  - data/sites.gpkg          (static attributes: area, type, funding...)
  - data/gee_trends.csv      (satellite NDVI trend, from fetch_gee_data.py)
  - data/field_survey.csv    (optional: field-measured vegetation_health,
                               one row per site_id — plug in your field
                               team's data collection form/app export here)

...into the exact schema dashboard/data.json needs, so index.html keeps
working unmodified. If field_survey.csv is missing, field health is
simulated from the satellite NDVI trend so the pipeline is runnable
end-to-end in demo mode.
"""

import json
from datetime import datetime, timezone

import geopandas as gpd
import numpy as np
import pandas as pd

import config


def load_ndvi_history(site_ids):
    """Per-site monthly NDVI series, for the map click-to-inspect chart.
    Returns {site_id: [{"date": "2023-01", "ndvi": 0.42}, ...]}."""
    if config.GEE_NDVI_CSV.exists():
        raw = pd.read_csv(config.GEE_NDVI_CSV)
        history = {}
        for site_id, rows in raw.groupby("site_id"):
            rows = rows.sort_values("date")
            history[site_id] = [
                {"date": d, "ndvi": round(float(v), 4)}
                for d, v in zip(rows["date"], rows["NDVI"])
            ]
        return history

    # Demo fallback: synthesize a plausible 24-month NDVI series per site
    # so the click-chart has something to show before a real GEE run.
    rng = np.random.default_rng(11)
    history = {}
    months = pd.period_range("2024-01", periods=24, freq="M")
    for sid in site_ids:
        base = rng.uniform(0.3, 0.6)
        drift = rng.uniform(-0.004, 0.006)
        noise = rng.normal(0, 0.02, size=len(months))
        series = np.clip(base + drift * np.arange(len(months)) + noise, 0.1, 0.9)
        history[sid] = [
            {"date": str(m), "ndvi": round(float(v), 4)}
            for m, v in zip(months, series)
        ]
    return history


def load_field_survey(site_ids):
    if config.FIELD_SURVEY_CSV.exists():
        return pd.read_csv(config.FIELD_SURVEY_CSV)
    # Demo fallback: simulate plausible field health so the dashboard
    # has something to show before real field data is wired in.
    rng = np.random.default_rng(7)
    return pd.DataFrame({
        "site_id": site_ids,
        "vegetation_health": rng.integers(25, 95, size=len(site_ids)),
    })


def ndvi_to_health_pct(avg_ndvi):
    # NDVI ~0.2 (bare/degraded) -> 0%,  NDVI ~0.8 (dense healthy veg) -> 100%
    if pd.isna(avg_ndvi):
        return None
    pct = (avg_ndvi - 0.2) / (0.8 - 0.2) * 100
    return round(min(max(pct, 0), 100), 1)


def compute_status(health):
    if health is None:
        return "warning"
    if health < config.CRITICAL_BELOW:
        return "critical"
    if health < config.WARNING_BELOW:
        return "warning"
    return "good"


def prediction_for(trend):
    return {
        "Improving": "On track",
        "Declining": "Needs intervention",
        "Stable": "Monitor closely",
    }.get(trend, "Monitor closely")


def run():
    sites = gpd.read_file(config.SITES_GPKG)
    sites["latitude"] = sites.geometry.y
    sites["longitude"] = sites.geometry.x

    if config.GEE_TRENDS_CSV.exists():
        trends = pd.read_csv(config.GEE_TRENDS_CSV)
        data_source = "Field monitoring + Sentinel-2 satellite (GEE)"
    else:
        print(f"WARNING: {config.GEE_TRENDS_CSV} not found — run "
              "fetch_gee_data.py first. Using placeholder trends so the "
              "dashboard still renders.")
        rng = np.random.default_rng(3)
        trends = pd.DataFrame({
            "site_id": sites["site_id"],
            "trend": rng.choice(["Improving", "Stable", "Declining"],
                                 size=len(sites)),
            "improvement_rate": rng.integers(10, 90, size=len(sites)),
            "avg_ndvi": rng.uniform(0.25, 0.75, size=len(sites)),
        })
        data_source = "Field monitoring + placeholder satellite data (no GEE run yet)"

    field = load_field_survey(sites["site_id"].tolist())
    ndvi_history = load_ndvi_history(sites["site_id"].tolist())

    # The GEE stage writes the acquisition date for each site image.
    ndvi_dates = {}
    dates_file = config.DATA_DIR / "site_ndvi_dates.csv"
    if dates_file.exists():
        dates_df = pd.read_csv(dates_file)
        if {"site_id", "date"}.issubset(dates_df.columns):
            ndvi_dates = dict(zip(dates_df["site_id"].astype(str), dates_df["date"].astype(str)))

    merged = (
        sites.merge(trends, on="site_id", how="left")
             .merge(field, on="site_id", how="left")
    )

    records = []
    for _, r in merged.iterrows():
        sat_health = ndvi_to_health_pct(r.get("avg_ndvi"))
        field_health = r.get("vegetation_health")
        field_health = None if pd.isna(field_health) else round(float(field_health), 1)

        combined = [v for v in (field_health, sat_health) if v is not None]
        combined_health = round(sum(combined) / len(combined), 1) if combined else None

        status = compute_status(combined_health if combined_health is not None else field_health)
        trend = r.get("trend", "Stable")
        if pd.isna(trend):
            trend = "Stable"

        records.append({
            "site_id": r["site_id"],
            "site_name": r["site_name"],
            "latitude": round(float(r["latitude"]), 5),
            "longitude": round(float(r["longitude"]), 5),
            "vegetation_health": field_health,
            "satellite_health": sat_health,
            "combined_health": combined_health,
            "area_hectares": r.get("area_hectares"),
            "restoration_type": r.get("restoration_type"),
            "invasive_species_cover": r.get("invasive_species_cover"),
            "community_engagement": r.get("community_engagement"),
            "funding_status": r.get("funding_status"),
            "status": status,
            "trend": trend,
            "improvement_rate": r.get("improvement_rate"),
            "prediction": prediction_for(trend),
            "ndvi_history": ndvi_history.get(r["site_id"], []),
            # Site-specific assets generated by the GEE/QGIS stages.
            "ndvi_image_url": f"ndvi/{r['site_id']}.png",
            "ndvi_image_date": ndvi_dates.get(str(r["site_id"])),
            "report_url": f"../reports/sites/{r['site_id']}_report.pdf",
        })

    now = datetime.now(timezone.utc)
    payload = {
        "last_updated_utc": now.isoformat(),
        "last_updated_human": now.strftime("%Y-%m-%d %H:%M UTC"),
        "total_sites": len(records),
        "data_source": data_source,
        "sites": records,
    }

    with open(config.DASHBOARD_JSON, "w") as f:
        json.dump(payload, f, indent=2, default=lambda o: None if pd.isna(o) else o)

    print(f"Wrote {len(records)} sites to {config.DASHBOARD_JSON}")
    return payload


if __name__ == "__main__":
    run()
