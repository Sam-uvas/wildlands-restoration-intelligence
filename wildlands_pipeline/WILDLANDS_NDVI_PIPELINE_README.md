# WILDLANDS — Sentinel-2 NDVI Pipeline

## What this adds

The satellite layer is deliberately separate from field observations:

    Field Monitoring
          |
          v
    FastAPI / PostgreSQL
          |
          +-------------------+
                              |
    Sentinel-2 -> GEE -> satellite_data.json
                              |
                              v
                         Analytics

The browser merges both sources by `site_id`.

## Required monitoring registry

The authoritative file is:

`data/sites.gpkg`

It must contain:

- `site_id`
- a valid geometry
- a valid CRS

The same `site_id` is what connects a monitoring area to its Sentinel-2 NDVI history.

## Google Earth Engine

The production configuration uses:

- project: `ee-sambanele860` unless `GEE_PROJECT` is set
- Sentinel-2 SR Harmonized
- NDVI = normalizedDifference(B8, B4)
- default cloud threshold: 20%
- default scale: 10 m
- default buffer for point sites: 500 m
- start date: 2023-01-01
- end date: today's date at runtime

Authenticate once from the project root:

    earthengine authenticate

If your Earth Engine Cloud Project is different:

PowerShell:

    $env:GEE_PROJECT="your-real-project-id"

Then run:

    python WILDLANDS_fetch_gee_production.py
    python WILDLANDS_build_satellite_json.py

Or double-click:

    run_wildlands_ndvi.bat

## Outputs

The pipeline produces:

`data/gee_ndvi_data.csv`
Monthly site-level NDVI observations.

`data/gee_trends.csv`
Latest NDVI, average NDVI, improvement rate and trend.

`dashboard/frontend/satellite_data.json`
Browser-ready satellite dataset consumed by Analytics.

`dashboard/frontend/ndvi/<site_id>.png`
Latest site-specific NDVI image.

## Important

There are NO synthetic NDVI values in this production pipeline.

If Earth Engine cannot find scenes or the site registry is missing, the pipeline fails instead of inventing numbers.

The Analytics page should therefore show:

`Satellite analytics pending`

until a successful GEE run creates `satellite_data.json`.

## Next architectural step

Once this is running reliably, the satellite dataset can be moved from a generated frontend JSON file into PostgreSQL/PostGIS. That is the stronger production architecture for scheduled deployments and multi-user access.
