"""Unit tests for MODIS masking utilities.

GEE-dependent tests are skipped if Earth Engine is not authenticated.
"""

import pytest

try:
    import ee
    ee.Initialize()
    HAS_GEE = True
except Exception:
    HAS_GEE = False


# ============================================================
# Import tests (no GEE needed)
# ============================================================

def test_masking_module_imports():
    """The masking module should import cleanly."""
    from aem.masking import modis
    assert hasattr(modis, "mask_lst_qa")
    assert hasattr(modis, "mask_ndvi_qa")
    assert hasattr(modis, "mask_burn_date")
    assert hasattr(modis, "apply_scale_offset")


# ============================================================
# GEE-dependent tests (skipped if not authenticated)
# ============================================================

@pytest.mark.skipif(not HAS_GEE, reason="GEE not authenticated")
def test_mask_lst_qa_returns_image():
    """mask_lst_qa should return an ee.Image."""
    from aem.masking.modis import mask_lst_qa

    img = ee.Image("MODIS/061/MOD11A1/2020_01_01").select(["LST_Day_1km", "QC_Day"])
    masked = mask_lst_qa(img, good_values=[0, 1])
    assert isinstance(masked, ee.Image)


@pytest.mark.skipif(not HAS_GEE, reason="GEE not authenticated")
def test_mask_ndvi_qa_returns_image():
    """mask_ndvi_qa should return an ee.Image."""
    from aem.masking.modis import mask_ndvi_qa

    img = ee.Image("MODIS/061/MOD13A2/2020_01_01").select(["NDVI", "SummaryQA"])
    masked = mask_ndvi_qa(img, good_values=[0])
    assert isinstance(masked, ee.Image)


@pytest.mark.skipif(not HAS_GEE, reason="GEE not authenticated")
def test_apply_scale_offset():
    """apply_scale_offset should return an ee.Image with the band scaled."""
    from aem.masking.modis import apply_scale_offset

    img = ee.Image("MODIS/061/MOD11A1/2020_01_01").select("LST_Day_1km")
    scaled = apply_scale_offset(img, "LST_Day_1km", scale=0.02, offset=-273.15)
    assert isinstance(scaled, ee.Image)
