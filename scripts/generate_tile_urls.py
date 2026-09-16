#!/usr/bin/env python3
"""
generate_tile_urls.py

Regenerates webgis/data/tile_urls.json by calling Earth Engine
and asking for a fresh map ID for each layer.

Run from the project root:
    python scripts/generate_tile_urls.py
"""

import ee
import json
import os
from datetime import datetime

# ---------- CONFIG ----------
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_PATH     = os.path.join(PROJECT_ROOT, "webgis", "data", "tile_urls.json")
os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)

# ---------- INIT EE ----------
try:
    ee.Initialize()
    print("✅ EE initialized")
except Exception:
    ee.Authenticate()
    ee.Initialize()
    print("✅ EE initialized after auth")

# ---------- LOAD DATASETS ----------
gaul = ee.FeatureCollection("FAO/GAUL_SIMPLIFIED_500m/2015/level0")
Aus  = gaul.filter(ee.Filter.eq('ADM0_NAME', 'Australia'))

Modis       = ee.ImageCollection("MODIS/061/MCD64A1")
NDVI        = ee.ImageCollection("MODIS/061/MOD13A2")
hansen      = ee.Image("UMD/hansen/global_forest_change_2023_v1_11")
suomi_viirs = ee.ImageCollection("NASA/LANCE/SNPP_VIIRS/C2")
lst         = ee.ImageCollection("MODIS/061/MOD11A1")
lulc        = ee.ImageCollection("MODIS/061/MCD12C1")

# ---------- 1. Burned Area 2021 ----------
burned = Modis.filterDate('2021-01-01', '2021-12-31').filterBounds(Aus).select('BurnDate')
ba = burned.max().clip(Aus)
burn_vis = {
    'min': 30, 'max': 355,
    'palette': ['ffffcc', 'ffeda0', 'fed976', 'feb24c',
                'fd8d3c', 'fc4e2a', 'e31a1c', 'bd0026', '800026']
}

# ---------- 2. Fire categories + count (VIIRS) ----------
viirs = suomi_viirs.filterDate('2023-10-08', '2023-10-30').filterBounds(Aus)

def mask_classify(img):
    b = img.select('Bright_ti4')
    c = (ee.Image(0)
         .where(b.gte(300).And(b.lt(320)), 1)
         .where(b.gte(320).And(b.lt(340)), 2)
         .where(b.gte(340).And(b.lt(360)), 3)
         .where(b.gte(360).And(b.lt(380)), 4)
         .where(b.gte(380), 5))
    return c.updateMask(c.gt(0)).rename('Category')

classified_viirs = viirs.map(mask_classify)
merged_fire = classified_viirs.max().clip(Aus)
fire_count  = classified_viirs.count().clip(Aus).rename('fire_count')

fire_vis = {'min': 1, 'max': 5,
            'palette': ['ffff00', 'ffa500', 'ff0000', 'ffffff', '8b0000']}
fire_count_vis = {'min': 0, 'max': 20,
                  'palette': ['000000', '440154', '3b528b',
                              '21918c', '5ec962', 'fde725']}

# ---------- 3. LST 2019 ----------
lst_img = lst.filterDate('2019-01-01', '2019-12-31').filterBounds(Aus).select('LST_Day_1km')

def k2c(img):
    return img.multiply(0.02).subtract(273.15).copyProperties(img, ['system:time_start'])

mean_lst = lst_img.map(k2c).mean().clip(Aus)
lst_vis = {'min': 10, 'max': 45,
           'palette': ['blue', 'limegreen', 'yellow', 'darkorange', 'red']}

# ---------- 4. LULC 2022 ----------
lulc_img = lulc.filterDate('2022-01-01', '2022-12-31').filterBounds(Aus).first().clip(Aus)
lk_in  = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15]
lk_out = [0, 1, 1, 1, 1, 1, 2, 2, 3, 3, 4, 4, 5, 5, 6, 7]
classified_lc = lulc_img.select('Majority_Land_Cover_Type_1').remap(lk_in, lk_out, 7).rename('classified')
lulc_vis = {'min': 0, 'max': 7,
            'palette': ['blue', 'green', 'yellow', 'orange',
                        'red', 'gray', 'white', 'cyan']}

# ---------- 5. NDVI mean (2010-2021) ----------
ndvi_f = NDVI.select('NDVI').filterBounds(Aus)
years  = ee.List.sequence(2010, 2021, 1)
months = ee.List.sequence(1, 12, 1)

def mk(y):
    def fm(m):
        return ndvi_f.filter(ee.Filter.calendarRange(y, y, 'year')) \
                     .filter(ee.Filter.calendarRange(m, m, 'month')) \
                     .mean()
    return months.map(fm)

ndvi_monthly = ee.ImageCollection.fromImages(years.map(mk).flatten())
ndvi_mean = ndvi_monthly.mean().clip(Aus).toInt16()
ndvi_vis = {'min': 0, 'max': 8000,
            'palette': ['#8B4513', '#FFFFE0', '#ADFF2F', '#228B22', '#006400']}

# ---------- 6. Forest loss 2020-2022 ----------
ly = hansen.select('lossyear')
fl_period = ly.gte(2020 - 2000).And(ly.lte(2022 - 2000))
forest_loss = hansen.select('loss').updateMask(fl_period).clip(Aus)
fl_vis = {'min': 0, 'max': 1, 'palette': ['red']}

# ---------- GET MAP IDs ----------
def tile_url(image, vis):
    return image.visualize(**vis).getMapId()['tile_fetcher'].url_format

print("🎫 Fetching tile URLs...")
tile_urls = {
    "burned":      tile_url(ba,              burn_vis),
    "fire":        tile_url(merged_fire,     fire_vis),
    "fire_count":  tile_url(fire_count,      fire_count_vis),
    "lst":         tile_url(mean_lst,        lst_vis),
    "lulc":        tile_url(classified_lc,   lulc_vis),
    "ndvi":        tile_url(ndvi_mean,       ndvi_vis),
    "forest_loss": tile_url(forest_loss,     fl_vis),
}

payload = {
    "generated_at": datetime.utcnow().isoformat() + "Z",
    "tiles": tile_urls,
}

with open(OUT_PATH, "w") as f:
    json.dump(payload, f, indent=2)

print(f"✅ Wrote {OUT_PATH}")
for k, v in tile_urls.items():
    print(f"   {k:12s} {v}")
