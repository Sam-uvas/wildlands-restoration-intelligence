"""
ORCHESTRATOR — run the whole pipeline in order.

    python3 run_pipeline.py                 # full run, skip QGIS if unavailable
    python3 run_pipeline.py --with-qgis      # also generate PDF report
    python3 run_pipeline.py --skip-gee       # dev/demo: reuse existing GEE data

Wire this to cron / Task Scheduler / GitHub Actions to make the whole
thing "automatic" (see README.md for scheduling examples).
"""

import argparse
import logging
import sys
import traceback

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("pipeline")


def stage(name, fn):
    log.info(f"--- STAGE: {name} ---")
    try:
        fn()
        log.info(f"OK: {name}")
        return True
    except Exception:
        log.error(f"FAILED: {name}\n{traceback.format_exc()}")
        return False


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-gee", action="store_true",
                         help="Skip the GEE fetch stage (reuse existing CSVs)")
    parser.add_argument("--with-qgis", action="store_true",
                         help="Also run the PyQGIS report stage (requires QGIS env)")
    args = parser.parse_args()

    import sites_setup
    stage("site registry", sites_setup.ensure_sites)

    if not args.skip_gee:
        import fetch_gee_data
        ok = stage("GEE fetch", fetch_gee_data.run)
        if not ok:
            log.warning("Continuing with existing/placeholder trend data.")

    import merge_data
    if not stage("merge -> dashboard data.json", merge_data.run):
        sys.exit(1)

    if args.with_qgis:
        import qgis_report
        stage("QGIS map/report export", qgis_report.run)

    log.info("Pipeline complete.")


if __name__ == "__main__":
    main()
