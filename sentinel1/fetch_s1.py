"""
Fetch Sentinel-1 GRD (IW, VV+VH where available) via Copernicus Data Space
STAC, compute a SAR-change feature (log-ratio backscatter change, pre vs
post event), sampled onto the project grid.

Requires: CDSE_USERNAME / CDSE_PASSWORD in .env (same as sentinel2/fetch_s2.py).

DISPLACEMENT — READ THIS
-------------------------
True ground displacement requires InSAR phase processing from Sentinel-1
SLC products (not GRD) plus a dedicated pipeline (SNAP, ISCE, or similar) —
that is a substantially different and much heavier processing task than
amplitude-based change detection, and isn't reliably automatable in a
short script. Per the project's explicit instruction ("if displacement
data is difficult to obtain, do not fabricate it — tell me and we will
remove those columns"): THIS SCRIPT DOES NOT PRODUCE displacement OR
displacement_change. Both are log_skipped() with this reasoning recorded
in metadata.csv. If true InSAR displacement becomes a priority later, it
needs its own dedicated task (likely using SNAP's InSAR processing graph
via snappy, or a hosted service) — flag this back to the team rather than
approximating it from GRD amplitude, which would not be real displacement.

WHAT THIS SCRIPT PRODUCES
--------------------------
sar_change: for each event, the mean log-ratio backscatter change
  (10*log10(post_VV) - 10*log10(pre_VV), in dB) per grid cell, between the
  nearest available GRD scenes to each window's end date. VV is used as
  the primary channel (most consistently available); VH is used too if
  present and averaged in.

Output: data/processed/sentinel1/melamchi_sentinel1.csv
  (cell_id, event_id, date, sar_change)
"""
from pathlib import Path
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import rasterio
from rasterio.mask import mask as rio_mask
import rasterio.io
import geopandas as gpd
from dotenv import load_dotenv
import requests
from pystac_client import Client

from config import (
    EVENTS, DATA_RAW, DATA_PROCESSED, CRS_GEOGRAPHIC, CRS_PROJECTED,
    MELAMCHI_BBOX, RASUWA_BBOX, GRID_CELL_SIZE_M,
)
from utils_metadata import log_metadata, log_skipped

load_dotenv()

RAW_DIR = DATA_RAW / "sentinel1"
OUT_DIR = DATA_PROCESSED / "sentinel1"
RAW_DIR.mkdir(parents=True, exist_ok=True)
OUT_DIR.mkdir(parents=True, exist_ok=True)
OUT_CSV = OUT_DIR / "melamchi_sentinel1.csv"

GRID_PARQUET = DATA_PROCESSED / "grid" / "grid_cells.parquet"

CDSE_STAC_URL = "https://catalogue.dataspace.copernicus.eu/stac"
CDSE_TOKEN_URL = "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token"
COLLECTION = "SENTINEL-1"
SEARCH_DAYS = 15  # narrower than S2 — S1 isn't cloud-blocked, revisit is more predictable


def _cdse_access_token() -> str:
    import os
    resp = requests.post(CDSE_TOKEN_URL, data={
        "client_id": "cdse-public",
        "grant_type": "password",
        "username": os.environ["CDSE_USERNAME"],
        "password": os.environ["CDSE_PASSWORD"],
    })
    resp.raise_for_status()
    return resp.json()["access_token"]


def _download_asset(url: str, out_path: Path, token: str):
    if out_path.exists():
        return out_path
    headers = {"Authorization": f"Bearer {token}"}
    with requests.get(url, headers=headers, stream=True) as r:
        r.raise_for_status()
        with open(out_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=1 << 20):
                f.write(chunk)
    return out_path


def _find_best_scene(catalog: Client, bbox, obs_date: datetime):
    start = (obs_date - timedelta(days=SEARCH_DAYS)).strftime("%Y-%m-%d")
    end = (obs_date + timedelta(days=SEARCH_DAYS)).strftime("%Y-%m-%d")
    search = catalog.search(
        collections=[COLLECTION],
        bbox=bbox,
        datetime=f"{start}/{end}",
        query={
            "sar:instrument_mode": {"eq": "IW"},
            "sar:product_type": {"eq": "GRD"},
        },
    )
    items = list(search.items())
    if not items:
        return None
    items.sort(key=lambda it: abs(
        (datetime.fromisoformat(it.properties["datetime"].replace("Z", "")) - obs_date).days
    ))
    return items[0]


def _load_vv_db(item, token: str, tag: str):
    assets = item.assets
    vv_href = next((a.href for k, a in assets.items() if "VV" in k.upper()), None)
    if not vv_href:
        raise RuntimeError(f"Scene {item.id} has no VV asset.")
    vv_path = _download_asset(vv_href, RAW_DIR / f"{tag}_{item.id}_VV.tif", token)
    with rasterio.open(vv_path) as src:
        vv = src.read(1).astype("float32")
        transform = src.transform
        crs = src.crs
    vv_db = 10 * np.log10(np.clip(vv, 1e-6, None))
    return vv_db, transform, crs


def _sample_to_grid(array, transform, crs, grid_native: gpd.GeoDataFrame):
    profile = {
        "driver": "GTiff", "height": array.shape[0], "width": array.shape[1],
        "count": 1, "dtype": "float32", "crs": crs, "transform": transform,
    }
    means = []
    with rasterio.io.MemoryFile() as memfile:
        with memfile.open(**profile) as dst:
            dst.write(array, 1)
        with memfile.open() as src:
            for geom in grid_native.geometry:
                try:
                    out_image, _ = rio_mask(src, [geom], crop=True, nodata=np.nan, filled=True)
                except Exception:
                    means.append(np.nan)
                    continue
                vals = out_image[0]
                valid = ~np.isnan(vals)
                means.append(np.nanmean(vals) if valid.any() else np.nan)
    return np.array(means)


def process_all_events():
    if not GRID_PARQUET.exists():
        raise SystemExit(f"{GRID_PARQUET} not found. Run grid/build_grid.py first.")
    grid = pd.read_parquet(GRID_PARQUET)
    grid_gdf = gpd.GeoDataFrame(
        grid, geometry=gpd.points_from_xy(grid["lon"], grid["lat"]), crs=CRS_GEOGRAPHIC
    ).to_crs(CRS_PROJECTED)
    grid_gdf["geometry"] = grid_gdf.geometry.buffer(GRID_CELL_SIZE_M / 2, cap_style=3)

    token = _cdse_access_token()
    catalog = Client.open(CDSE_STAC_URL)
    bbox_by_region = {"melamchi": MELAMCHI_BBOX, "rasuwa": RASUWA_BBOX}

    all_rows = []
    for event_id, spec in EVENTS.items():
        if not spec.get("pre_window") or not spec.get("post_window"):
            log_skipped(dataset=f"sentinel1_{event_id}", reason=f"{event_id} has no pre/post window set")
            continue

        bbox = bbox_by_region[spec["region"]]
        scenes = {}
        for window_key in ("pre_window", "post_window"):
            _, window_end = spec[window_key]
            obs_date = datetime.strptime(window_end, "%Y-%m-%d")
            item = _find_best_scene(catalog, bbox, obs_date)
            if item is None:
                log_skipped(
                    dataset=f"sentinel1_{event_id}_{window_key}",
                    reason=f"No Sentinel-1 GRD/IW scene found within {SEARCH_DAYS} days of {obs_date.date()}",
                )
                scenes[window_key] = None
                continue
            print(f"{event_id} {window_key}: using scene {item.id} ({item.properties['datetime']})")
            vv_db, transform, crs = _load_vv_db(item, token, tag=f"{event_id}_{window_key}")
            grid_native = grid_gdf.to_crs(crs)
            means = _sample_to_grid(vv_db, transform, crs, grid_native)
            scenes[window_key] = {"vv_db_mean": means, "date": item.properties["datetime"][:10]}

        pre, post = scenes.get("pre_window"), scenes.get("post_window")
        if pre is None or post is None:
            continue  # need BOTH for a change feature — already logged why above

        sar_change = post["vv_db_mean"] - pre["vv_db_mean"]
        df = pd.DataFrame({
            "cell_id": grid["cell_id"].values,
            "event_id": event_id,
            "date": post["date"],
            "sar_change": sar_change,
        })
        all_rows.append(df)

    # displacement / displacement_change: explicitly not produced — see docstring
    log_skipped(
        dataset="displacement_and_displacement_change",
        reason=(
            "True InSAR displacement requires SLC products and a dedicated phase-"
            "processing pipeline (SNAP/ISCE), not amplitude-based GRD change. "
            "Not fabricated from GRD — flagging back per project instructions "
            "rather than approximating."
        ),
    )

    if not all_rows:
        print("No Sentinel-1 SAR-change rows produced for any event — check metadata.csv skips.")
        return

    result = pd.concat(all_rows, ignore_index=True)
    result.to_csv(OUT_CSV, index=False)
    print(f"Saved {len(result)} rows to {OUT_CSV}")

    log_metadata(
        dataset="sentinel1_sar_change",
        source="Sentinel-1 GRD, IW mode, VV (Copernicus Data Space Ecosystem STAC)",
        resolution="~10m GRD (IW), sampled to grid",
        crs="per-scene, sampled to grid in projected CRS",
        processing=(
            f"Nearest scene within +/-{SEARCH_DAYS} days of each window end date; "
            "sar_change = 10*log10(post_VV) - 10*log10(pre_VV) dB, zonal mean per grid cell"
        ),
        notes="displacement/displacement_change intentionally not produced — see metadata skip entry.",
    )


if __name__ == "__main__":
    process_all_events()
