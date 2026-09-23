#!/bin/bash
# Refresh all GEE tile URLs and push to Vercel.
set -e
cd "/Users/ghulamabbaszafari/Downloads/AUSTRALIA ENVIRONMENTAL MONITORING PROJECT"
source .venv/bin/activate

echo "=== 1/2 Refresh main tiles ==="
python -c "
import ee, json, os
from datetime import datetime, timezone
ee.Initialize()

gaul = ee.FeatureCollection('FAO/GAUL_SIMPLIFIED_500m/2015/level0')
Aus  = gaul.filter(ee.Filter.eq('ADM0_NAME', 'Australia'))

Modis  = ee.ImageCollection('MODIS/061/MCD64A1')
NDVI   = ee.ImageCollection('MODIS/061/MOD13A2')
hansen = ee.Image('UMD/hansen/global_forest_change_2023_v1_11')
viirs  = ee.ImageCollection('NASA/LANCE/SNPP_VIIRS/C2')
lst    = ee.ImageCollection('MODIS/061/MOD11A1')
lulc   = ee.ImageCollection('MODIS/061/MCD12C1')

burned = Modis.filterDate('2021-01-01','2021-12-31').filterBounds(Aus).select('BurnDate')
ba = burned.max().clip(Aus)
burn_vis = {'min':30,'max':355,'palette':['ffffcc','ffeda0','fed976','feb24c','fd8d3c','fc4e2a','e31a1c','bd0026','800026']}

v = viirs.filterDate('2023-10-08','2023-10-30').filterBounds(Aus)
def mc(img):
    b = img.select('Bright_ti4')
    c = (ee.Image(0).where(b.gte(300).And(b.lt(320)),1).where(b.gte(320).And(b.lt(340)),2)
                     .where(b.gte(340).And(b.lt(360)),3).where(b.gte(360).And(b.lt(380)),4)
                     .where(b.gte(380),5))
    return c.updateMask(c.gt(0)).rename('Category')
cv = v.map(mc); mf = cv.max().clip(Aus); fc = cv.count().clip(Aus).rename('fire_count')
fire_vis = {'min':1,'max':5,'palette':['ffff00','ffa500','ff0000','ffffff','8b0000']}
fc_vis = {'min':0,'max':20,'palette':['000000','440154','3b528b','21918c','5ec962','fde725']}

lst_img = lst.filterDate('2019-01-01','2019-12-31').filterBounds(Aus).select('LST_Day_1km')
def k2c(img): return img.multiply(0.02).subtract(273.15).copyProperties(img, ['system:time_start'])
mean_lst = lst_img.map(k2c).mean().clip(Aus)
lst_vis = {'min':10,'max':45,'palette':['blue','limegreen','yellow','darkorange','red']}

lulc_img = lulc.filterDate('2022-01-01','2022-12-31').filterBounds(Aus).first().clip(Aus)
lk_in = list(range(16))
lk_out = [0,1,1,1,1,1,2,2,3,3,4,4,5,5,6,7]
clc = lulc_img.select('Majority_Land_Cover_Type_1').remap(lk_in, lk_out, 7).rename('classified')
lulc_vis = {'min':0,'max':7,'palette':['blue','green','yellow','orange','red','gray','white','cyan']}

ndvi_f = NDVI.select('NDVI').filterBounds(Aus)
years = ee.List.sequence(2010, 2021, 1)
months = ee.List.sequence(1, 12, 1)
def mk(y):
    def fm(m):
        return ndvi_f.filter(ee.Filter.calendarRange(y,y,'year')).filter(ee.Filter.calendarRange(m,m,'month')).mean()
    return months.map(fm)
nm = ee.ImageCollection.fromImages(years.map(mk).flatten())
ndvi_mean = nm.mean().clip(Aus).toInt16()
ndvi_vis = {'min':0,'max':8000,'palette':['#8B4513','#FFFFE0','#ADFF2F','#228B22','#006400']}

ly = hansen.select('lossyear')
fl_period = ly.gte(2020-2000).And(ly.lte(2022-2000))
fl = hansen.select('loss').updateMask(fl_period).clip(Aus)
fl_vis = {'min':0,'max':1,'palette':['red']}

def tu(i, v): return i.visualize(**v).getMapId()['tile_fetcher'].url_format

tiles = {
    'burned':      tu(ba,       burn_vis),
    'fire':        tu(mf,       fire_vis),
    'fire_count':  tu(fc,       fc_vis),
    'lst':         tu(mean_lst, lst_vis),
    'lulc':        tu(clc,      lulc_vis),
    'ndvi':        tu(ndvi_mean, ndvi_vis),
    'forest_loss': tu(fl,       fl_vis),
}
p = {'generated_at': datetime.now(timezone.utc).isoformat().replace('+00:00','Z'), 'tiles': tiles}
for o in ['data/tile_urls.json', 'webgis/data/tile_urls.json']:
    os.makedirs(os.path.dirname(o), exist_ok=True)
    with open(o, 'w') as f: json.dump(p, f, indent=2)
    print(f'  Saved: {o}')
"

echo ""
echo "=== 2/2 Refresh trends tile ==="
python scripts/generate_trends_tile.py 2>&1 | grep -E "Saved|DONE" || true

echo ""
echo "=== Commit + push ==="
git add data/ webgis/data/
git commit -m "chore: refresh GEE tile URLs — $(date -u +%Y-%m-%d)" || echo "  (nothing new)"
git push || true

echo ""
echo "✅ Done. Vercel redeploys in ~30s."
