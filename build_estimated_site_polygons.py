"""
AUTOMATED ESTIMATED SITE BOUNDARIES
-----------------------------------
Reads point sites with area_hectares and creates estimated square polygons
centred on each point. The polygon area is equal to area_hectares.

IMPORTANT:
These are monitoring-area estimates, NOT surveyed/legal restoration boundaries.
When real boundaries become available, replace this layer and keep the rest
of the pipeline unchanged.
"""

from pathlib import Path
import geopandas as gpd
from shapely.geometry import box

INPUT = Path("data/sites.gpkg")
OUTPUT = Path("data/sites_estimated.gpkg")
METRIC_CRS = "EPSG:32735"


def build():
    sites = gpd.read_file(INPUT)
    required = {"site_id", "area_hectares"}
    missing = required - set(sites.columns)
    if missing:
        raise ValueError(f"Missing required fields: {sorted(missing)}")

    metric = sites.to_crs(METRIC_CRS)
    metric["area_hectares"] = metric["area_hectares"].astype(float)

    polygons = []
    for point, area_ha in zip(metric.geometry, metric["area_hectares"]):
        side_m = (area_ha * 10000.0) ** 0.5
        half = side_m / 2.0
        polygons.append(box(
            point.x - half, point.y - half,
            point.x + half, point.y + half
        ))

    result = metric.copy()
    result["geometry"] = polygons
    result["boundary_type"] = "Estimated square from area_hectares"
    result["boundary_confidence"] = "Estimated — not surveyed boundary"
    result["estimated_area_ha"] = result.geometry.area / 10000.0
    result = result.to_crs(sites.crs)

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    if OUTPUT.exists():
        OUTPUT.unlink()
    result.to_file(OUTPUT, layer="sites", driver="GPKG")

    print(f"Created {len(result)} estimated site polygons: {OUTPUT}")
    print("IMPORTANT: These are estimated monitoring areas, not surveyed boundaries.")


if __name__ == "__main__":
    build()
