"""
NDWI Computation Module
=======================
Computes the Normalised Difference Water Index from Sentinel-2
Green (B03) and NIR (B08) bands, then detects water-change between
a baseline and target scene.

Formula: NDWI = (Green - NIR) / (Green + NIR)

Data mode: HISTORICAL | SIMULATED | LIVE  (set by caller)
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import rasterio

logger = logging.getLogger(__name__)

# Default threshold — see docs/risk-methodology/ for calibration notes.
# OPEN QUESTION: This value must be validated against the Melamchi event.
DEFAULT_NDWI_THRESHOLD = 0.3


def compute_ndwi(green: np.ndarray, nir: np.ndarray) -> np.ndarray:
    """Compute NDWI from Green and NIR reflectance arrays.

    Args:
        green: 2-D array of green-band surface reflectance values (0–1 or DN).
        nir:   2-D array of NIR-band surface reflectance values.

    Returns:
        2-D float32 NDWI array in [-1, 1]. Division-by-zero pixels are NaN.
    """
    green = green.astype(np.float32)
    nir = nir.astype(np.float32)
    denom = green + nir
    with np.errstate(divide="ignore", invalid="ignore"):
        ndwi = np.where(denom != 0, (green - nir) / denom, np.nan)
    return ndwi.astype(np.float32)


def water_change(
    baseline_ndwi: np.ndarray,
    target_ndwi: np.ndarray,
    threshold: float = DEFAULT_NDWI_THRESHOLD,
) -> np.ndarray:
    """Detect new water pixels by comparing baseline and target NDWI.

    Args:
        baseline_ndwi: NDWI for the pre-event scene.
        target_ndwi:   NDWI for the event/post-event scene.
        threshold:     NDWI value above which a pixel is classified as water.

    Returns:
        Integer array: 0 = no change, 1 = new water, -1 = water loss.
    """
    baseline_water = baseline_ndwi >= threshold
    target_water = target_ndwi >= threshold
    change = np.zeros_like(baseline_ndwi, dtype=np.int8)
    change[~baseline_water & target_water] = 1   # new inundation
    change[baseline_water & ~target_water] = -1  # water receded
    return change


def ndwi_change_from_files(
    baseline_path: Path,
    target_path: Path,
    output_path: Path,
    *,
    green_band: int = 1,
    nir_band: int = 2,
    threshold: float = DEFAULT_NDWI_THRESHOLD,
    data_mode: str = "HISTORICAL",
) -> dict:
    """End-to-end NDWI water-change computation for two GeoTIFF scenes.

    Args:
        baseline_path: Pre-event Sentinel-2 GeoTIFF.
        target_path:   Event/post-event Sentinel-2 GeoTIFF.
        output_path:   Path to write the water-change GeoTIFF.
        green_band:    Band index for green reflectance (1-indexed).
        nir_band:      Band index for NIR reflectance (1-indexed).
        threshold:     NDWI water classification threshold.
        data_mode:     HISTORICAL | SIMULATED | LIVE.

    Returns:
        Metadata dict for the output.
    """
    logger.info(
        "NDWI change: %s → %s [mode=%s, threshold=%.2f]",
        baseline_path.name,
        target_path.name,
        data_mode,
        threshold,
    )

    with rasterio.open(baseline_path) as src:
        baseline_green = src.read(green_band).astype(np.float32)
        baseline_nir = src.read(nir_band).astype(np.float32)
        profile = src.profile.copy()

    with rasterio.open(target_path) as src:
        target_green = src.read(green_band).astype(np.float32)
        target_nir = src.read(nir_band).astype(np.float32)

    baseline_ndwi = compute_ndwi(baseline_green, baseline_nir)
    target_ndwi = compute_ndwi(target_green, target_nir)
    change = water_change(baseline_ndwi, target_ndwi, threshold=threshold)

    profile.update(dtype=rasterio.int8, count=1, nodata=-128)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(output_path, "w", **profile) as dst:
        dst.write(change, 1)
        dst.update_tags(
            data_mode=data_mode,
            ndwi_threshold=str(threshold),
        )

    new_water = int((change == 1).sum())
    logger.info("New inundation pixels: %d", new_water)

    return {
        "output": str(output_path),
        "data_mode": data_mode,
        "new_water_pixels": new_water,
        "ndwi_threshold": threshold,
    }
