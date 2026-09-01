"""
ORCHESTRATOR — run the whole pipeline in order.

python3 run_pipeline.py
    Full run, skip QGIS if unavailable.

python3 run_pipeline.py --with-qgis
    Also generate PDF report.

python3 run_pipeline.py --skip-gee
    Dev/demo mode: reuse existing GEE data.

This pipeline can be scheduled using:
- GitHub Actions
- Windows Task Scheduler
- cron
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

    log.info(
        f"--- STAGE: {name} ---"
    )

    try:

        fn()

        log.info(
            f"OK: {name}"
        )

        return True

    except Exception:

        log.error(
            f"FAILED: {name}\n"
            f"{traceback.format_exc()}"
        )

        return False


def main():

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--skip-gee",
        action="store_true",
        help=(
            "Skip the GEE fetch stage "
            "(reuse existing CSVs)"
        ),
    )

    parser.add_argument(
        "--with-qgis",
        action="store_true",
        help=(
            "Also run the PyQGIS report stage "
            "(requires QGIS environment)"
        ),
    )

    args = parser.parse_args()

    # --------------------------------------------------------
    # SITE REGISTRY
    # --------------------------------------------------------

    import sites_setup

    if not stage(
        "site registry",
        sites_setup.ensure_sites,
    ):
        sys.exit(1)

    # --------------------------------------------------------
    # GOOGLE EARTH ENGINE
    # --------------------------------------------------------

    if not args.skip_gee:

        import fetch_gee_data

        gee_ok = stage(
            "GEE fetch",
            fetch_gee_data.run,
        )

        if not gee_ok:

            log.error(
                "GEE stage failed. "
                "Pipeline stopped."
            )

            sys.exit(1)

    # --------------------------------------------------------
    # MERGE DATA
    # --------------------------------------------------------

    import merge_data

    if not stage(
        "merge -> dashboard data.json",
        merge_data.run,
    ):

        sys.exit(1)

    # --------------------------------------------------------
    # OPTIONAL QGIS REPORT
    # --------------------------------------------------------

    if args.with_qgis:

        import qgis_report

        stage(
            "QGIS map/report export",
            qgis_report.run,
        )

    log.info(
        "Pipeline complete."
    )


if __name__ == "__main__":
    main()