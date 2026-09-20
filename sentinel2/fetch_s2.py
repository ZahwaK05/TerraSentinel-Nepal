"""
Fetch Sentinel-2 L2A imagery (Copernicus Data Space STAC), compute NDWI,
NDWI change, water area, and water-area change % per event, sampled onto
the project grid.

Requires: CDSE_USERNAME / CDSE_PASSWORD (and the S3 keys) in .env.

WHAT THIS PRODUCES (v2: cloud/snow-masked composites)
-----------------------------------------------------
For each event in config.EVENTS with pre_window/post_window set:
  - Search range keeps the event on the correct side:
        pre  window: from (start - SEARCH_DAYS) up to the window END
        post window: from the window START up to (end + SEARCH_DAYS)
    so a "pre" composite can never contain post-event scenes.
  - Per Sentinel-2 tile: the N_SCENES_PER_TILE least-cloudy scenes.
  - Per scene: B03 (Green) and B08 (NIR) at 10 m plus the SCL scene-
    classification band (20 m, resampled to 10 m by nearest neighbour).
    Pixels that are cloud, cloud shadow, cirrus, topographic shadow, snow/ice,
    saturated, unclassified or no-data (SCL_INVALID) are dropped BEFORE any
    index is computed.
  - NDWI = (Green - NIR) / (Green + NIR) per clear pixel.
  - Per tile: per-pixel MEDIAN NDWI over the clear scenes = the composite.
  - Water mask: composite NDWI > NDWI_WATER_THRESHOLD.
  - Per 100 m grid cell: ndwi_mean and water_area (m^2) are only reported if
    at least MIN_VALID_FRACTION of the cell's pixels are clear; otherwise NaN.
  - ndwi_change = post ndwi_mean - pre ndwi_mean;
    water_area_change_pct = (post - pre) / pre * 100 (NaN if pre is 0 or NaN).

Output: data/processed/sentinel2/melamchi_sentinel2.csv
  cell_id, event_id, date, ndwi_mean, water_area, ndwi_change,
  water_area_change_pct, ndwi_valid_frac, ndwi_n_obs, scene_dates
  - date        = the window END date (same convention as the rainfall table)
  - scene_dates = the acquisition dates that went into the composite
  - ndwi_valid_frac = share of the cell's pixels that were clear (0-1)
  - ndwi_n_obs      = mean number of clear scenes per pixel in the cell

If no usable scene exists for an event/window, that window is log_skipped(),
not fabricated.
"""
import math
import os
import re
import time
import warnings
from pathlib import Path
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import rasterio
from rasterio.enums import Resampling
from rasterio.windows import Window, from_bounds
from rasterio.windows import bounds as window_bounds
from pyproj import Transformer
from dotenv import load_dotenv
import requests
from pystac_client import Client

from config import (
    EVENTS, DATA_RAW, DATA_PROCESSED, CRS_GEOGRAPHIC,
    MELAMCHI_BBOX, RASUWA_BBOX, GRID_CELL_SIZE_M,
)
from utils_metadata import log_metadata, log_skipped

load_dotenv()
COLLECTION = "sentinel-2-l2a"

RAW_DIR = DATA_RAW / "sentinel2"
OUT_DIR = DATA_PROCESSED / "sentinel2"
RAW_DIR.mkdir(parents=True, exist_ok=True)
OUT_DIR.mkdir(parents=True, exist_ok=True)
OUT_CSV = OUT_DIR / "melamchi_sentinel2.csv"

GRID_PARQUET = DATA_PROCESSED / "grid" / "grid_cells.parquet"

CDSE_STAC_URL = "https://catalogue.dataspace.copernicus.eu/stac"
CDSE_TOKEN_URL = "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token"
GRID_REGION = "melamchi"  # the grid file covers this region only
SEARCH_DAYS = 20          # how far a window may be stretched (pre: before its start, post: after its end)
MAX_CLOUD_COVER = 60      # %, scene-level pre-filter only; the real cloud removal is per pixel (SCL)
N_SCENES_PER_TILE = 4     # scenes composited per tile and window (per-pixel median of clear pixels)
NDWI_WATER_THRESHOLD = 0.2  # stricter than 0: haze/shadow sit near 0. Check against known rivers/lakes.
MIN_VALID_FRACTION = 0.8  # a 100 m cell needs >= this share of clear pixels, else NaN
PIXEL_SIZE_M = 10         # B03/B08 native resolution
# SCL classes treated as NOT usable:
# 0 no data, 1 saturated/defective, 2 dark/topographic shadow, 3 cloud shadow,
# 7 unclassified, 8/9 cloud (medium/high probability), 10 thin cirrus, 11 snow/ice
SCL_INVALID = (0, 1, 2, 3, 7, 8, 9, 10, 11)


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


def _s3_client():
    import boto3
    from botocore.config import Config
    return boto3.client(
        "s3",
        endpoint_url="https://eodata.dataspace.copernicus.eu",
        aws_access_key_id=os.environ["CDSE_S3_ACCESS_KEY"],
        aws_secret_access_key=os.environ["CDSE_S3_SECRET_KEY"],
        region_name="default",
        config=Config(retries={"max_attempts": 8, "mode": "standard"},
                      connect_timeout=30, read_timeout=90),
    )


DOWNLOAD_ATTEMPTS = 5      # whole-file attempts before giving up
S3_PARALLEL_CONNECTIONS = 2  # Copernicus can drop connections when too many run at once


def _download_asset(url: str, out_path: Path, token: str):
    if out_path.exists():
        return out_path
    # Download to a temporary .part file, rename only when complete, so an
    # interrupted download is never mistaken for a finished one.
    part_path = out_path.with_name(out_path.name + ".part")
    print(f"  downloading {out_path.name} ...", flush=True)

    for attempt in range(1, DOWNLOAD_ATTEMPTS + 1):
        progress = {"done": 0, "shown": 0, "total": 0}

        def _tick(nbytes):
            progress["done"] += nbytes
            if progress["done"] - progress["shown"] >= 20 * 1024 * 1024 or progress["done"] >= progress["total"] > 0:
                progress["shown"] = progress["done"]
                total_mb = f" / {progress['total'] / 1e6:.0f}" if progress["total"] else ""
                print(f"    {progress['done'] / 1e6:.0f}{total_mb} MB", flush=True)

        try:
            if url.startswith("s3://"):
                from boto3.s3.transfer import TransferConfig
                _, _, rest = url.partition("s3://")
                bucket, _, key = rest.partition("/")
                client = _s3_client()
                try:
                    progress["total"] = client.head_object(Bucket=bucket, Key=key)["ContentLength"]
                except Exception:
                    pass  # size is only for the progress display
                client.download_file(bucket, key, str(part_path), Callback=_tick,
                                     Config=TransferConfig(max_concurrency=S3_PARALLEL_CONNECTIONS))
            else:
                headers = {"Authorization": f"Bearer {token}"}
                with requests.get(url, headers=headers, stream=True, timeout=(30, 90)) as r:
                    r.raise_for_status()
                    progress["total"] = int(r.headers.get("Content-Length", 0))
                    with open(part_path, "wb") as f:
                        for chunk in r.iter_content(chunk_size=1 << 20):
                            f.write(chunk)
                            _tick(len(chunk))
            break
        except Exception as e:
            # A wrong password / missing file will not fix itself: stop at once.
            status = None
            resp = getattr(e, "response", None)
            if isinstance(resp, dict):
                status = resp.get("ResponseMetadata", {}).get("HTTPStatusCode")
            elif resp is not None:
                status = getattr(resp, "status_code", None)
            if status is not None and 400 <= status < 500 and status != 429:
                raise
            if attempt == DOWNLOAD_ATTEMPTS:
                raise
            wait = 15 * attempt
            print(f"  download interrupted ({type(e).__name__}). "
                  f"Retrying in {wait} s (attempt {attempt + 1} of {DOWNLOAD_ATTEMPTS}) ...", flush=True)
            time.sleep(wait)
    os.replace(part_path, out_path)
    return out_path


def _find_scenes_covering_grid(catalog: Client, bbox, date_from: datetime, date_to: datetime,
                               anchor: datetime, grid: pd.DataFrame):
    """Search date_from..date_to. For each Sentinel-2 tile keep the N_SCENES_PER_TILE
    least-cloudy scenes (ties: closest to `anchor`), then keep only the tiles needed
    to cover the grid: the tile covering the most cells first, then any tile that adds
    cells the earlier ones missed.
    Returns (list of (tile, [scenes]), boolean array of grid cells covered)."""
    from shapely.geometry import shape, box, Point
    from shapely.prepared import prep

    search = catalog.search(
        collections=[COLLECTION],
        bbox=bbox,
        datetime=f"{date_from.strftime('%Y-%m-%d')}/{date_to.strftime('%Y-%m-%d')}",
        query={"eo:cloud_cover": {"lt": MAX_CLOUD_COVER}},
    )
    items = list(search.items())
    if not items:
        return [], np.zeros(len(grid), dtype=bool)

    def _rank(it):
        return (
            it.properties.get("eo:cloud_cover", 100),
            abs((datetime.fromisoformat(it.properties["datetime"].replace("Z", "")) - anchor).days),
        )

    by_tile = {}
    for it in items:
        m = re.search(r"_T(\d{2}[A-Z]{3})_", it.id)
        by_tile.setdefault(m.group(1) if m else it.id, []).append(it)
    tiles = {t: sorted(v, key=_rank)[:N_SCENES_PER_TILE] for t, v in by_tile.items()}
    names = list(tiles)

    points = [Point(x, y) for x, y in zip(grid["lon"].to_numpy(), grid["lat"].to_numpy())]
    covers = []
    for t in names:
        it = tiles[t][0]
        geom = shape(it.geometry) if getattr(it, "geometry", None) else box(*it.bbox)
        prepared = prep(geom)
        covers.append(np.array([prepared.contains(pt) for pt in points], dtype=bool))

    order = sorted(range(len(names)), key=lambda i: -int(covers[i].sum()))
    chosen, covered = [], np.zeros(len(grid), dtype=bool)
    for i in order:
        if (covers[i] & ~covered).sum() == 0:
            continue  # adds nothing new
        chosen.append((names[i], tiles[names[i]]))
        covered |= covers[i]
    return chosen, covered


def _pick_scl(assets):
    """The scene-classification (SCL) asset, preferring the 20 m one. Refuses to run
    unmasked: without SCL we cannot tell cloud/snow from water."""
    cands = [k for k in assets.keys() if "SCL" in k.upper()]
    if not cands:
        raise RuntimeError(
            "No SCL (scene classification) asset on this scene, so clouds cannot be masked. "
            f"Asset keys: {list(assets.keys())}"
        )
    pref = [k for k in cands if "20M" in k.upper()] or cands
    return pref[0], assets[pref[0]].href


def _pick_band(assets, band: str):
    """Pick the 10 m asset for a band (e.g. 'B03' -> 'B03_10m'). Refuses to guess."""
    candidates = [k for k in assets.keys() if band in k.upper()]
    tenm = [k for k in candidates if "10M" in k.upper()]
    if tenm:
        key = tenm[0]
    elif len(candidates) == 1:
        key = candidates[0]
    else:
        raise RuntimeError(
            f"Cannot tell which {band} asset is the 10 m one. "
            f"Asset keys on this scene: {list(assets.keys())}"
        )
    return key, assets[key].href


def _boa_offset(item_id: str) -> float:
    """Sentinel-2 L2A processing baseline 04.00 and later (the 'N0400'+ part of
    the scene name, which includes reprocessed older scenes) add 1000 to every
    pixel value. It must be removed before computing an index, and scenes with
    and without it must not be compared directly."""
    m = re.search(r"_N(\d{4})_", item_id)
    if not m:
        print(f"  WARNING: could not read processing baseline from {item_id}; assuming no offset")
        return 0.0
    return 1000.0 if int(m.group(1)) >= 400 else 0.0


def _grid_xy(grid: pd.DataFrame, crs):
    """Grid cell centres (lon/lat columns) in the raster's own CRS."""
    tf = Transformer.from_crs(CRS_GEOGRAPHIC, crs, always_xy=True)
    xs, ys = tf.transform(grid["lon"].to_numpy(), grid["lat"].to_numpy())
    return np.asarray(xs, dtype="float64"), np.asarray(ys, dtype="float64")


def _window_for_area(src, xmin, ymin, xmax, ymax) -> Window:
    """Pixel window covering the given bounds, clipped to the image."""
    inv = ~src.transform
    c0, r0 = inv.a * xmin + inv.b * ymax + inv.c, inv.d * xmin + inv.e * ymax + inv.f
    c1, r1 = inv.a * xmax + inv.b * ymin + inv.c, inv.d * xmax + inv.e * ymin + inv.f
    col_off = max(0, math.floor(min(c0, c1)))
    row_off = max(0, math.floor(min(r0, r1)))
    col_end = min(src.width, math.ceil(max(c0, c1)))
    row_end = min(src.height, math.ceil(max(r0, r1)))
    if col_end <= col_off or row_end <= row_off:
        raise RuntimeError("This scene does not cover the grid area at all.")
    return Window(col_off, row_off, col_end - col_off, row_end - row_off)


def _compute_ndwi_for_scene(item, token: str, tag: str, grid: pd.DataFrame):
    """Download B03/B08 (10 m) + SCL (20 m), read ONLY the part covering the grid,
    compute NDWI and set every non-clear pixel (per SCL) to NaN."""
    green_key, green_href = _pick_band(item.assets, "B03")
    nir_key, nir_href = _pick_band(item.assets, "B08")
    scl_key, scl_href = _pick_scl(item.assets)

    green_path = _download_asset(green_href, RAW_DIR / f"{tag}_{item.id}_{green_key}.jp2", token)
    nir_path = _download_asset(nir_href, RAW_DIR / f"{tag}_{item.id}_{nir_key}.jp2", token)
    scl_path = _download_asset(scl_href, RAW_DIR / f"{tag}_{item.id}_{scl_key}.jp2", token)
    offset = _boa_offset(item.id)
    print(f"  bands: {green_key}, {nir_key}, {scl_key}; value offset removed: {offset:.0f}")

    with rasterio.open(green_path) as gsrc, rasterio.open(nir_path) as nsrc:
        for name, s in (("green", gsrc), ("nir", nsrc)):
            if abs(abs(s.transform.a) - PIXEL_SIZE_M) > 0.01:
                raise RuntimeError(f"{name} band pixel size is {abs(s.transform.a)} m, expected {PIXEL_SIZE_M} m.")
        if gsrc.crs != nsrc.crs or gsrc.transform != nsrc.transform or gsrc.shape != nsrc.shape:
            raise RuntimeError("Green and NIR bands are not on the same pixel grid.")

        crs = gsrc.crs
        xs, ys = _grid_xy(grid, crs)
        pad = 2 * GRID_CELL_SIZE_M
        win = _window_for_area(gsrc, xs.min() - pad, ys.min() - pad, xs.max() + pad, ys.max() + pad)
        green = gsrc.read(1, window=win).astype("float32")
        nir = nsrc.read(1, window=win).astype("float32")
        transform = gsrc.window_transform(win)
    print(f"  read {green.shape[1]} x {green.shape[0]} pixels (grid area only)")

    # SCL is 20 m: read the SAME ground area and resample (nearest) onto the 10 m pixels.
    with rasterio.open(scl_path) as ssrc:
        # BUG FIX: `transform` is already the window's own transform, so the ground bounds of
        # the window are those of Window(0, 0, w, h) under it. The old code passed `win` (with its
        # row/col offset) again, shifting the SCL read kilometres away -> off-tile fill 0 ->
        # every pixel masked ("0% clear pixels" even on 1-8% cloud scenes).
        swin = from_bounds(*window_bounds(Window(0, 0, green.shape[1], green.shape[0]), transform),
                           transform=ssrc.transform)
        scl = ssrc.read(1, window=swin, out_shape=green.shape,
                        resampling=Resampling.nearest, boundless=True, fill_value=0)

    nodata = (green == 0) | (nir == 0)
    green = np.maximum(green - offset, 0)
    nir = np.maximum(nir - offset, 0)
    denom = green + nir
    bad = nodata | (denom == 0) | np.isin(scl, SCL_INVALID)
    ndwi = (green - nir) / np.where(bad, 1, denom)
    ndwi[bad] = np.nan

    clear = float(np.isfinite(ndwi).mean())
    med = float(np.nanmedian(ndwi)) if np.isfinite(ndwi).any() else float("nan")
    print(f"  clear pixels: {clear * 100:.0f}%   median NDWI of clear pixels: {med:.2f}")
    return ndwi.astype("float32"), transform, crs


def _composite(arrays):
    """Per-pixel median NDWI over the clear observations + how many there were."""
    stack = np.stack(arrays)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=RuntimeWarning)  # all-NaN pixels are expected
        comp = np.nanmedian(stack, axis=0)
    n_obs = np.isfinite(stack).sum(axis=0)
    return comp.astype("float32"), n_obs.astype("int16")


def _sample_to_grid(ndwi, n_obs, transform, crs, grid: pd.DataFrame):
    """Per grid cell: mean NDWI, water area, share of clear pixels, mean #observations.
    Each cell is a square of (GRID_CELL_SIZE_M / PIXEL_SIZE_M) pixels per side centred
    on the cell's lat/lon. ndwi_mean and water_area are NaN unless the cell has at least
    MIN_VALID_FRACTION clear pixels."""
    xs, ys = _grid_xy(grid, crs)
    n = int(round(GRID_CELL_SIZE_M / PIXEL_SIZE_M))
    H, W = ndwi.shape

    inv = ~transform
    cols_f = inv.a * xs + inv.b * ys + inv.c
    rows_f = inv.d * xs + inv.e * ys + inv.f
    r0 = np.round(rows_f - n / 2).astype(np.int64)
    c0 = np.round(cols_f - n / 2).astype(np.int64)
    inside = (r0 >= 0) & (c0 >= 0) & (r0 + n <= H) & (c0 + n <= W)

    off = np.arange(n)
    rr = np.clip(r0[:, None, None] + off[None, :, None], 0, H - 1)
    cc = np.clip(c0[:, None, None] + off[None, None, :], 0, W - 1)
    vals = ndwi[rr, cc]                      # shape (cells, n, n)
    vals[~inside] = np.nan
    obs = n_obs[rr, cc].astype("float32")
    obs[~inside] = 0.0

    valid = ~np.isnan(vals)
    count = valid.sum(axis=(1, 2))
    valid_frac = count / float(n * n)
    ok = valid_frac >= MIN_VALID_FRACTION
    sums = np.where(valid, vals, 0.0).sum(axis=(1, 2))
    ndwi_mean = np.where(ok, sums / np.maximum(count, 1), np.nan)
    water_px = ((vals > NDWI_WATER_THRESHOLD) & valid).sum(axis=(1, 2))
    water_area = np.where(ok, water_px * float(PIXEL_SIZE_M ** 2), np.nan)
    return ndwi_mean, water_area, valid_frac, obs.mean(axis=(1, 2))


def process_all_events():
    if not GRID_PARQUET.exists():
        raise SystemExit(f"{GRID_PARQUET} not found. Run grid/build_grid.py first.")
    grid = pd.read_parquet(GRID_PARQUET)

    token = _cdse_access_token()
    catalog = Client.open(CDSE_STAC_URL)
    bbox_by_region = {"melamchi": MELAMCHI_BBOX, "rasuwa": RASUWA_BBOX}

    all_rows = []
    for event_id, spec in EVENTS.items():
        if not spec.get("pre_window") or not spec.get("post_window"):
            log_skipped(dataset=f"sentinel2_{event_id}", reason=f"{event_id} has no pre/post window set")
            continue

        if spec["region"] != GRID_REGION:
            log_skipped(
                dataset=f"sentinel2_{event_id}",
                reason=(f"{event_id} is in region '{spec['region']}' but the grid covers "
                        f"'{GRID_REGION}' only; a scene there would not overlap the grid."),
            )
            print(f"{event_id}: skipped (different basin from the grid)")
            continue

        bbox = bbox_by_region[spec["region"]]
        window_results = {}
        for window_key in ("pre_window", "post_window"):
            w_start, w_end = spec[window_key]
            start_d = datetime.strptime(w_start, "%Y-%m-%d")
            end_d = datetime.strptime(w_end, "%Y-%m-%d")
            if window_key == "pre_window":     # never later than the window end
                s_from, s_to, anchor = start_d - timedelta(days=SEARCH_DAYS), end_d, end_d
            else:                              # never earlier than the window start
                s_from, s_to, anchor = start_d, end_d + timedelta(days=SEARCH_DAYS), start_d
            tiles, footprint = _find_scenes_covering_grid(catalog, bbox, s_from, s_to, anchor, grid)
            if not tiles:
                msg = (f"No Sentinel-2 scene under {MAX_CLOUD_COVER}% cloud cover between "
                       f"{s_from.date()} and {s_to.date()}")
                print(f"{event_id} {window_key}: SKIPPED - {msg}")
                log_skipped(dataset=f"sentinel2_{event_id}_{window_key}", reason=msg)
                window_results[window_key] = None
                continue
            print(f"{event_id} {window_key}: {len(tiles)} tile(s) needed to cover the grid "
                  f"({int(footprint.sum())} of {len(grid)} cells inside them); "
                  f"scenes searched {s_from.date()} -> {s_to.date()}")

            ndwi_all = water_all = vf_all = nobs_all = None
            used_dates = []
            for tile, items in tiles:
                arrays, tf0, crs0 = [], None, None
                for item in items:
                    print(f"  scene {item.id} "
                          f"({item.properties.get('eo:cloud_cover', '?')}% cloud, {item.properties['datetime']})")
                    try:
                        ndwi, transform, crs = _compute_ndwi_for_scene(
                            item, token, tag=f"{event_id}_{window_key}", grid=grid)
                    except RuntimeError as e:
                        # Don't lose the other scenes/tiles because one scene is unusable.
                        print(f"  SKIPPED this scene: {e}")
                        log_skipped(dataset=f"sentinel2_{event_id}_{window_key}", reason=str(e))
                        continue
                    if tf0 is not None and (transform != tf0 or ndwi.shape != arrays[0].shape):
                        print("  SKIPPED this scene: pixel grid differs from the other scenes of this tile")
                        continue
                    arrays.append(ndwi)
                    tf0, crs0 = transform, crs
                    used_dates.append(item.properties["datetime"][:10])
                if not arrays:
                    continue
                comp, n_obs = _composite(arrays)
                m, wa, vf, no = _sample_to_grid(comp, n_obs, tf0, crs0, grid)
                print(f"  tile {tile}: {len(arrays)} scene(s) composited, "
                      f"usable value for {int(np.isfinite(m).sum())} cells")
                if ndwi_all is None:
                    ndwi_all, water_all, vf_all, nobs_all = m, wa, vf, no
                else:
                    # fill only cells still empty; cells already covered keep the earlier tile's value
                    gap = np.isnan(ndwi_all) & np.isfinite(m)
                    ndwi_all = np.where(gap, m, ndwi_all)
                    water_all = np.where(gap, wa, water_all)
                    vf_all = np.where(gap, vf, vf_all)
                    nobs_all = np.where(gap, no, nobs_all)

            if ndwi_all is None:
                window_results[window_key] = None
                continue
            n_ok = int(np.isfinite(ndwi_all).sum())
            print(f"  ALL TILES COMBINED: real NDWI value for {n_ok} of {len(ndwi_all)} cells "
                  f"(needs >= {MIN_VALID_FRACTION:.0%} clear pixels per cell)")
            if n_ok < 0.5 * len(ndwi_all):
                print("  WARNING: fewer than half of the cells have data in this window - use with caution")
            window_results[window_key] = {
                "ndwi_mean": ndwi_all, "water_area": water_all,
                "valid_frac": vf_all, "n_obs": nobs_all,
                "scene_dates": ";".join(sorted(set(used_dates))),
                "date": end_d.strftime("%Y-%m-%d"),   # window end = observation date
            }

        pre, post = window_results.get("pre_window"), window_results.get("post_window")
        if pre is None and post is None:
            continue  # already logged both as skipped above

        for label, data in (("pre", pre), ("post", post)):
            if data is None:
                continue
            df = pd.DataFrame({
                "cell_id": grid["cell_id"].values,
                "event_id": event_id,
                "date": data["date"],
                "ndwi_mean": data["ndwi_mean"],
                "water_area": data["water_area"],
                "ndwi_valid_frac": np.round(data["valid_frac"], 2),
                "ndwi_n_obs": np.round(data["n_obs"], 1),
                "scene_dates": data["scene_dates"],
            })
            if pre is not None and post is not None:
                df["ndwi_change"] = (post["ndwi_mean"] - pre["ndwi_mean"]) if label == "post" else np.nan
                with np.errstate(divide="ignore", invalid="ignore"):
                    pct = np.where(pre["water_area"] > 0,
                                    (post["water_area"] - pre["water_area"]) / pre["water_area"] * 100,
                                    np.nan)
                df["water_area_change_pct"] = pct if label == "post" else np.nan
            else:
                df["ndwi_change"] = np.nan
                df["water_area_change_pct"] = np.nan
            all_rows.append(df)

    if not all_rows:
        raise SystemExit("No Sentinel-2 data produced for any event — see logged skips in metadata.csv.")

    result = pd.concat(all_rows, ignore_index=True)
    result.to_csv(OUT_CSV, index=False)
    print(f"Saved {len(result)} rows to {OUT_CSV}")

    log_metadata(
        dataset="sentinel2_ndwi",
        source="Sentinel-2 L2A (Copernicus Data Space Ecosystem STAC)",
        resolution="10m (B03, B08 native)",
        crs="per-scene UTM (see individual scene metadata), sampled to grid in EPSG:4326",
        processing=(
            f"Per tile, up to {N_SCENES_PER_TILE} least-cloudy scenes (< {MAX_CLOUD_COVER}% scene cloud) per window; "
            f"pre scenes not later than the window end, post scenes not earlier than the window start. "
            f"Pixels with SCL class in {list(SCL_INVALID)} (cloud, shadow, cirrus, snow/ice, no data) removed; "
            f"NDWI=(B03-B08)/(B03+B08) per clear pixel; per-pixel median composite; "
            f"water mask NDWI > {NDWI_WATER_THRESHOLD}; per 100 m cell mean/area only if >= {MIN_VALID_FRACTION:.0%} "
            f"of pixels clear; date = window end, scene_dates = acquisition dates used"
        ),
        notes="Some event/window combinations may be skipped if no clear scene was found — check metadata.csv skip entries.",
    )


if __name__ == "__main__":
    process_all_events()
