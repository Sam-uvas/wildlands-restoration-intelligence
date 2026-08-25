"""
STAGE 0 — SITE REGISTRY
========================
Your restoration sites live in a single GeoPackage (data/sites.gpkg),
NOT hardcoded in Python. This is the file you maintain/digitize in QGIS.

Required attributes per site:
    site_id            e.g. 'REST-001'
    site_name          e.g. 'uThukela 4'
    area_hectares       float
    restoration_type    'Grassland' | 'Forest' | 'Wetland' | 'Savanna'
    funding_status      'Fully Funded' | 'Partially Funded' | 'Seeking Funding'
    invasive_species_cover   0-100 (%, optional field estimate)
    community_engagement     'High' | 'Medium' | 'Low' (optional)
    geometry            Point, in EPSG:4326

If data/sites.gpkg doesn't exist, this script creates a demo one so the
rest of the pipeline (GEE fetch -> merge -> QGIS report) can run
end-to-end immediately. Once you have real sites, either:
  (a) replace data/sites.gpkg with your real GeoPackage (same schema), or
  (b) open the generated one in QGIS and edit it directly.
"""

import random
import geopandas as gpd
import pandas as pd
from shapely.geometry import Point

import config


def build_demo_sites(n=config.DEMO_SITE_COUNT):
    random.seed(42)
    base_names = ["uThukela", "Drakensberg", "Tugela", "Mkomazi", "Umgeni",
                  "Mooi", "Bushmans", "Blood", "Sundays", "Gamtoos"]
    types = ["Grassland", "Forest", "Wetland", "Savanna"]
    funding = ["Fully Funded", "Partially Funded", "Seeking Funding"]
    engagement = ["High", "Medium", "Low"]

    rows = []
    for i in range(1, n + 1):
        rows.append({
            "site_id": f"REST-{i:03d}",
            "site_name": f"{base_names[i % len(base_names)]} {random.randint(1, 20)}",
            "area_hectares": round(random.uniform(0.5, 45.0), 1),
            "restoration_type": random.choice(types),
            "funding_status": random.choice(funding),
            "invasive_species_cover": random.randint(0, 60),
            "community_engagement": random.choice(engagement),
            "geometry": Point(
                29.5 + (random.random() - 0.5) * 2.2,   # lng
                -28.5 + (random.random() - 0.5) * 2.2,  # lat
            ),
        })
    return gpd.GeoDataFrame(rows, geometry="geometry", crs="EPSG:4326")


def ensure_sites():
    """Return a GeoDataFrame of sites, creating a demo file if needed."""
    if config.SITES_GPKG.exists():
        gdf = gpd.read_file(config.SITES_GPKG)
        print(f"Loaded {len(gdf)} sites from {config.SITES_GPKG}")
        return gdf

    print(f"No {config.SITES_GPKG.name} found — generating demo site registry...")
    gdf = build_demo_sites()
    gdf.to_file(config.SITES_GPKG, driver="GPKG")
    print(f"Wrote {len(gdf)} demo sites to {config.SITES_GPKG}")
    print("Replace this file with your real digitized sites when ready "
          "(same columns, EPSG:4326 points).")
    return gdf


if __name__ == "__main__":
    ensure_sites()
