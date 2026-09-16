#!/usr/bin/env python3
"""Copy exports_png/*.png → webgis/images/ for offline-capable WebGIS."""
import os, shutil, glob

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(PROJECT_ROOT, "exports_png")
DST = os.path.join(PROJECT_ROOT, "webgis", "images")
os.makedirs(DST, exist_ok=True)

files = glob.glob(os.path.join(SRC, "*.png"))
if not files:
    print(f"⚠️  No PNGs found in {SRC}")
else:
    for f in files:
        shutil.copy2(f, DST)
        print(f"📄 {os.path.basename(f)} → webgis/images/")
    print(f"\n✅ Copied {len(files)} PNGs to {DST}")
