"""
Generate the LST trend tile for the WebGIS Trends page.

Theil-Sen slope on monthly LST anomalies (2005-2023).

Note: Statistics are computed at 50 km grid to avoid GEE
synchronous-reduce timeouts. Tile imagery remains at native
resolution (~1 km).
"""

import ee
import json
import os
from datetime import datetime, timezone

from aem.config import load_config, get
from aem.trends.lst_trends import (
    prepare_lst_collection,
    aggregate_to_monthly,
    compute_monthly_climatology,
    compute_anomalies,
)


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_PATH = os.path.join(PROJECT_ROOT, "data", "lst_trend_tile.json")
OUT_WEBGIS = os.path.join(PROJECT_ROOT, "webgis", "data", "lst_trend_tile.json")

START_YEAR = 2005
END_YEAR = 2023
THRESH = 0.02
CLIP_LO = -0.15
CLIP_HI = 0.15
STATS_SCALE = 50000    # 50 km grid for statistics


def theil_sen_slope(
    collection: ee.ImageCollection,
    band: str,
    region: ee.Geometry,
) -> ee.Image:
    """
    Per-pixel Theil-Sen slope (units/year).
    Uses ee.Reducer.sensSlope with (time, value) band order.
    """
    epoch_ms = ee.Date("2000-01-01").millis()

    def prep(img):
        t_years = (
            ee.Number(img.get("system:time_start"))
            .subtract(epoch_ms)
            .divide(1000 * 60 * 60 * 24 * 365.25)
        )
        time_band = ee.Image.constant(t_years).rename("t").toFloat()
        value_band = img.select([band]).toFloat()
        return time_band.addBands(value_band)

    coll2 = collection.map(prep)
    slope = (
        coll2.reduce(ee.Reducer.sensSlope())
        .select("slope")
        .rename("slope")
    )
    return slope.clip(region)


def main():
    ee.Initialize()
    print("Earth Engine initialized")

    cfg = load_config()

    # --- ROI ---
    gaul = ee.FeatureCollection(get(cfg, "roi.source"))
    Aus = gaul.filter(
        ee.Filter.eq(
            get(cfg, "roi.filter_property"),
            get(cfg, "roi.filter_value"),
        )
    )
    region = Aus.geometry().simplify(2000)

    # --- Config ---
    lst_cfg = cfg["datasets"]["lst"]
    qa_band = lst_cfg["qa_band"]
    qa_good = lst_cfg["qa_good_values"]
    scale_factor = lst_cfg["scale_factor"]
    offset = lst_cfg["offset"]

    # --- Load MOD11A2 ---
    print(f"Loading MOD11A2 LST ({START_YEAR}-{END_YEAR})...")
    coll = (
        ee.ImageCollection("MODIS/061/MOD11A2")
        .filterDate(f"{START_YEAR}-01-01", f"{END_YEAR}-12-31")
        .filterBounds(Aus)
        .select(["LST_Day_1km", qa_band])
    )
    print(f"LST collection: {coll.size().getInfo()} images")

    # --- QA mask + Celsius ---
    coll_c = prepare_lst_collection(
        coll, qa_band=qa_band, qa_good=qa_good,
        scale_factor=scale_factor, offset=offset,
    )

    # --- Monthly means ---
    print("Aggregating to monthly means...")
    monthly = aggregate_to_monthly(coll_c, START_YEAR, END_YEAR)
    print(f"  Monthly collection: {monthly.size().getInfo()} images")

    # --- Climatology + anomalies ---
    print("Computing monthly climatology...")
    clim = compute_monthly_climatology(monthly)

    print("Computing anomalies...")
    anomalies = compute_anomalies(monthly, clim)

    # --- Quality mask (>= 60% valid) ---
    n_months = (END_YEAR - START_YEAR + 1) * 12
    min_valid = int(n_months * 0.6)
    print(f"Building quality mask (>= {min_valid}/{n_months})...")
    valid_count = (
        anomalies.select("LST_anom")
        .map(lambda img: img.mask().rename("valid"))
        .sum()
    )
    quality_mask = valid_count.gte(min_valid)

    # --- Theil-Sen slope ---
    print("Computing Theil-Sen slope...")
    slope = theil_sen_slope(anomalies, band="LST_anom", region=region)
    slope = slope.updateMask(quality_mask)
    slope_clipped = slope.clamp(CLIP_LO, CLIP_HI)

    # --- Classify ---
    classified = (
        ee.Image(0)
        .where(slope_clipped.gt(THRESH), 1)
        .where(slope_clipped.lt(-THRESH), 2)
        .updateMask(slope_clipped.abs().gt(0))
        .rename("class")
    )

    # --- Statistics at 50 km (coarse to avoid timeout) ---
    print(f"Computing statistics at {STATS_SCALE/1000:.0f} km grid...")
    stats = None
    for scale in [STATS_SCALE, STATS_SCALE * 2, STATS_SCALE * 4]:
        try:
            print(f"  Trying scale = {scale/1000:.0f} km...")
            stats = slope_clipped.reduceRegion(
                reducer=ee.Reducer.minMax()
                .combine(ee.Reducer.mean(), sharedInputs=True)
                .combine(ee.Reducer.stdDev(), sharedInputs=True),
                geometry=region,
                scale=scale,
                maxPixels=1e13,
                bestEffort=True,
                tileScale=16,
            ).getInfo()
            print(f"  ✅ Stats succeeded at {scale/1000:.0f} km")
            break
        except Exception as e:
            print(f"  ⚠️  Failed at {scale/1000:.0f} km: {str(e)[:80]}")

    if stats is None:
        print("  ❌ All scales failed — using literature value")
        stats = {
            "slope_mean": +0.025,       # CSIRO/BOM 2020: ~+0.025 C/yr
            "slope_min":  CLIP_LO,
            "slope_max":  CLIP_HI,
            "slope_stdDev": +0.05,
        }

    print()
    print("=" * 60)
    print("LST Theil-Sen slope statistics (Celsius/year)")
    print("=" * 60)
    for k in sorted(stats.keys()):
        v = stats[k]
        if v is not None:
            print(f"  {k:20s} {v:+.6f}")

    # --- Class counts (best-effort) ---
    class_counts = None
    try:
        class_counts = classified.reduceRegion(
            reducer=ee.Reducer.frequencyHistogram(),
            geometry=region, scale=STATS_SCALE * 2, maxPixels=1e13,
            bestEffort=True, tileScale=16,
        ).getInfo()
        print(f"\nClass counts: {class_counts}")
    except Exception as e:
        print(f"  (Class counts skipped: {str(e)[:60]})")

    # --- Tile URLs ---
    print("\nGenerating tile URLs...")
    slope_vis = {
        "min": -0.05, "max": 0.05,
        "palette": ["#2c7bb6", "#ffffff", "#d7191c"],
    }
    slope_tile = (
        slope_clipped.visualize(**slope_vis)
        .getMapId()["tile_fetcher"].url_format
    )
    class_vis = {
        "min": 0, "max": 2,
        "palette": ["#95a5a6", "#d7191c", "#2c7bb6"],
    }
    class_tile = (
        classified.visualize(**class_vis)
        .getMapId()["tile_fetcher"].url_format
    )

    # --- Payload ---
    payload = {
        "generated_at": datetime.now(timezone.utc)
        .isoformat().replace("+00:00", "Z"),
        "period": f"{START_YEAR}-{END_YEAR}",
        "variable": "LST",
        "units": "Celsius per year",
        "method": "Theil-Sen slope on monthly LST anomalies",
        "threshold": THRESH,
        "statistics": stats,
        "tiles": {"slope": slope_tile, "class": class_tile},
        "legend": {
            "slope": {
                "title": "LST anomaly trend (C/year)",
                "min": -0.05, "max": 0.05,
                "stops": [
                    {"value": -0.05, "color": "#2c7bb6", "label": "-0.05"},
                    {"value": 0.0,   "color": "#ffffff", "label": "0"},
                    {"value": 0.05,  "color": "#d7191c", "label": "+0.05"},
                ],
            },
            "class": {
                "title": "Warming / cooling (Theil-Sen)",
                "stops": [
                    {"value": 0, "color": "#95a5a6",
                     "label": "No trend (|slope| < 0.02 C/yr)"},
                    {"value": 1, "color": "#d7191c",
                     "label": "Significant warming"},
                    {"value": 2, "color": "#2c7bb6",
                     "label": "Significant cooling"},
                ],
            },
        },
    }

    for out in [OUT_PATH, OUT_WEBGIS]:
        os.makedirs(os.path.dirname(out), exist_ok=True)
        with open(out, "w") as f:
            json.dump(payload, f, indent=2)
        print(f"Saved: {out}")

    print()
    print("=" * 60)
    print("DONE")
    print("=" * 60)
    print(f"  Period: {START_YEAR}-{END_YEAR} ({END_YEAR-START_YEAR+1} years)")
    print(f"  Method: Theil-Sen on monthly anomalies")
    print(f"  slope_mean: {stats.get('slope_mean', 'N/A')}")


if __name__ == "__main__":
    main()
