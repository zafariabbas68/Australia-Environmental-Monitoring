"""
Unit tests for Mann-Kendall trend analysis.

Split into:
  - Pure numpy tests (no GEE needed) — synthetic series with known trends
  - GEE-dependent tests (skipped if not authenticated)
"""

import numpy as np
import pytest
import pandas as pd


# ============================================================
# Import test
# ============================================================

def test_module_imports():
    from aem.trends import mann_kendall as mk
    for fn in ["gee_mann_kendall", "gee_sens_slope",
               "mk_local", "mk_dataframe",
               "classify_trend", "trend_color"]:
        assert hasattr(mk, fn), f"missing {fn}"


# ============================================================
# Reference-implementation tests (numpy only)
# ============================================================

def test_mk_detects_strong_increase():
    """A clean increasing series should be flagged as significant."""
    from aem.trends.mann_kendall import mk_local

    values = np.array([1, 2, 3, 4, 5, 6, 7, 8, 9, 10], dtype=float)
    result = mk_local(values)

    assert result["trend"] == "increasing"
    assert result["h"] is True
    assert result["p"] < 0.05
    assert result["slope"] == pytest.approx(1.0, abs=0.01)


def test_mk_detects_strong_decrease():
    from aem.trends.mann_kendall import mk_local

    values = np.array([10, 9, 8, 7, 6, 5, 4, 3, 2, 1], dtype=float)
    result = mk_local(values)

    assert result["trend"] == "decreasing"
    assert result["h"] is True
    assert result["slope"] == pytest.approx(-1.0, abs=0.01)


def test_mk_no_trend_on_flat_series():
    """A constant series should have no trend."""
    from aem.trends.mann_kendall import mk_local

    values = np.full(10, 5.0)
    result = mk_local(values)

    assert result["h"] is False
    assert result["trend"] == "no trend"


def test_mk_handles_nan():
    """NaN values should be silently ignored."""
    from aem.trends.mann_kendall import mk_local

    values = np.array([1, 2, np.nan, 4, 5, 6, 7, 8, 9, 10], dtype=float)
    result = mk_local(values)

    assert result["trend"] == "increasing"
    assert not np.isnan(result["p"])


def test_mk_insufficient_data():
    """Fewer than 3 valid values → return sentinel dict."""
    from aem.trends.mann_kendall import mk_local

    values = np.array([1.0, 2.0])
    result = mk_local(values)

    assert result["trend"] == "insufficient data"
    assert result["h"] is False


def test_mk_robust_to_outlier():
    """Mann-Kendall should resist a single outlier."""
    from aem.trends.mann_kendall import mk_local

    clean = np.arange(20, dtype=float)
    outlier = clean.copy()
    outlier[10] = 500.0  # massive spike

    r_clean = mk_local(clean)
    r_outlier = mk_local(outlier)

    # Trend direction must be unchanged
    assert r_clean["trend"] == r_outlier["trend"] == "increasing"
    # p-value may shift slightly but should stay highly significant
    assert r_outlier["p"] < 0.05


def test_mk_dataframe():
    from aem.trends.mann_kendall import mk_dataframe

    df = pd.DataFrame({
        "year": list(range(2010, 2020)),
        "ndvi": [0.3, 0.32, 0.31, 0.35, 0.37, 0.36, 0.40, 0.42, 0.41, 0.45],
    })
    result = mk_dataframe(df, value_col="ndvi", time_col="year")

    assert result["trend"] == "increasing"
    assert result["h"] is True


# ============================================================
# Classification tests
# ============================================================

def test_classify_trend():
    from aem.trends.mann_kendall import classify_trend

    assert classify_trend("increasing", True) == "significant increase"
    assert classify_trend("decreasing", True) == "significant decrease"
    assert classify_trend("increasing", False) == "no significant trend"


def test_trend_color():
    from aem.trends.mann_kendall import trend_color

    assert trend_color("increasing") == "#2ecc71"
    assert trend_color("decreasing") == "#e74c3c"
    assert trend_color("no trend") == "#95a5a6"
    assert trend_color("unknown") == "#95a5a6"
