"""
Demo: OLS slope on Australia NDVI 2015-2024.

Pipeline:
  1. Load MOD13A2 NDVI + SummaryQA
  2. Mask by QA (SummaryQA == 0, good only)
  3. Scale raw int16 x 10000 -> [-1, 1]
  4. Verify scaling with sanity_check_scaling
  5. Compute per-pixel OLS slope (NDVI/year) using linearFit
  6. Save statistics + tile URL
"""

import ee
import json
from datetime import datetime, timezone

from aem.config import load_config, get
from aem.masking.modis import mask_ndvi_qa
from aem.trends.mann_kendall import gee_linear_slope, sanity_check_scaling


def main():
    ee.Initialize()
    print("Earth Engine initialized")

    cfg = load_config()

    # --- Region of interest ---
    gaul = ee.FeatureCollection(get(cfg, "roi.source"))
    Aus = gaul.filter(ee.Filter.eq(
        get(cfg, "roi.filter_property"),
        get(cfg, "roi.filter_value"),
    ))
    region = Aus.geometry()

    # --- NDVI config ---
    ndvi_cfg = cfg["datasets"]["ndvi"]
    scale_factor = ndvi_cfg["scale_factor"]   # 0.0001
    qa_band = ndvi_cfg["qa_band"]              # SummaryQA
    qa_good = ndvi_cfg["qa_good_values"]       # [0]

    coll = (
        ee.ImageCollection(ndvi_cfg["id"])
        .filterDate("2015-01-01", "2024-12-31")
        .filterBounds(Aus)
    )
    print(f"NDVI collection: {coll.size().getInfo()} images")

    # --- Prep: QA mask + explicit scaling ---
    # Do NOT use apply_scale_offset here: addBands(overwrite=True)
    # is ambiguous in GEE and can leave the raw band in place.
    def prep(img):
        masked = mask_ndvi_qa(img, qa_band=qa_band, good_values=qa_good)
        raw = masked.select(ndvi_cfg["band"])
        scaled = raw.multiply(scale_factor).rename("NDVI")
        return scaled.copyProperties(
            masked, ["system:time_start", "system:index"]
        )

    coll_scaled = coll.map(prep)

    # --- Debug: confirm single band and correct range ---
    sample = coll_scaled.first()
    print("Sample bands:", sample.bandNames().getInfo())

    test_region = ee.Geometry.Point([133.0, -25.0]).buffer(1e5)
    check = sanity_check_scaling(
        coll_scaled,
        band="NDVI",
        expected_range=(-1.0, 1.0),
        region=test_region,
    )
    print(f"Scaling check: {check['message']}")
    print(f"  min = {check['min']}, max = {check['max']}")
    if not check["ok"]:
        raise ValueError("NDVI scaling bug — check prep() function")

    # --- Compute per-pixel slope ---
    print("\nComputing OLS slope over Australia...")
    slope = gee_linear_slope(coll_scaled, band="NDVI", region=region)

    # --- Statistics ---
    stats = slope.reduceRegion(
        reducer=ee.Reducer.minMax()
            .combine(ee.Reducer.mean(), sharedInputs=True)
            .combine(ee.Reducer.stdDev(), sharedInputs=True),
        geometry=region,
        scale=5000,
        maxPixels=1e10,
        bestEffort=True,
    ).getInfo()

    print()
    print("=" * 60)
    print("OLS slope statistics (NDVI units per year)")
    print("=" * 60)
    for k in sorted(stats.keys()):
        v = stats[k]
        if v is not None:
            print(f"  {k:20s} {v:+.6f}")

    mean_slope = stats.get("slope_mean")
    if mean_slope is not None:
        print()
        print("Interpretation:")
        print(f"  Mean slope: {mean_slope:+.6f} NDVI/year")
        if abs(mean_slope) > 0.05:
            print("  WARNING: magnitude > 0.05 NDVI/year unrealistic.")
            print("  Likely a scaling or unit error.")
        if mean_slope > 0:
            print("  Australia is GREENER on average (2015-2024)")
        elif mean_slope < 0:
            print("  Australia is BROWner on average (2015-2024)")
        else:
            print("  No significant trend detected")

    # --- Tile URL for WebGIS ---
    vis = {"min": -0.005, "max": 0.005,
           "palette": ["#c0392b", "#ffffff", "#27ae60"]}
    tile_url = slope.visualize(**vis).getMapId()["tile_fetcher"].url_format
    print()
    print("Slope tile URL (paste into browser):")
    print(f"  {tile_url}")

    # --- Save ---
    out = {
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "statistics": stats,
        "tile_url": tile_url,
    }
    with open("figures/mk_trend_australia.json", "w") as f:
        json.dump(out, f, indent=2)
    print()
    print("Saved to figures/mk_trend_australia.json")


if __name__ == "__main__":
    main()
