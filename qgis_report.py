"""
WILDLANDS Restoration Intelligence — polished QGIS PDF report.

Produces a one-page A4 executive report containing:
- status map
- current/latest Sentinel-2 NDVI image when available
- NDVI legend
- overall NDVI trend chart
- clean executive statistics
- data/date/source information

Run inside the QGIS Python environment.
"""
import json
import sys
from pathlib import Path

import config

try:
    from qgis.core import (
        QgsApplication, QgsVectorLayer, QgsProject, QgsField,
        QgsRuleBasedRenderer, QgsSymbol, QgsMarkerSymbol,
        QgsPrintLayout, QgsLayoutItemMap, QgsLayoutItemLegend,
        QgsLayoutItemLabel, QgsLayoutItemScaleBar, QgsLayoutSize,
        QgsLayoutPoint, QgsLayoutExporter, QgsUnitTypes,
        QgsLayoutItemPicture, QgsLayoutItemPage, QgsRectangle, Qgis,
    )
    from qgis.PyQt.QtCore import QVariant, Qt
except ImportError:
    sys.exit("PyQGIS not found. Run inside QGIS's Python environment.")

try:
    import pandas as pd
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import LinearSegmentedColormap
except ImportError as exc:
    sys.exit(f"Enhanced report requires pandas and matplotlib: {exc}")

STATUS_COLORS = {
    "good": "#28a745",
    "warning": "#f2b01e",
    "critical": "#d64550",
}

NDVI_IMAGE = Path(config.DATA_DIR) / "latest_ndvi.png"
NDVI_DATE = Path(config.DATA_DIR) / "latest_ndvi_date.txt"
NDVI_CHART = Path(config.REPORTS_DIR) / "ndvi_trend.png"
NDVI_LEGEND = Path(config.REPORTS_DIR) / "ndvi_legend.png"


def init_qgis():
    qgs = QgsApplication([], False)
    qgs.initQgis()
    return qgs


def load_dashboard():
    with open(config.DASHBOARD_JSON, encoding="utf-8") as f:
        return json.load(f)


def load_joined_layer():
    layer = QgsVectorLayer(str(config.SITES_GPKG), "sites", "ogr")
    if not layer.isValid():
        raise RuntimeError(f"Could not load {config.SITES_GPKG}")

    payload = load_dashboard()
    status_by_id = {s["site_id"]: s for s in payload["sites"]}

    for fname, ftype in [
        ("status", QVariant.String),
        ("trend", QVariant.String),
        ("combined_health", QVariant.Double),
    ]:
        if layer.fields().indexOf(fname) == -1:
            layer.dataProvider().addAttributes([QgsField(fname, ftype)])
    layer.updateFields()

    layer.startEditing()
    idx_status = layer.fields().indexOf("status")
    idx_trend = layer.fields().indexOf("trend")
    idx_health = layer.fields().indexOf("combined_health")

    for feat in layer.getFeatures():
        rec = status_by_id.get(feat["site_id"])
        if rec:
            layer.changeAttributeValue(feat.id(), idx_status, rec.get("status"))
            layer.changeAttributeValue(feat.id(), idx_trend, rec.get("trend"))
            layer.changeAttributeValue(feat.id(), idx_health, rec.get("combined_health"))

    layer.commitChanges()
    return layer


def apply_status_symbology(layer):
    root_rule = QgsRuleBasedRenderer.Rule(
        QgsSymbol.defaultSymbol(layer.geometryType())
    )
    for status, color in STATUS_COLORS.items():
        symbol = QgsMarkerSymbol.createSimple({
            "color": color,
            "outline_color": "white",
            "outline_width": "0.6",
            "size": "3",
        })
        rule = QgsRuleBasedRenderer.Rule(
            symbol, filterExp=f'"status" = \'{status}\''
        )
        rule.setLabel(status.capitalize())
        root_rule.appendChild(rule)

    layer.setRenderer(QgsRuleBasedRenderer(root_rule))
    layer.triggerRepaint()
    layer.saveNamedStyle(str(config.QGIS_STYLE_QML))
    print(f"Saved symbology to {config.QGIS_STYLE_QML}")


def collect_ndvi(payload):
    rows = []
    latest_values = []
    for site in payload.get("sites", []):
        history = site.get("ndvi_history", []) or []
        for item in history:
            try:
                rows.append({"date": item["date"], "ndvi": float(item["ndvi"])})
            except (KeyError, TypeError, ValueError):
                continue
        if history:
            try:
                latest_values.append(float(history[-1]["ndvi"]))
            except (KeyError, TypeError, ValueError):
                pass

    if not rows:
        return pd.DataFrame(), None

    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"], format="%Y-%m", errors="coerce")
    df = df.dropna(subset=["date"])
    trend = df.groupby("date", as_index=False)["ndvi"].mean()
    latest_mean = sum(latest_values) / len(latest_values) if latest_values else None
    return trend, latest_mean


def create_ndvi_assets(payload):
    trend, latest_mean = collect_ndvi(payload)
    if trend.empty:
        return None, None

    fig, ax = plt.subplots(figsize=(9.5, 3.0), dpi=200)
    ax.plot(trend["date"], trend["ndvi"], linewidth=2.5)
    ax.fill_between(trend["date"], trend["ndvi"], alpha=0.10)
    ax.scatter(trend["date"].iloc[-1], trend["ndvi"].iloc[-1], s=28, zorder=3)
    ax.set_title("Overall NDVI Performance", loc="left", fontsize=13, fontweight="bold")
    ax.set_ylabel("Mean NDVI", fontsize=9)
    ax.set_ylim(0, 1)
    ax.grid(True, alpha=0.18)
    ax.tick_params(axis="x", labelrotation=30, labelsize=8)
    ax.tick_params(axis="y", labelsize=8)
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(NDVI_CHART, bbox_inches="tight", facecolor="white")
    plt.close(fig)

    cmap = LinearSegmentedColormap.from_list(
        "ndvi", ["#8c510a", "#d8b365", "#f6e8c3", "#f5f5f5", "#c7eae5", "#5ab4ac", "#01665e"]
    )
    fig, ax = plt.subplots(figsize=(5.2, 0.55), dpi=180)
    fig.subplots_adjust(left=0.06, right=0.98, top=0.78, bottom=0.35)
    gradient = [[-0.2 + i * (1.0 / 1000) for i in range(1001)]]
    ax.imshow(gradient, aspect="auto", cmap=cmap, extent=[-0.2, 0.8, 0, 1])
    ax.set_yticks([])
    ax.set_xticks([-0.2, 0, 0.2, 0.4, 0.6, 0.8])
    ax.tick_params(axis="x", labelsize=7, length=2)
    ax.set_xlabel("NDVI: lower vegetation response → higher vegetation response", fontsize=7)
    for spine in ax.spines.values():
        spine.set_visible(False)
    fig.savefig(NDVI_LEGEND, bbox_inches="tight", facecolor="white", transparent=False)
    plt.close(fig)

    print(f"Created NDVI chart: {NDVI_CHART}")
    print(f"Created NDVI legend: {NDVI_LEGEND}")
    return latest_mean, trend


# Current page used by the report. QGIS layout coordinates are absolute,
# so every item must be translated from page-relative coordinates.
_CURRENT_PAGE_INDEX = 0


def _page_point(layout, x, y):
    """Convert page-relative millimetre coordinates to absolute layout coordinates."""
    point = layout.pageCollection().pagePositionToLayoutPosition(
        _CURRENT_PAGE_INDEX,
        QgsLayoutPoint(x, y, QgsUnitTypes.LayoutMillimeters),
    )
    return QgsLayoutPoint(point.x(), point.y(), QgsUnitTypes.LayoutMillimeters)


def add_label(layout, text, x, y, w=None, h=None, font_size=10, bold=False, align="left"):
    """Add a QGIS 4 label without custom font manipulation."""
    item = QgsLayoutItemLabel(layout)
    item.setText(str(text))

    # QGIS 4-compatible alignment. Font styling intentionally uses the
    # QGIS layout defaults instead of deprecated QGIS 3/PyQt5 font APIs.
    if align == "center":
        item.setHAlign(Qt.AlignmentFlag.AlignCenter)
    elif align == "right":
        item.setHAlign(Qt.AlignmentFlag.AlignRight)
    else:
        item.setHAlign(Qt.AlignmentFlag.AlignLeft)

    item.adjustSizeToText()
    item.attemptMove(_page_point(layout, x, y))
    if w is not None and h is not None:
        item.attemptResize(QgsLayoutSize(w, h, QgsUnitTypes.LayoutMillimeters))
    layout.addLayoutItem(item)
    return item


def add_picture(layout, path, x, y, w, h, keep_aspect=True):
    """Add a raster image using the QGIS 4 layout picture item."""
    path = Path(path).expanduser().resolve()

    if not path.exists():
        raise FileNotFoundError(f"Report image not found: {path}")
    if path.stat().st_size == 0:
        raise RuntimeError(f"Report image is empty: {path}")

    # Create the item first, add it to the layout, then assign the source.
    # This mirrors the normal QGIS layout-item lifecycle.
    picture = QgsLayoutItemPicture(layout)
    layout.addLayoutItem(picture)

    picture.attemptMove(_page_point(layout, x, y))
    picture.attemptResize(
        QgsLayoutSize(w, h, QgsUnitTypes.LayoutMillimeters)
    )

    # QGIS 4: explicitly set the source as a raster image.
    picture.setPicturePath(str(path), Qgis.PictureFormat.Raster)
    picture.setResizeMode(
        QgsLayoutItemPicture.Zoom if keep_aspect
        else QgsLayoutItemPicture.Stretch
    )

    # Force the raster to be loaded and redraw the item.
    picture.refreshPicture()
    picture.invalidateCache()
    picture.recalculateSize()
    picture.attemptResize(
        QgsLayoutSize(w, h, QgsUnitTypes.LayoutMillimeters)
    )
    picture.redraw()

    # Diagnostic output — this will tell us whether QGIS actually loaded it.
    print(
        f"IMAGE | {path.name} | "
        f"exists={path.exists()} | "
        f"bytes={path.stat().st_size} | "
        f"missing={picture.isMissingImage()} | "
        f"path={picture.picturePath()}"
    )

    return picture

def add_rect_border(layout, x, y, w, h, color="#e0e0e0", width=0.5):
    """Add a rectangular border for visual grouping"""
    from qgis.core import QgsLayoutItemShape, QgsRectangle
    from qgis.PyQt.QtGui import QColor, QPen
    from qgis.PyQt.QtCore import Qt
    
    rect = QgsLayoutItemShape(layout)
    rect.setShapeType(QgsLayoutItemShape.Rectangle)
    rect.setPen(QPen(QColor(color), width, Qt.PenStyle.SolidLine))
    rect.attemptMove(_page_point(layout, x, y))
    rect.attemptResize(QgsLayoutSize(w, h, QgsUnitTypes.LayoutMillimeters))
    layout.addLayoutItem(rect)
    return rect


def create_site_ndvi_chart(site, out_path):
    """Create a compact site-level NDVI history chart."""
    history = site.get("ndvi_history", []) or []
    rows = []
    for item in history:
        try:
            rows.append((pd.to_datetime(item["date"], format="%Y-%m"), float(item["ndvi"])))
        except (KeyError, TypeError, ValueError):
            continue

    if not rows:
        return False

    rows.sort(key=lambda x: x[0])
    dates = [r[0] for r in rows]
    values = [r[1] for r in rows]

    fig, ax = plt.subplots(figsize=(5.2, 1.75), dpi=180)
    ax.plot(dates, values, linewidth=2.0)
    ax.fill_between(dates, values, alpha=0.10)
    ax.scatter(dates[-1], values[-1], s=24, zorder=3)
    ax.set_ylim(0, 1)
    ax.set_ylabel("NDVI", fontsize=7)
    ax.tick_params(axis="x", labelrotation=25, labelsize=6)
    ax.tick_params(axis="y", labelsize=6)
    ax.grid(True, alpha=0.16)
    ax.spines[["top", "right"]].set_visible(False)
    ax.set_title("NDVI history", loc="left", fontsize=8.5, fontweight="bold")
    fig.tight_layout()
    fig.savefig(out_path, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return True


def _priority_sites(payload, limit=6):
    """Return the most important sites for page 2."""
    sites = payload.get("sites", []) or []
    severity = {"critical": 0, "warning": 1, "good": 2}

    def key(site):
        status = str(site.get("status", "warning")).lower()
        health = site.get("combined_health")
        try:
            health_value = float(health)
        except (TypeError, ValueError):
            health_value = 999
        return (severity.get(status, 1), health_value)

    return sorted(sites, key=key)[:limit]


def _site_recommendation(site):
    status = str(site.get("status", "warning")).lower()
    trend = str(site.get("trend", "Stable"))
    health = site.get("combined_health")

    if status == "critical":
        return "Immediate field investigation and restoration intervention recommended."
    if status == "warning" and trend == "Declining":
        return "Prioritise field inspection and investigate the declining vegetation response."
    if status == "warning":
        return "Monitor closely and prioritise routine restoration follow-up."
    return "Continue monitoring and maintain current restoration activities."


def _add_page(layout):
    """Add an A4 page and make it the active coordinate space for helpers."""
    global _CURRENT_PAGE_INDEX

    page = QgsLayoutItemPage(layout)
    page.setPageSize("A4")
    layout.pageCollection().addPage(page)
    _CURRENT_PAGE_INDEX = layout.pageCollection().pageCount() - 1
    return page


def _add_section_title(layout, text, x, y, w=190):
    add_label(layout, text, x, y, w, 7, 12, True)


def _safe(value, fallback="—"):
    return fallback if value is None or value == "" else str(value)


def _add_kpi(layout, x, y, w, value, label):
    add_label(layout, str(value), x, y, w, 10, 16, True, "center")
    add_label(layout, label, x, y + 10, w, 5, 7, False, "center")


def export_pdf_report(layer):
    """Create a simple, reliable one-page A4 monitoring report."""
    payload = load_dashboard()
    latest_mean, trend = create_ndvi_assets(payload)

    project = QgsProject.instance()
    project.addMapLayer(layer)

    layout = QgsPrintLayout(project)
    layout.initializeDefaults()
    layout.pageCollection().page(0).setPageSize("A4")

    global _CURRENT_PAGE_INDEX
    _CURRENT_PAGE_INDEX = 0

    MARGIN = 10
    PAGE_W = 210

    sites = payload.get("sites", []) or []
    total = len(sites)
    critical = sum(str(s.get("status", "")).lower() == "critical" for s in sites)
    warning = sum(str(s.get("status", "")).lower() == "warning" for s in sites)
    good = sum(str(s.get("status", "")).lower() == "good" for s in sites)

    health = []
    for s in sites:
        try:
            if s.get("combined_health") is not None:
                health.append(float(s["combined_health"]))
        except (TypeError, ValueError):
            pass
    avg_health = sum(health) / len(health) if health else 0

    latest_date = NDVI_DATE.read_text(encoding="utf-8").strip() if NDVI_DATE.exists() else "Not available"
    updated = payload.get("last_updated_human", "Not available")

    # Header
    add_label(layout, "WILDLANDS RESTORATION INTELLIGENCE", MARGIN, 9, 130, 10, 14, True)
    add_label(layout, "Restoration monitoring report", MARGIN, 20, 100, 7, 8, False)
    add_label(
        layout,
        f"Report refresh: {updated}\nLatest Sentinel-2: {latest_date}",
        135, 9, 65, 18, 7, False, "right"
    )
    add_rect_border(layout, MARGIN, 29, 190, 0.3, "#cccccc", 0.3)

    # KPI row
    kpi_y = 35
    kpi_w = 36
    gap = 2
    kpis = [
        (total, "TOTAL SITES"),
        (good, "GOOD"),
        (warning, "WARNING"),
        (critical, "CRITICAL"),
        (f"{avg_health:.0f}%", "AVG HEALTH"),
    ]
    for i, (value, label) in enumerate(kpis):
        x = MARGIN + i * (kpi_w + gap)
        add_rect_border(layout, x, kpi_y, kpi_w, 21, "#d8d8d8", 0.4)
        add_label(layout, str(value), x, kpi_y + 3, kpi_w, 9, 13, True, "center")
        add_label(layout, label, x, kpi_y + 12, kpi_w, 6, 6.5, False, "center")

    # Map
    map_x, map_y, map_w, map_h = 10, 63, 105, 100
    add_label(layout, "SITE STATUS MAP", map_x, 57, 80, 6, 9, True)

    map_item = QgsLayoutItemMap(layout)
    map_item.attemptMove(_page_point(layout, map_x, map_y))
    map_item.attemptResize(QgsLayoutSize(map_w, map_h, QgsUnitTypes.LayoutMillimeters))
    map_item.setExtent(layer.extent())
    layout.addLayoutItem(map_item)
    add_rect_border(layout, map_x, map_y, map_w, map_h, "#aaaaaa", 0.35)

    # Current NDVI
    img_x, img_y, img_w, img_h = 120, 63, 80, 100
    add_label(layout, "CURRENT SENTINEL-2 NDVI", img_x, 57, 80, 6, 9, True)

    if NDVI_IMAGE.exists():
        add_picture(layout, NDVI_IMAGE, img_x, img_y, img_w, img_h, True)
        add_rect_border(layout, img_x, img_y, img_w, img_h, "#aaaaaa", 0.35)

    ndvi_text = f"Acquisition: {latest_date}"
    if latest_mean is not None:
        ndvi_text += f"\nMean NDVI: {latest_mean:.3f}"
    add_label(layout, ndvi_text, img_x, 165, img_w, 10, 7.5, False, "center")

    # Performance graph
    add_label(layout, "NDVI PERFORMANCE", MARGIN, 181, 80, 6, 9, True)
    if NDVI_CHART.exists():
        add_picture(layout, NDVI_CHART, MARGIN, 188, 190, 53, True)
        add_rect_border(layout, MARGIN, 188, 190, 53, "#dddddd", 0.3)

    # Interpretation
    if trend is not None and not trend.empty:
        first = float(trend["ndvi"].iloc[:3].mean())
        last = float(trend["ndvi"].iloc[-3:].mean())
        change = ((last - first) / first * 100) if first else 0
        direction = "Improving" if change > 3 else "Declining" if change < -3 else "Stable"
        interpretation = f"Overall NDVI trend: {direction} ({change:+.1f}%)."
    else:
        interpretation = "Overall NDVI trend: insufficient historical data."

    add_rect_border(layout, MARGIN, 248, 190, 25, "#d8d8d8", 0.35)
    add_label(layout, "PROGRAMME INTERPRETATION", MARGIN + 4, 252, 180, 6, 9, True)
    add_label(
        layout,
        interpretation + " Critical sites should be prioritised for field investigation and restoration follow-up.",
        MARGIN + 4, 260, 180, 11, 7.5, False
    )

    # Footer
    add_label(
        layout,
        "Source: field monitoring + Sentinel-2 NDVI | Automated PyQGIS report",
        MARGIN, 282, 190, 7, 6.5, False, "center"
    )
    add_label(
        layout,
        "Note: report refresh time and satellite observation date are separate.",
        MARGIN, 289, 190, 6, 6.5, False, "center"
    )

    exporter = QgsLayoutExporter(layout)
    result = exporter.exportToPdf(
        str(config.REPORT_PDF),
        QgsLayoutExporter.PdfExportSettings()
    )
    if result != QgsLayoutExporter.Success:
        raise RuntimeError(f"PDF export failed with code {result}")

    print(f"Exported simple report to {config.REPORT_PDF}")


def export_site_pdf_reports(layer):
    """Create one compact A4 PDF per site containing its map, current NDVI,
    site NDVI history and decision-ready statistics.
    """
    payload = load_dashboard()
    sites = payload.get("sites", []) or []
    project = QgsProject.instance()
    if layer.id() not in [l.id() for l in project.mapLayers().values()]:
        project.addMapLayer(layer)

    config.SITE_REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    for site in sites:
        site_id = str(site.get("site_id", ""))
        if not site_id:
            continue

        feat = next((f for f in layer.getFeatures() if str(f["site_id"]) == site_id), None)
        if feat is None:
            print(f"WARNING: No geometry found for {site_id}; skipping report.")
            continue

        image_path = config.NDVI_IMAGES_DIR / f"{site_id}.png"
        chart_path = config.REPORTS_DIR / f"{site_id}_ndvi_trend.png"
        chart_ok = create_site_ndvi_chart(site, chart_path)

        layout = QgsPrintLayout(project)
        layout.initializeDefaults()
        layout.pageCollection().page(0).setPageSize("A4")
        global _CURRENT_PAGE_INDEX
        _CURRENT_PAGE_INDEX = 0

        M = 10
        # Header
        add_label(layout, "WILDLANDS RESTORATION INTELLIGENCE", M, 9, 135, 8, 13, True)
        add_label(layout, f"SITE MONITORING REPORT  •  {site_id}", M, 18, 130, 7, 8, False)
        add_label(layout, _safe(site.get("ndvi_image_date"), "Latest Sentinel-2 date unavailable"), 145, 10, 55, 8, 7.5, False, "right")
        add_rect_border(layout, M, 28, 190, 0.3, "#cccccc", 0.3)

        # Site facts
        facts = [
            ("SITE", _safe(site.get("site_name"))),
            ("TYPE", _safe(site.get("restoration_type"))),
            ("AREA", f"{_safe(site.get('area_hectares'))} ha"),
            ("STATUS", _safe(site.get("status")).upper()),
            ("FIELD HEALTH", f"{_safe(site.get('vegetation_health'))}%"),
            ("SATELLITE HEALTH", f"{_safe(site.get('satellite_health'))}%"),
        ]
        x_positions = [10, 73, 136]
        for idx, (label, value) in enumerate(facts):
            row = idx // 3
            col = idx % 3
            x = x_positions[col]
            y = 34 + row * 21
            add_rect_border(layout, x, y, 59, 17, "#d8d8d8", 0.4)
            add_label(layout, value, x + 2, y + 2, 55, 7, 10.5, True, "center")
            add_label(layout, label, x + 2, y + 10, 55, 5, 6.2, False, "center")

        # Map and current NDVI image
        map_x, map_y, map_w, map_h = 10, 82, 90, 85
        img_x, img_y, img_w, img_h = 110, 82, 90, 85
        add_label(layout, "SITE LOCATION", map_x, 76, 80, 6, 9, True)
        map_item = QgsLayoutItemMap(layout)
        map_item.attemptMove(_page_point(layout, map_x, map_y))
        map_item.attemptResize(QgsLayoutSize(map_w, map_h, QgsUnitTypes.LayoutMillimeters))
        geom = feat.geometry()
        rect = geom.boundingBox()
        # Sites are points; give the report a useful local viewing extent.
        if rect.width() == 0 and rect.height() == 0:
            cx, cy = rect.center().x(), rect.center().y()
            rect = QgsRectangle(cx - 0.05, cy - 0.05, cx + 0.05, cy + 0.05)
        else:
            rect.scale(2.5)
        map_item.setExtent(rect)
        layout.addLayoutItem(map_item)
        add_rect_border(layout, map_x, map_y, map_w, map_h, "#aaaaaa", 0.35)

        add_label(layout, "CURRENT NDVI", img_x, 76, 80, 6, 9, True)
        if image_path.exists() and image_path.stat().st_size > 0:
            add_picture(layout, image_path, img_x, img_y, img_w, img_h, True)
            add_rect_border(layout, img_x, img_y, img_w, img_h, "#aaaaaa", 0.35)
        else:
            add_rect_border(layout, img_x, img_y, img_w, img_h, "#dddddd", 0.35)
            add_label(layout, "NDVI image unavailable", img_x + 5, img_y + 38, img_w - 10, 8, 8, False, "center")

        latest_ndvi = site.get("ndvi_history", [])[-1].get("ndvi") if site.get("ndvi_history") else None
        image_date = _safe(site.get("ndvi_image_date"), "Not available")
        add_label(layout, f"Observation: {image_date}   |   Latest monthly NDVI: {_safe(latest_ndvi)}", 10, 170, 190, 8, 7.2, False, "center")

        # Graph
        add_label(layout, "NDVI HISTORY", 10, 181, 80, 6, 9, True)
        if chart_ok:
            add_picture(layout, chart_path, 10, 188, 190, 54, True)
            add_rect_border(layout, 10, 188, 190, 54, "#dddddd", 0.3)
        else:
            add_label(layout, "No NDVI history available.", 10, 205, 190, 8, 8, False, "center")

        # Interpretation / decision block
        status = str(site.get("status", "warning")).lower()
        trend_name = _safe(site.get("trend"), "Stable")
        prediction = _safe(site.get("prediction"), "Monitor closely")
        recommendation = _site_recommendation(site)
        add_rect_border(layout, 10, 247, 190, 30, "#d8d8d8", 0.35)
        add_label(layout, "DECISION SUMMARY", 14, 251, 80, 6, 9, True)
        summary = f"Trend: {trend_name}  •  Status: {status.upper()}  •  Outlook: {prediction}\nRecommendation: {recommendation}"
        add_label(layout, summary, 14, 258, 182, 15, 7.2, False)

        add_label(layout, "Source: field monitoring + Sentinel-2 NDVI | Automated PyQGIS site report", 10, 285, 190, 6, 6.2, False, "center")

        output = config.SITE_REPORTS_DIR / f"{site_id}_report.pdf"
        result = QgsLayoutExporter(layout).exportToPdf(str(output), QgsLayoutExporter.PdfExportSettings())
        if result != QgsLayoutExporter.Success:
            raise RuntimeError(f"PDF export failed for {site_id} with code {result}")
        print(f"Exported site report: {output}")


def run():
    qgs = init_qgis()
    try:
        layer = load_joined_layer()
        apply_status_symbology(layer)
        export_pdf_report(layer)
        export_site_pdf_reports(layer)
    finally:
        qgs.exitQgis()


if __name__ == "__main__":
    run()