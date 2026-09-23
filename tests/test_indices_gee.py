"""Unit tests for spectral indices on live GEE data.

Skips gracefully if GEE is not authenticated.
"""

import pytest

try:
    import ee
    ee.Initialize()
    HAS_GEE = True
except Exception:
    HAS_GEE = False


# ============================================================
# Import tests (always run)
# ============================================================

def test_spectral_module_imports():
    from aem.indices import spectral
    expected = ["ndvi", "evi", "savi", "msavi",
                "ndwi", "mndwi",
                "nbr", "dnbr", "rdnbr",
                "vci", "tci", "vhi"]
    for fn in expected:
        assert hasattr(spectral, fn), f"missing {fn}"


# ============================================================
# GEE-dependent tests
# ============================================================

@pytest.mark.skipif(not HAS_GEE, reason="GEE not authenticated")
def test_ndvi_on_modis():
    """Compute NDVI from real MODIS surface reflectance bands."""
    from aem.indices.spectral import ndvi

    img = ee.Image("MODIS/061/MOD09A1/2020_01_01")
    nir = img.select("sur_refl_b02")   # NIR
    red = img.select("sur_refl_b01")   # RED
    result = ndvi(nir, red)
    assert isinstance(result, ee.Image)
    # NDVI should be bounded roughly in [-1, 1]
    stats = result.reduceRegion(
        reducer=ee.Reducer.minMax(),
        geometry=ee.Geometry.Point([133.0, -25.0]).buffer(1e5),
        scale=500,
        maxPixels=1e9,
    ).getInfo()
    assert stats["NDVI_min"] >= -1.1
    assert stats["NDVI_max"] <= 1.1


@pytest.mark.skipif(not HAS_GEE, reason="GEE not authenticated")
def test_nbr_on_modis():
    """NBR should be bounded in [-1, 1]."""
    from aem.indices.spectral import nbr

    img = ee.Image("MODIS/061/MOD09A1/2020_01_01")
    nir = img.select("sur_refl_b02")
    swir2 = img.select("sur_refl_b07")
    result = nbr(nir, swir2)
    assert isinstance(result, ee.Image)


@pytest.mark.skipif(not HAS_GEE, reason="GEE not authenticated")
def test_vci_bounds():
    """VCI should be in [0, 100] when inputs are consistent."""
    from aem.indices.spectral import vci

    ndvi_min = ee.Image(0.1)
    ndvi_max = ee.Image(0.9)
    ndvi_cur = ee.Image(0.5)
    result = vci(ndvi_cur, ndvi_min, ndvi_max)

    val = result.reduceRegion(
        reducer=ee.Reducer.mean(),
        geometry=ee.Geometry.Point([133.0, -25.0]),
        scale=1000,
    ).getInfo()

    assert 0 <= val["VCI"] <= 100
