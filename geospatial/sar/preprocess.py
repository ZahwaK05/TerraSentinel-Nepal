"""
SAR Preprocessing Module
========================
Converts Sentinel-1 GRD backscatter to sigma-naught (dB) and
produces a water-mask raster.

Data mode: HISTORICAL | SIMULATED | LIVE  (set by caller)
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import rasterio
from rasterio.transform import from_bounds

logger = logging.getLogger(__name__)


def backscatter_to_db(array: np.ndarray) -> np.ndarray:
    """Convert linear SAR backscatter values to decibels (dB).

    Args:
        array: 2-D NumPy array of linear amplitude values.

    Returns:
        2-D NumPy array of dB values. NoData pixels (0) are set to NaN.
    """
    with np.errstate(divide="ignore", invalid="ignore"):
        db = 10.0 * np.log10(array, where=array > 0)
        db[array <= 0] = np.nan
    return db


def classify_water(db_array: np.ndarray, threshold_db: float = -16.0) -> np.ndarray:
    """Classify pixels as water based on a backscatter threshold.

    Args:
        db_array: 2-D array of dB backscatter values.
        threshold_db: Pixels below this value are classified as water.
                      Default -16 dB is a common Sentinel-1 VV threshold.

    Returns:
        Binary mask (1 = water, 0 = non-water).

    Note:
        This threshold is an assumption. Adjust per scene and validate
        against optical water indices. Document any changes in
        docs/risk-methodology/.
    """
    return (db_array < threshold_db).astype(np.uint8)


def preprocess_sar_file(
    input_path: Path,
    output_path: Path,
    *,
    band: int = 1,
    threshold_db: float = -16.0,
    data_mode: str = "HISTORICAL",
) -> dict:
    """Run the full SAR preprocessing pipeline for a single GRD file.

    Args:
        input_path: Path to the input GeoTIFF (Sentinel-1 GRD).
        output_path: Path to write the water-mask GeoTIFF.
        band: Band index to read (1-indexed). VV=1, VH=2 for IW GRD.
        threshold_db: Water classification threshold in dB.
        data_mode: One of HISTORICAL, SIMULATED, LIVE.

    Returns:
        Metadata dict describing the output.
    """
    logger.info("SAR preprocessing: %s [mode=%s]", input_path.name, data_mode)

    with rasterio.open(input_path) as src:
        raw = src.read(band).astype(np.float32)
        profile = src.profile.copy()

    db = backscatter_to_db(raw)
    water_mask = classify_water(db, threshold_db=threshold_db)

    profile.update(dtype=rasterio.uint8, count=1, nodata=255)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(output_path, "w", **profile) as dst:
        dst.write(water_mask, 1)
        dst.update_tags(
            data_mode=data_mode,
            threshold_db=str(threshold_db),
            band_used=str(band),
        )

    water_pixels = int(water_mask.sum())
    total_pixels = int(water_mask.size)
    logger.info(
        "Water pixels: %d / %d (%.1f%%)",
        water_pixels,
        total_pixels,
        100.0 * water_pixels / total_pixels,
    )

    return {
        "output": str(output_path),
        "data_mode": data_mode,
        "water_pixel_count": water_pixels,
        "total_pixel_count": total_pixels,
        "threshold_db": threshold_db,
    }
