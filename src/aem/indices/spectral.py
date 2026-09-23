"""
Spectral indices for environmental monitoring.

All formulas follow the original publications. Band assignments
are documented for MODIS products. Every function returns a
single-band ee.Image with the index name as the band name.

References
----------
- Rouse et al. (1974)  — NDVI original definition
- Huete et al. (2002)  — EVI MODIS-specific coefficients
- Huete (1988)         — SAVI
- McFeeters (1996)     — NDWI
- Xu (2006)            — MNDWI
- Gao (1996)           — NDWI (vegetation water)
- Key & Benson (2006)  — NBR, dNBR (USGS fire severity)
- Miller & Thode (2007) — RdNBR
- Kogan (1995)         — VCI (drought)
- Tucker (1979)        — spectral index theory
"""

import ee


# ============================================================
# Vegetation indices
# ============================================================

def ndvi(nir: ee.Image, red: ee.Image) -> ee.Image:
    """
    Normalized Difference Vegetation Index.

    Formula
    -------
    NDVI = (NIR - RED) / (NIR + RED)

    Range
    -----
    [-1, 1]. Values > 0.2 typically indicate vegetation;
    > 0.5 indicate dense vegetation.

    MODIS bands
    -----------
    - MOD13A2: NDVI is a pre-computed product
    - MOD09: NIR = b02, RED = b01

    Reference
    ---------
    Rouse, J.W., Haas, R.H., Schell, J.A., & Deering, D.W. (1974).
    Monitoring vegetation systems in the Great Plains with ERTS.
    NASA Special Publication, 351, 309.
    """
    return nir.subtract(red).divide(nir.add(red)).rename("NDVI")


def evi(
    nir: ee.Image,
    red: ee.Image,
    blue: ee.Image,
    g: float = 2.5,
    c1: float = 6.0,
    c2: float = 7.5,
    L: float = 1.0,
) -> ee.Image:
    """
    Enhanced Vegetation Index.

    Formula
    -------
    EVI = G * (NIR - RED) / (NIR + C1*RED - C2*BLUE + L)

    Reduces atmospheric and canopy background noise; saturates less
    than NDVI in high-biomass regions (tropical forests, irrigated
    croplands). Standard MODIS coefficients (G=2.5, C1=6.0, C2=7.5,
    L=1.0) are the defaults.

    Range
    -----
    [-1, 1]. Same interpretation as NDVI.

    Reference
    ---------
    Huete, A., Didan, K., Miura, T., Rodriguez, E.P., Gao, X., &
    Ferreira, L.G. (2002). Overview of the radiometric and
    biophysical performance of the MODIS vegetation indices.
    Remote Sensing of Environment, 83(1-2), 195-213.
    """
    num = nir.subtract(red).multiply(g)
    den = nir.add(red.multiply(c1)).subtract(blue.multiply(c2)).add(L)
    return num.divide(den).rename("EVI")


def savi(nir: ee.Image, red: ee.Image, L: float = 0.5) -> ee.Image:
    """
    Soil-Adjusted Vegetation Index.

    Formula
    -------
    SAVI = ((NIR - RED) / (NIR + RED + L)) * (1 + L)

    L=0.5 is recommended for intermediate vegetation cover. Useful
    in arid regions where soil background dominates (Australian
    interior).

    Reference
    ---------
    Huete, A.R. (1988). A soil-adjusted vegetation index (SAVI).
    Remote Sensing of Environment, 25(3), 295-309.
    """
    return (
        nir.subtract(red)
        .divide(nir.add(red).add(L))
        .multiply(1 + L)
        .rename("SAVI")
    )


def msavi(nir: ee.Image, red: ee.Image) -> ee.Image:
    """
    Modified Soil-Adjusted Vegetation Index.

    Formula
    -------
    MSAVI = (2*NIR + 1 - sqrt((2*NIR + 1)^2 - 8*(NIR - RED))) / 2

    Better than SAVI for very low vegetation cover.

    Reference
    ---------
    Qi, J., Chehbouni, A., Huete, A.R., Kerr, Y.H., & Sorooshian, S.
    (1994). A modified soil adjusted vegetation index.
    Remote Sensing of Environment, 48(2), 119-126.
    """
    term1 = nir.multiply(2).add(1)
    term2 = term1.pow(2).subtract(nir.subtract(red).multiply(8))
    return term1.subtract(term2.sqrt()).divide(2).rename("MSAVI")


# ============================================================
# Water indices
# ============================================================

def ndwi(green: ee.Image, nir: ee.Image) -> ee.Image:
    """
    Normalized Difference Water Index.

    Formula
    -------
    NDWI = (GREEN - NIR) / (GREEN + NIR)

    Positive values indicate water; negative values indicate
    vegetation or bare soil.

    MODIS bands
    -----------
    - MOD09: GREEN = b04, NIR = b02

    Reference
    ---------
    McFeeters, S.K. (1996). The use of the Normalized Difference
    Water Index (NDWI) in the delineation of open water features.
    International Journal of Remote Sensing, 17(7), 1425-1432.
    """
    return green.subtract(nir).divide(green.add(nir)).rename("NDWI")


def mndwi(green: ee.Image, swir1: ee.Image) -> ee.Image:
    """
    Modified Normalized Difference Water Index.

    Formula
    -------
    MNDWI = (GREEN - SWIR1) / (GREEN + SWIR1)

    More robust than NDWI in urban and mixed environments. Also
    better at separating water from built-up areas.

    Reference
    ---------
    Xu, H. (2006). Modification of normalised difference water index
    (NDWI) to enhance open water features in remotely sensed imagery.
    International Journal of Remote Sensing, 27(14), 3025-3033.
    """
    return green.subtract(swir1).divide(green.add(swir1)).rename("MNDWI")


# ============================================================
# Fire indices
# ============================================================

def nbr(nir: ee.Image, swir2: ee.Image) -> ee.Image:
    """
    Normalized Burn Ratio.

    Formula
    -------
    NBR = (NIR - SWIR2) / (NIR + SWIR2)

    High values -> healthy vegetation. Low/negative -> recently
    burned or water.

    MODIS bands
    -----------
    - MOD09: NIR = b02, SWIR2 = b07

    Reference
    ---------
    Key, C.H., & Benson, N.C. (2006). Landscape Assessment: Ground
    Measure of Severity, the Composite Burn Index. In FIREMON:
    Fire Effects Monitoring and Inventory System (pp. LA-1-55).
    USDA Forest Service, Rocky Mountain Research Station.
    """
    return nir.subtract(swir2).divide(nir.add(swir2)).rename("NBR")


def dnbr(nbr_pre: ee.Image, nbr_post: ee.Image) -> ee.Image:
    """
    Differenced Normalized Burn Ratio — fire severity.

    Formula
    -------
    dNBR = NBR_pre - NBR_post

    Interpretation (USGS thresholds, Key & Benson 2006)
    ---------------------------------------------------
    < 100    : unburned
    100–270  : low severity
    270–440  : moderate-low
    440–660  : moderate-high
    > 660    : high severity

    Multiply by 1000 for the "scaled dNBR" convention used in many
    operational products.
    """
    return nbr_pre.subtract(nbr_post).rename("dNBR")


def rdnbr(nbr_pre: ee.Image, nbr_post: ee.Image) -> ee.Image:
    """
    Relativized dNBR — normalizes severity by pre-fire vegetation.

    Formula
    -------
    RdNBR = dNBR / sqrt(abs(NBR_pre))

    More consistent across vegetation types than dNBR. Recommended
    when comparing severity across diverse ecosystems (e.g.,
    Australian savannas vs. alpine forests).

    Reference
    ---------
    Miller, J.D., & Thode, A.E. (2007). Quantifying burn severity
    in a heterogeneous landscape with a relative version of the
    delta Normalized Burn Ratio (dNBR). Remote Sensing of
    Environment, 109(1), 66-80.
    """
    d = dnbr(nbr_pre, nbr_post)
    return d.divide(nbr_pre.abs().sqrt()).rename("RdNBR")


# ============================================================
# Drought indices
# ============================================================

def vci(
    ndvi_current: ee.Image,
    ndvi_min: ee.Image,
    ndvi_max: ee.Image,
) -> ee.Image:
    """
    Vegetation Condition Index.

    Formula
    -------
    VCI = 100 * (NDVI - NDVI_min) / (NDVI_max - NDVI_min)

    Range
    -----
    [0, 100]:
      < 35  : severe drought
      35–50 : moderate drought
      > 50  : normal to wet

    NDVI_min and NDVI_max are computed per-pixel over a reference
    period (e.g., 2015–2020).

    Reference
    ---------
    Kogan, F.N. (1995). Application of vegetation index and
    brightness temperature for drought detection. Advances in
    Space Research, 15(11), 91-100.
    """
    return (
        ndvi_current.subtract(ndvi_min)
        .divide(ndvi_max.subtract(ndvi_min))
        .multiply(100)
        .rename("VCI")
    )


def tci(
    lst_current: ee.Image,
    lst_min: ee.Image,
    lst_max: ee.Image,
) -> ee.Image:
    """
    Temperature Condition Index.

    Formula
    -------
    TCI = 100 * (LST_max - LST) / (LST_max - LST_min)

    Range
    -----
    [0, 100]:
      < 35  : severe heat stress
      > 50  : normal

    Companion index to VCI. Together they form the Vegetation
    Health Index (VHI = 0.5*VCI + 0.5*TCI).

    Reference
    ---------
    Kogan, F.N. (1995). Application of vegetation index and
    brightness temperature for drought detection.
    """
    return (
        lst_max.subtract(lst_current)
        .divide(lst_max.subtract(lst_min))
        .multiply(100)
        .rename("TCI")
    )


# ============================================================
# Composite indices
# ============================================================

def vhi(vci_img: ee.Image, tci_img: ee.Image) -> ee.Image:
    """
    Vegetation Health Index — combines VCI and TCI.

    Formula
    -------
    VHI = 0.5 * VCI + 0.5 * TCI

    Range [0, 100]. Lower values indicate combined drought and
    heat stress.

    Reference
    ---------
    Kogan, F.N. (1995).
    """
    return vci_img.multiply(0.5).add(tci_img.multiply(0.5)).rename("VHI")
