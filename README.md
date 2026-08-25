# WILDLANDS Restoration Intelligence — automated pipeline

Turns your manual `fetch_gee_data.py` + static dashboard into an
end-to-end, schedulable pipeline: **sites (QGIS) → GEE → merge → QGIS
report → dashboard**.

```
wildlands_pipeline/
  config.py            all settings (GEE project, thresholds, paths)
  sites_setup.py        stage 0 — authoritative site registry (GeoPackage)
  fetch_gee_data.py     stage 1 — batched, fixed GEE fetch
  merge_data.py          stage 2 — builds dashboard/data.json
  qgis_report.py         stage 3 — PyQGIS symbology + PDF report
  run_pipeline.py        orchestrator
  dashboard/
    index.html           your existing dashboard, unmodified
    data.json            generated — dashboard reads this
  data/
    sites.gpkg            your site registry (edit in QGIS)
    gee_ndvi_data.csv      raw monthly NDVI per site
    gee_trends.csv         computed trend per site
  reports/
    restoration_report.pdf generated PDF map report
```

## What changed vs. your original script

- **Sites are no longer hardcoded.** They live in `data/sites.gpkg`,
  which you maintain/digitize in QGIS. `sites_setup.py` auto-generates
  50 demo sites the first time so everything is runnable immediately;
  swap that file for your real one (same column schema) whenever ready.
- **Extraction is batched, not looped.** The original called
  `.getInfo()` once per site per month — 1,800 sequential calls for 50
  sites x 36 months. `fetch_gee_data.py` now uses `reduceRegions()`
  (one call per month across all sites) and pulls everything back with
  a single `.getInfo()` at the end.
- **`numpy` is actually imported** — the original crashed in
  `calculate_trends()`.
- **A merge stage** builds `dashboard/data.json` in the exact schema
  `index.html` expects, blending satellite NDVI with (optional) field
  survey data — so the dashboard, which already has a "load
  `data.json`" path built in, just works.
- **A QGIS automation stage** applies rule-based status symbology and
  exports a print-ready PDF report — donor-facing output straight from
  the same data, without manually styling anything in QGIS each time.
- **An orchestrator + example GitHub Actions workflow** so the whole
  thing can run unattended on a schedule.

## First-time setup

```bash
pip install -r requirements.txt
earthengine authenticate          # one-time, opens a browser
export GEE_PROJECT="your-real-project-id"
```

Run everything once, without GEE, to see it work end-to-end on demo data:

```bash
python3 run_pipeline.py --skip-gee
```

Open `dashboard/index.html` in a browser (or serve the folder,
e.g. `python3 -m http.server` from inside `dashboard/`) — it will pick
up the generated `data.json`.

Once your GEE project + real sites are ready:

```bash
python3 run_pipeline.py           # runs the real GEE fetch too
```

## QGIS report stage

PyQGIS isn't pip-installable — it ships inside a QGIS install. Options:

- **QGIS Desktop's own Python** (OSGeo4W shell on Windows, or the
  system Python QGIS uses on Linux/macOS):
  ```bash
  QT_QPA_PLATFORM=offscreen python3 qgis_report.py
  ```
- **Docker** (best for CI/scheduled servers, no local QGIS needed):
  ```bash
  docker run --rm -v $(pwd):/work -w /work qgis/qgis:latest \
      sh -c "QT_QPA_PLATFORM=offscreen python3 qgis_report.py"
  ```

Or via the orchestrator: `python3 run_pipeline.py --with-qgis` (only
works where PyQGIS is importable).

## Scheduling options

- **Cron** (Linux server): `0 3 * * 1  cd /path/to/pipeline && python3 run_pipeline.py >> pipeline.log 2>&1`
- **Windows Task Scheduler**: point at `python.exe run_pipeline.py`.
- **GitHub Actions**: see `.github/workflows/pipeline.yml` — needs a
  GEE *service account* (not personal OAuth) stored as a repo secret
  for unattended auth. The QGIS stage needs its own job/runner with
  the `qgis/qgis` Docker image since standard GitHub runners don't
  have QGIS.

## Where to go next

- **Field data**: point `config.FIELD_SURVEY_CSV` at your real field
  team export (one row per `site_id`, column `vegetation_health`) —
  right now it's simulated if the file is missing.
- **QGIS Server**: publish `data/sites.gpkg` as WMS/WFS so the Leaflet
  dashboard (or field staff in QGIS Desktop) can pull a live layer
  instead of only `data.json`.
- **NDVI rasters, not just point buffers**: export monthly NDVI images
  from GEE (`ee.batch.Export.image`) and add them as a raster layer in
  `qgis_report.py` for a much richer PDF report.
