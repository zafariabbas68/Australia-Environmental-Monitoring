"""
Land Surface Temperature (LST) trend analysis.

MODIS MOD11A2 stores LST_Day_1km as int16 in Kelvin x 50.
To obtain Celsius:  LST_C = raw * 0.02 - 273.15

Important
---------
Raw LST contains a strong seasonal cycle (Australia:
+40 C in January, +15 C in July). A naive trend on monthly
means picks up the seasonal cycle, not the climate signal.

We remove the seasonal cycle via per-month climatology:
    anomaly[y, m] = LST[y, m] - climatology[m]
where climatology[m] = mean over all years for month m.

The trend is then computed on anomalies, which is standard
practice in climate science (IPCC AR6, CSIRO/BOM).

References
----------
- Wan, Z. (2014). New refinements and validation of the
  collection-6 MODIS LST/emissivity product. RSE, 140, 36-45.
- CSIRO & BOM (2020). State of the Climate 2020.
"""

from __future__ import annotations

import ee

from aem.masking.modis import mask_lst_qa
from aem.trends.mann_kendall import gee_linear_slope


def prepare_lst_collection(
    collection: ee.ImageCollection,
    qa_band: str = "QC_Day",
    qa_good: list[int] | None = None,
    scale_factor: float = 0.02,
    offset: float = -273.15,
) -> ee.ImageCollection:
    """
    QA-mask and convert MODIS LST to Celsius.

    Returns a collection with a SINGLE band 'LST' in Celsius.
    """
    if qa_good is None:
        qa_good = [0, 1]

    def prep(img: ee.Image) -> ee.Image:
        masked = mask_lst_qa(img, qa_band=qa_band, good_values=qa_good)
        raw = masked.select("LST_Day_1km")
        lst_c = raw.multiply(scale_factor).add(offset).rename("LST")
        return lst_c.copyProperties(
            masked, ["system:time_start", "system:index"]
        )

    return collection.map(prep)


def aggregate_to_monthly(
    collection: ee.ImageCollection,
    start_year: int = 2015,
    end_year: int = 2023,
) -> ee.ImageCollection:
    """
    Aggregate to monthly means. Each image carries 'year' and
    'month' properties for later climatology computation.
    """
    years = ee.List.sequence(start_year, end_year)
    months = ee.List.sequence(1, 12)

    def for_year(y):
        def for_month(m):
            monthly = (
                collection
                .filter(ee.Filter.calendarRange(y, y, "year"))
                .filter(ee.Filter.calendarRange(m, m, "month"))
                .mean()
                .set("system:time_start",
                     ee.Date.fromYMD(y, m, 1).millis())
                .set("year", y)
                .set("month", m)
            )
            return monthly
        return months.map(for_month)

    return ee.ImageCollection.fromImages(years.map(for_year).flatten())


def compute_monthly_climatology(
    monthly_collection: ee.ImageCollection,
) -> dict:
    """
    Compute per-month climatology (mean across all years).

    Parameters
    ----------
    monthly_collection : ee.ImageCollection
        Monthly means with 'month' property (1-12).

    Returns
    -------
    dict {month: ee.Image}
        Climatology image for each month (1-12).
    """
    clim = {}
    for m in range(1, 13):
        monthly_subset = monthly_collection.filter(
            ee.Filter.eq("month", m)
        )
        clim[m] = monthly_subset.mean().rename("LST_clim")
    return clim


def compute_anomalies(
    monthly_collection: ee.ImageCollection,
    climatology: dict,
) -> ee.ImageCollection:
    """
    Compute LST anomalies by subtracting per-month climatology.

    anomaly[y, m] = LST[y, m] - climatology[m]

    The result removes the seasonal cycle, leaving only the
    interannual climate signal.

    Parameters
    ----------
    monthly_collection : ee.ImageCollection
    climatology : dict {month: ee.Image}

    Returns
    -------
    ee.ImageCollection with 'LST_anom' band and time metadata.
    """
    def subtract_clim(img: ee.Image) -> ee.Image:
        m = ee.Number(img.get("month")).toInt()
        lst = img.select("LST")

        clim_img = ee.Image(
            ee.Algorithms.If(m.eq(1),  climatology[1].select("LST_clim"),
            ee.Algorithms.If(m.eq(2),  climatology[2].select("LST_clim"),
            ee.Algorithms.If(m.eq(3),  climatology[3].select("LST_clim"),
            ee.Algorithms.If(m.eq(4),  climatology[4].select("LST_clim"),
            ee.Algorithms.If(m.eq(5),  climatology[5].select("LST_clim"),
            ee.Algorithms.If(m.eq(6),  climatology[6].select("LST_clim"),
            ee.Algorithms.If(m.eq(7),  climatology[7].select("LST_clim"),
            ee.Algorithms.If(m.eq(8),  climatology[8].select("LST_clim"),
            ee.Algorithms.If(m.eq(9),  climatology[9].select("LST_clim"),
            ee.Algorithms.If(m.eq(10), climatology[10].select("LST_clim"),
            ee.Algorithms.If(m.eq(11), climatology[11].select("LST_clim"),
                                       climatology[12].select("LST_clim")
            )))))))))))
        )

        anom = lst.subtract(clim_img).rename("LST_anom")
        return anom.copyProperties(img, ["system:time_start", "year", "month"])

    return monthly_collection.map(subtract_clim)


def lst_trend(
    collection: ee.ImageCollection,
    region: ee.Geometry | None = None,
    use_anomalies: bool = True,
) -> ee.Image:
    """
    Per-pixel OLS slope (Celsius/year) on LST or LST anomalies.
    """
    band = "LST_anom" if use_anomalies else "LST"
    return gee_linear_slope(collection, band=band, region=region)
