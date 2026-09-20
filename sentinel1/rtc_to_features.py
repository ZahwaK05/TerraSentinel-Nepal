"""
Turn the terrain-corrected (RTC) Sentinel-1 files ordered from ASF HyP3 into
the sar_change feature, one value per grid cell and event.

Replaces sentinel1/fetch_s1.py for this project: that script uses plain GRD
(not terrain-corrected), which misplaces pixels by up to kilometres in steep
terrain. HyP3 RTC (Copernicus 30 m DEM, gamma0, power scale) does not.

Run from the project root, after `hyp3_rtc_melamchi.py download`:
    python sentinel1\\rtc_to_features.py
    python sentinel1\\rtc_to_features.py --dir "D:\\some\\folder"   (if the files are elsewhere)

Input: *_VV.tif (and *_VH.tif if present) inside data/raw/sentinel1 (searched
recursively, .zip files are unpacked first). Each file is matched to its event
and window by the acquisition date in its name (the 4 scenes ordered from HyP3).

How the value is made (100 m cell = about 11 RTC pixels of 30 m):
  1. RTC power is averaged over each grid cell (linear power, valid pixels only),
     then converted to dB. A cell needs >= MIN_VALID_FRACTION valid pixels.
  2. sar_change = post_dB - pre_dB (VV). sar_change_vh is the same for VH.
  Positive = brighter after the event, negative = darker (e.g. new water, wet soil).

Output: data/processed/sentinel1/melamchi_sentinel1.csv
  cell_id, event_id, date (= post window end, so merge_features.py maps it to the
  'post' window), sar_change, sar_change_vh, scene_dates
Not produced: displacement / displacement_change (needs InSAR from SLC data).
"""
import argparse
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
import rasterio
from rasterio.transform import from_origin
from rasterio.warp import reproject, Resampling
import geopandas as gpd

from config import (EVENTS, DATA_RAW, DATA_PROCESSED, CRS_GEOGRAPHIC, CRS_PROJECTED,
                    GRID_CELL_SIZE_M)
from utils_metadata import log_metadata, log_skipped

RAW_DIR = DATA_RAW / "sentinel1"
OUT_DIR = DATA_PROCESSED / "sentinel1"
OUT_CSV = OUT_DIR / "melamchi_sentinel1.csv"
GRID_PARQUET = DATA_PROCESSED / "grid" / "grid_cells.parquet"
MIN_VALID_FRACTION = 0.8

# Acquisition date (YYYYMMDD) of the scene ordered from HyP3 for each event/window.
SCENES = {
    "MELAMCHI_2021": {"pre": "20210603", "post": "20210627"},
    "MELAMCHI_2026": {"pre": "20260625", "post": "20260707"},
}


def _unzip_products(root: Path) -> None:
    for z in sorted(root.rglob("*.zip")):
        try:
            with zipfile.ZipFile(z) as zf:
                todo = [n for n in zf.namelist()
                        if n.lower().endswith(("_vv.tif", "_vh.tif")) and not (root / "unzipped" / Path(n).name).exists()]
                if todo:
                    (root / "unzipped").mkdir(exist_ok=True)
                    for n in todo:
                        with zf.open(n) as src, open(root / "unzipped" / Path(n).name, "wb") as dst:
                            dst.write(src.read())
                    print(f"Unpacked {len(todo)} file(s) from {z.name}")
        except zipfile.BadZipFile:
            print(f"WARNING: {z} is not a valid zip (incomplete download?) - skipped.")


def _find_tif(root: Path, date: str, pol: str) -> Path | None:
    hits = [p for p in root.rglob(f"*_{pol}.tif") if f"{date}T" in p.name]
    return sorted(hits)[0] if hits else None


def _cell_lattice(x: np.ndarray, y: np.ndarray):
    """Spacing and integer (col, row) of every cell centroid on a regular lattice."""
    dx = np.diff(np.unique(np.round(x)))
    dx = dx[dx > 5]
    s = float(np.median(dx)) if len(dx) else float(GRID_CELL_SIZE_M)
    col = np.round((x - x.min()) / s).astype(int)
    row = np.round((y.max() - y) / s).astype(int)
    resid = max(np.abs(x - (x.min() + col * s)).max(), np.abs(y - (y.max() - row * s)).max())
    if resid > 0.25 * s:
        raise SystemExit(f"Grid centroids do not sit on a regular {s:.0f} m lattice "
                         f"(max offset {resid:.0f} m); this script needs a regular grid.")
    return s, col, row


def _cell_db(path: Path, dst_transform, shape, col, row):
    """Mean power per grid cell (linear), returned as dB per cell, plus valid fraction."""
    with rasterio.open(path) as src:
        power = src.read(1).astype("float32")
        valid = np.isfinite(power) & (power > 0)
        power = np.where(valid, power, 0).astype("float32")
        mean_p = np.full(shape, np.nan, dtype="float32")
        frac = np.zeros(shape, dtype="float32")
        reproject(power, mean_p, src_transform=src.transform, src_crs=src.crs, src_nodata=0,
                  dst_transform=dst_transform, dst_crs=CRS_PROJECTED, dst_nodata=np.nan,
                  resampling=Resampling.average)
        reproject(valid.astype("float32"), frac, src_transform=src.transform, src_crs=src.crs,
                  dst_transform=dst_transform, dst_crs=CRS_PROJECTED, resampling=Resampling.average)
    p, f = mean_p[row, col], frac[row, col]
    db = np.full(len(p), np.nan, dtype="float32")
    ok = np.isfinite(p) & (p > 0) & (f >= MIN_VALID_FRACTION)
    db[ok] = 10 * np.log10(p[ok])
    return db


def main(search_dir: Path):
    if not GRID_PARQUET.exists():
        raise SystemExit(f"{GRID_PARQUET} not found. Run grid/build_grid.py first.")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    grid = pd.read_parquet(GRID_PARQUET)
    pts = gpd.GeoDataFrame(grid, geometry=gpd.points_from_xy(grid["lon"], grid["lat"]),
                           crs=CRS_GEOGRAPHIC).to_crs(CRS_PROJECTED)
    x, y = pts.geometry.x.to_numpy(), pts.geometry.y.to_numpy()
    s, col, row = _cell_lattice(x, y)
    if abs(s - GRID_CELL_SIZE_M) > 0.1 * GRID_CELL_SIZE_M:
        print(f"WARNING: grid centroids are {s:.0f} m apart, config says {GRID_CELL_SIZE_M} m. "
              f"Averaging over {s:.0f} m cells.")
    shape = (int(row.max()) + 1, int(col.max()) + 1)
    dst_transform = from_origin(x.min() - s / 2, y.max() + s / 2, s, s)

    _unzip_products(search_dir)
    print(f"Looking for RTC files under {search_dir}")

    rows = []
    for event_id, wins in SCENES.items():
        cfg = EVENTS[event_id]
        found = {(w, pol): _find_tif(search_dir, d, pol) for w, d in wins.items() for pol in ("VV", "VH")}
        if not all(found[(w, "VV")] for w in wins):
            missing = [f"{w} ({wins[w]})" for w in wins if not found[(w, "VV")]]
            log_skipped(dataset=f"sentinel1_{event_id}",
                        reason=f"RTC VV file not found for: {', '.join(missing)}. Run hyp3_rtc_melamchi.py download.")
            print(f"{event_id}: SKIPPED, VV file missing for {', '.join(missing)}")
            continue
        for k, v in found.items():
            print(f"  {event_id} {k[0]:4s} {k[1]}: {v.name if v else '-'}")

        vv = {w: _cell_db(found[(w, 'VV')], dst_transform, shape, col, row) for w in wins}
        df = pd.DataFrame({
            "cell_id": grid["cell_id"].to_numpy(), "event_id": event_id,
            "date": cfg["post_window"][1], "sar_change": vv["post"] - vv["pre"],
        })
        if all(found[(w, "VH")] for w in wins):
            vh = {w: _cell_db(found[(w, 'VH')], dst_transform, shape, col, row) for w in wins}
            df["sar_change_vh"] = vh["post"] - vh["pre"]
        df["scene_dates"] = "/".join(pd.to_datetime(wins[w]).strftime("%Y-%m-%d") for w in ("pre", "post"))
        rows.append(df)
        c = df["sar_change"]
        print(f"  {event_id}: value for {c.notna().mean():.0%} of cells; sar_change dB "
              f"mean {c.mean():.2f}, std {c.std():.2f}, min {c.min():.1f}, max {c.max():.1f}")

    if not rows:
        raise SystemExit("No events could be built. See the messages above.")
    result = pd.concat(rows, ignore_index=True)
    result.to_csv(OUT_CSV, index=False)
    print(f"Saved {len(result)} rows to {OUT_CSV}")

    log_metadata(
        dataset="sentinel1_sar_change", source="ASF HyP3 RTC (Sentinel-1 IW GRD, gamma0, power, 30 m, Copernicus DEM)",
        resolution=f"30 m RTC averaged to {s:.0f} m grid cells", crs=CRS_PROJECTED,
        processing=(f"Linear power averaged per cell (>= {MIN_VALID_FRACTION:.0%} valid pixels), then dB; "
                    f"sar_change = post_dB - pre_dB; scenes: {SCENES}"),
        notes="Supersedes fetch_s1.py (uncorrected GRD). Displacement not produced (needs InSAR).")
    log_skipped(dataset="displacement_and_displacement_change",
                reason="True InSAR displacement needs SLC products and phase processing; not approximated from amplitude.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default=str(RAW_DIR))
    main(Path(ap.parse_args().dir))
