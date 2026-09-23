"""
MODIS QA/QC masking utilities.

Every MODIS product carries per-pixel quality flags. Using raw
bands without QA masking introduces systematic errors of 5–20%
in LST, NDVI, and reflectance products.

References
----------
- Wan, Z. (2014). New refinements and validation of the
  collection-6 MODIS land-surface temperature/emissivity
  product. Remote Sensing of Environment, 140, 36-45.
- Huete, A. et al. (2002). Overview of the radiometric and
  biophysical performance of the MODIS vegetation indices.
  Remote Sensing of Environment, 83, 195-213.
- Giglio, L. et al. (2018). The Collection 6 MODIS active fire
  detection algorithm and fire products. RSE, 178, 31-41.
"""

import ee


# ============================================================
# LST
# ============================================================

def mask_lst_qa(
    img: ee.Image,
    qa_band: str = "QC_Day",
    good_values: list[int] | None = None,
) -> ee.Image:
    """
    Mask MODIS LST pixels not in the specified QA classes.

    MOD11A1 QC_Day bits 0-1 encode quality:
        0 = good quality
        1 = other quality (usually acceptable)
        2 = TBD
        3 = not produced (bad)

    Parameters
    ----------
    img : ee.Image
        MODIS MOD11A1 image with LST_Day_1km and QC_Day.
    qa_band : str
        QA band name. Default 'QC_Day'.
    good_values : list[int], optional
        QA values to KEEP. Default [0, 1].

    Returns
    -------
    ee.Image
        Image with bad pixels masked out.
    """
    if good_values is None:
        good_values = [0, 1]

    qa = img.select(qa_band)
    qa_quality = qa.bitwiseAnd(3)

    mask = ee.Image(0)
    for v in good_values:
        mask = mask.Or(qa_quality.eq(v))

    return img.updateMask(mask)


# ============================================================
# NDVI / EVI
# ============================================================

def mask_ndvi_qa(
    img: ee.Image,
    qa_band: str = "SummaryQA",
    good_values: list[int] | None = None,
) -> ee.Image:
    """
    Mask MODIS NDVI/EVI pixels not in the specified QA classes.

    MOD13A2 SummaryQA (bits 0-1):
        0 = good data
        1 = marginal
        2 = snow/ice
        3 = cloudy

    Parameters
    ----------
    img : ee.Image
        MODIS MOD13A2 image with NDVI/EVI + SummaryQA.
    qa_band : str
        QA band name. Default 'SummaryQA'.
    good_values : list[int], optional
        QA values to KEEP. Default [0] (good only).

    Returns
    -------
    ee.Image
        Image with bad pixels masked out.
    """
    if good_values is None:
        good_values = [0]

    qa = img.select(qa_band)

    mask = ee.Image(0)
    for v in good_values:
        mask = mask.Or(qa.eq(v))

    return img.updateMask(mask)


# ============================================================
# Burned area
# ============================================================

def mask_burn_date(img: ee.Image, band: str = "BurnDate") -> ee.Image:
    """
    Keep only pixels that burned (BurnDate > 0).

    MODIS MCD64A1 encodes burned pixels as day-of-year (1-366),
    unburned as 0.

    Parameters
    ----------
    img : ee.Image
        MODIS MCD64A1 image with BurnDate band.
    band : str
        Band name. Default 'BurnDate'.

    Returns
    -------
    ee.Image
        Image with non-burned pixels masked.
    """
    burned = img.select(band).gt(0)
    return img.updateMask(burned)


# ============================================================
# Scaling
# ============================================================

def apply_scale_offset(
    img: ee.Image,
    band: str,
    scale: float,
    offset: float = 0.0,
) -> ee.Image:
    """
    Apply linear scaling to a MODIS band.

    MODIS bands are stored as integers; physical values require:
        value = raw * scale + offset

    Examples
    --------
    LST:  scale=0.02, offset=-273.15 -> Celsius
    NDVI: scale=0.0001, offset=0     -> [-1, 1]

    Parameters
    ----------
    img : ee.Image
        Input image.
    band : str
        Band to scale.
    scale : float
        Multiplicative factor.
    offset : float
        Additive offset.

    Returns
    -------
    ee.Image
        Image with the scaled band replacing the original.
    """
    scaled = img.select(band).multiply(scale).add(offset)
    return img.addBands(scaled.rename(band), overwrite=True)
