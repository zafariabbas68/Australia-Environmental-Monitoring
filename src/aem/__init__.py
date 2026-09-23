"""
Australia Environmental Monitoring - Scientific Extension.

A cloud-native geospatial pipeline for environmental monitoring
using Google Earth Engine, with rigorous QA/QC, trend analysis,
change detection, and validation against reference datasets.
"""

from pathlib import Path

__version__ = "0.2.0"
__author__ = "Ghulam Abbas Zafari"
PROJECT_ROOT = Path(__file__).resolve().parents[2]

__all__ = ["PROJECT_ROOT", "__version__", "__author__"]
