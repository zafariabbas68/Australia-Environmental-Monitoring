"""
Mann-Kendall trend analysis for environmental time series.

This module provides:
  - `gee_linear_slope`: per-pixel OLS slope on GEE (fast)
  - `gee_sens_slope`: alias for `gee_linear_slope` (back-compat)
  - `gee_mann_kendall`: slope + correlation with time
  - `mk_local`: exact Mann-Kendall via pyMannKendall (reference)
  - `mk_dataframe`: same, on pandas series
  - `classify_trend`, `trend_color`: helpers for reporting
  - `sanity_check_scaling`: guard against unit-conversion bugs

Design notes
------------
GEE's `ee.Reducer.sensSlope()` is under-documented (band order,
unit interpretation). We use `ee.Reducer.linearFit()` instead,
which computes the least-squares slope with a clearly defined
(x, y) interface. On typical NDVI time series, the OLS slope
closely matches Sen's slope and has the same units (value/year).

For strict Sen's slope and Mann-Kendall p-values, sample pixels
and use `mk_local` (pyMannKendall) as ground truth.

References
----------
- Mann, H.B. (1945). Nonparametric tests against trend.
  Econometrica, 13(3), 245-259.
- Kendall, M.G. (1975). Rank Correlation Methods, 4th ed.
- Sen, P.K. (1968). Estimates of the regression coefficient
  based on Kendall's tau. JASA, 63(324), 1379-1389.
- Hussain, M., & Mahmud, I. (2019). pyMannKendall. JOSS 4(39), 1556.
"""

from __future__ import annotations

import ee
import numpy as np
import pandas as pd


# ============================================================
# Internal helper: years-since-2000 time band
# ============================================================

def _add_time_band(img: ee.Image) -> ee.Image:
    """
    Prepend a synthetic time band 't' (years since 2000-01-01)
    to an image.

    linearFit expects (x, y) with x = predictor. We use time as x.

    Parameters
    ----------
    img : ee.Image
        Any single-band image with `system:time_start`.

    Returns
    -------
    ee.Image
        Two-band image: 't' (time, years) + the original value band.
    """
    epoch_ms = ee.Date("2000-01-01").millis()
    t_years = (
        ee.Number(img.get("system:time_start"))
        .subtract(epoch_ms)
        .divide(1000 * 60 * 60 * 24 * 365.25)
    )
    time_band = ee.Image.constant(t_years).rename("t").toFloat()
    return time_band.addBands(img.toFloat())


# ============================================================
# GEE-side slope (OLS via linearFit)
# ============================================================

def gee_linear_slope(
    collection: ee.ImageCollection,
    band: str,
    region: ee.Geometry | None = None,
) -> ee.Image:
    """
    Compute per-pixel least-squares slope (value/year) on GEE.

    Uses `ee.Reducer.linearFit()` with time (years) as x and the
    value band as y. The reducer returns {scale, offset}; we keep
    `scale`, which is the slope in value units per year.

    Parameters
    ----------
    collection : ee.ImageCollection
        Time series with `system:time_start` on every image.
    band : str
        Value band name, already in physical units.
    region : ee.Geometry, optional
        Clip region.

    Returns
    -------
    ee.Image
        Single-band slope raster named "slope".
    """
    def prep(img: ee.Image) -> ee.Image:
        return _add_time_band(img.select([band]))

    coll2 = collection.map(prep)
    slope = (
        coll2.reduce(ee.Reducer.linearFit())
        .select("scale")
        .rename("slope")
    )
    if region is not None:
        slope = slope.clip(region)
    return slope


# Alias for backward compatibility
def gee_sens_slope(
    collection: ee.ImageCollection,
    band: str,
    region: ee.Geometry | None = None,
) -> ee.Image:
    """
    Alias for `gee_linear_slope`.

    Historically this used `ee.Reducer.sensSlope()`, which has
    ambiguous band-order requirements. The current implementation
    uses least-squares fitting for reliability and clarity.

    For strict Sen's slope, use `mk_local()` on sampled pixels.
    """
    return gee_linear_slope(collection, band, region)


# ============================================================
# GEE-side slope + correlation
# ============================================================

def gee_mann_kendall(
    collection: ee.ImageCollection,
    band: str,
    region: ee.Geometry | None = None,
) -> dict[str, ee.Image]:
    """
    Compute per-pixel slope and correlation with time.

    Returns
    -------
    dict
        {
            "slope": ee.Image,   # OLS slope, value/year
            "tau":   ee.Image,   # Pearson r with time (proxy for tau)
        }

    Notes
    -----
    Strict Kendall's tau is not directly available from a simple
    GEE reducer. We use Pearson's r as a monotonicity indicator.
    For exact tau, use `mk_local` on sampled pixels.
    """
    def prep(img: ee.Image) -> ee.Image:
        return _add_time_band(img.select([band]))

    coll2 = collection.map(prep)

    fit = coll2.reduce(ee.Reducer.linearFit())
    slope = fit.select("scale").rename("slope")

    corr = coll2.reduce(ee.Reducer.pearsonsCorrelation())
    r = corr.select("correlation").rename("tau")

    result = {"slope": slope, "tau": r}
    if region is not None:
        result = {k: v.clip(region) for k, v in result.items()}
    return result


# ============================================================
# Local Mann-Kendall (exact, per time series)
# ============================================================

def mk_local(values: np.ndarray, alpha: float = 0.05) -> dict:
    """
    Exact Mann-Kendall trend test for a 1-D time series.

    Uses `pymannkendall.original_test`. Handles NaNs by dropping them.

    Parameters
    ----------
    values : np.ndarray
        1-D array of values in physical units.
    alpha : float
        Significance level (default 0.05).

    Returns
    -------
    dict with keys:
        trend       'increasing' | 'decreasing' | 'no trend' | 'insufficient data'
        h           True if significant at alpha
        p           two-sided p-value
        z           z-statistic
        tau         Kendall's tau
        s           Mann-Kendall S statistic
        var_s       variance of S
        slope       Sen's slope (value per time step)
        intercept   Sen's intercept
    """
    import pymannkendall as mk

    arr = np.asarray(values, dtype=float)
    arr = arr[~np.isnan(arr)]

    if arr.size < 3:
        return {
            "trend": "insufficient data", "h": False,
            "p": np.nan, "z": np.nan, "tau": np.nan,
            "s": np.nan, "var_s": np.nan,
            "slope": np.nan, "intercept": np.nan,
        }

    r = mk.original_test(arr, alpha=alpha)
    return {
        "trend":     r.trend,
        "h":         bool(r.h),
        "p":         float(r.p),
        "z":         float(r.z),
        "tau":       float(r.Tau),
        "s":         float(r.s),
        "var_s":     float(r.var_s),
        "slope":     float(r.slope),
        "intercept": float(r.intercept),
    }


def mk_dataframe(
    df: pd.DataFrame,
    value_col: str,
    time_col: str = "year",
    alpha: float = 0.05,
) -> dict:
    """Mann-Kendall test on a pandas time series."""
    df = df.sort_values(time_col)
    return mk_local(df[value_col].to_numpy(), alpha=alpha)


# ============================================================
# Classification helpers
# ============================================================

def classify_trend(trend: str, h: bool) -> str:
    """Human-readable classification."""
    if not h:
        return "no significant trend"
    if trend == "increasing":
        return "significant increase"
    if trend == "decreasing":
        return "significant decrease"
    return "no significant trend"


def trend_color(trend: str) -> str:
    """Standard colour for trend direction."""
    return {
        "increasing": "#2ecc71",
        "decreasing": "#e74c3c",
        "no trend":   "#95a5a6",
    }.get(trend, "#95a5a6")


# ============================================================
# Sanity checks
# ============================================================

def sanity_check_scaling(
    collection: ee.ImageCollection,
    band: str,
    expected_range: tuple[float, float] = (-1.0, 1.0),
    region: ee.Geometry | None = None,
) -> dict:
    """
    Verify that a collection's band is properly scaled.

    Common bug: forgetting MODIS scale factors (raw int16 x 10000).
    This function samples the first image and checks min/max.

    Returns
    -------
    dict with keys: min, max, ok, message
    """
    if region is None:
        region = collection.first().geometry()

    stats = collection.first().select([band]).reduceRegion(
        reducer=ee.Reducer.minMax(),
        geometry=region,
        scale=5000,
        maxPixels=1e10,
        bestEffort=True,
    ).getInfo()

    lo = stats.get(f"{band}_min")
    hi = stats.get(f"{band}_max")

    if lo is None or hi is None:
        return {"min": None, "max": None, "ok": False,
                "message": "No data in region"}

    ok = expected_range[0] <= lo and hi <= expected_range[1]
    return {
        "min": lo,
        "max": hi,
        "ok": ok,
        "message": (
            "OK scaling verified"
            if ok else
            f"WARNING out of range {expected_range}: got [{lo:.4f}, {hi:.4f}]"
        ),
    }
