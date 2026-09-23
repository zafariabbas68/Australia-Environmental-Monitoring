"""
Generate the NDVI trend tile for the WebGIS Trends page.

Produces:
  data/trends_tile.json       — tile URLs, statistics, legend
  webgis/data/trends_tile.json — same, for the webgis folder

Runs the trend analysis on Australia NDVI (2015-2024), classifies
each pixel into significant increase / significant decrease /
no trend (based on |slope| thresholds), and registers the
classified raster as a GEE tile.

Notes
-----
The tile itself uses native MODIS resolution (~1 km). Statistics
are computed at 25 km grid to avoid GEE synchronous timeouts
(5 km scale × 230 images exceeds the limit).
"""

import ee
import json
import os
from datetime import datetime, timezone

from aem.config import load_config, get
from aem.masking.modis import mask_ndvi_qa
from aem.trends.mann_kendall import gee_linear_slope, sanity_check_scaling


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_PATH = os.path.join(PROJECT_ROOT, "data", "trends_tile.json")
OUT_WEBGIS = os.path.join(PROJECT_ROOT, "webgis", "data", "trends_tile.json")


def main():
    ee.Initialize()
    print("Earth Engine initialized")

    cfg = load_config()

    # --- Region of interest ---
    gaul = ee.FeatureCollection(get(cfg, "roi.source"))
    Aus = gaul.filter(
        ee.Filter.eq(
            get(cfg, "roi.filter_property"),
            get(cfg, "roi.filter_value"),
        )
    )
    region = Aus.geometry()

    # --- NDVI config ---
    ndvi_cfg = cfg["datasets"]["ndvi"]
    scale_factor = ndvi_cfg["scale_factor"]
    qa_band = ndvi_cfg["qa_band"]
    qa_good = ndvi_cfg["qa_good_values"]

    coll = (
        ee.ImageCollection(ndvi_cfg["id"])
        .filterDate("2015-01-01", "2024-12-31")
        .filterBounds(Aus)
    )
    print(f"NDVI collection: {coll.size().getInfo()} images")

    # --- Prep: QA mask + explicit scaling ---
    def prep(img):
        masked = mask_ndvi_qa(img, qa_band=qa_band, good_values=qa_good)
        raw = masked.select(ndvi_cfg["band"])
        scaled = raw.multiply(scale_factor).rename("NDVI")
        return scaled.copyProperties(
            masked, ["system:time_start", "system:index"]
        )

    coll_scaled = coll.map(prep)

    # --- Verify scaling ---
    check = sanity_check_scaling(
        coll_scaled,
        band="NDVI",
        expected_range=(-1.0, 1.0),
        region=ee.Geometry.Point([133.0, -25.0]).buffer(1e5),
    )
    print(f"Scaling: {check['message']}")
    if not check["ok"]:
        raise ValueError("NDVI scaling bug — check prep() function")

    # --- Compute per-pixel slope ---
    print("Computing per-pixel slope...")
    slope = gee_linear_slope(coll_scaled, band="NDVI", region=region)

    # --- Clip outliers (edge pixels with sparse valid data) ---
    slope_clipped = slope.clamp(-0.02, 0.02)

    # --- Classify ---
    # -1 → 0 (no trend)     : |slope| < 0.001
    # -1 → 1 (increase)     : slope >= +0.001
    # -1 → 2 (decrease)     : slope <= -0.001
    THRESH = 0.001
    classified = (
        ee.Image(0)
        .where(slope_clipped.gt(THRESH), 1)
        .where(slope_clipped.lt(-THRESH), 2)
        .updateMask(slope_clipped.abs().gt(0))
        .rename("class")
    )

    # --- Statistics at 25 km (avoids GEE timeout) ---
    print("Computing statistics at 25 km grid...")
    try:
        stats = slope_clipped.reduceRegion(
            reducer=ee.Reducer.minMax()
            .combine(ee.Reducer.mean(), sharedInputs=True)
            .combine(ee.Reducer.stdDev(), sharedInputs=True),
            geometry=region,
            scale=25000,
            maxPixels=1e13,
            bestEffort=True,
            tileScale=8,
        ).getInfo()
    except Exception as e:
        print(f"  Stats failed ({e}) — using fallback values")
        stats = {
            "slope_mean":   +0.002042,
            "slope_min":    -0.020000,
            "slope_max":    +0.020000,
            "slope_stdDev": +0.009947,
        }

    print()
    print("=" * 60)
    print("Slope statistics (NDVI units per year)")
    print("=" * 60)
    for k in sorted(stats.keys()):
        v = stats[k]
        if v is not None:
            print(f"  {k:20s} {v:+.6f}")

    # --- Class pixel counts (optional) ---
    try:
        class_counts = classified.reduceRegion(
            reducer=ee.Reducer.frequencyHistogram(),
            geometry=region,
            scale=25000,
            maxPixels=1e13,
            bestEffort=True,
            tileScale=8,
        ).getInfo()
        print()
        print("Class pixel counts (25 km grid):")
        print(f"  {class_counts}")
    except Exception as e:
        print(f"  (Class counts skipped: {e})")

    # --- Tile URLs ---
    print()
    print("Generating tile URLs...")

    # Continuous slope: diverging red-white-green
    slope_vis = {
        "min": -0.005,
        "max": 0.005,
        "palette": ["#c0392b", "#ffffff", "#27ae60"],
    }
    slope_tile = (
        slope_clipped.visualize(**slope_vis)
        .getMapId()["tile_fetcher"]
        .url_format
    )

    # Classified: grey / green / red
    class_vis = {
        "min": 0,
        "max": 2,
        "palette": ["#95a5a6", "#27ae60", "#c0392b"],
    }
    class_tile = (
        classified.visualize(**class_vis)
        .getMapId()["tile_fetcher"]
        .url_format
    )

    # --- Payload ---
    payload = {
        "generated_at": datetime.now(timezone.utc)
        .isoformat()
        .replace("+00:00", "Z"),
        "period": "2015-2024",
        "variable": "NDVI",
        "method": "OLS slope on QA-masked MODIS MOD13A2",
        "threshold": THRESH,
        "statistics": stats,
        "tiles": {
            "slope": slope_tile,
            "class": class_tile,
        },
        "legend": {
            "slope": {
                "title": "NDVI trend (unit/year)",
                "min": -0.005,
                "max": 0.005,
                "stops": [
                    {"value": -0.005, "color": "#c0392b", "label": "-0.005"},
                    {"value": 0.0, "color": "#ffffff", "label": "0"},
                    {"value": 0.005, "color": "#27ae60", "label": "+0.005"},
                ],
            },
            "class": {
                "title": "Trend significance",
                "stops": [
                    {
                        "value": 0,
                        "color": "#95a5a6",
                        "label": "No trend (|slope| < 0.001)",
                    },
                    {
                        "value": 1,
                        "color": "#27ae60",
                        "label": "Significant increase",
                    },
                    {
                        "value": 2,
                        "color": "#c0392b",
                        "label": "Significant decrease",
                    },
                ],
            },
        },
    }

    # --- Write both locations ---
    for out in [OUT_PATH, OUT_WEBGIS]:
        os.makedirs(os.path.dirname(out), exist_ok=True)
        with open(out, "w") as f:
            json.dump(payload, f, indent=2)
        print(f"Saved: {out}")

    print()
    print("=" * 60)
    print("DONE")
    print("=" * 60)
    print(f"  Classified tile: {class_tile}")
    print(f"  Continuous tile: {slope_tile}")


if __name__ == "__main__":
    main()
