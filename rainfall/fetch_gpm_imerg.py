"""
Fetch NASA GPM IMERG half-hourly precipitation and derive the cumulative
rainfall features (rainfall_1h ... rainfall_7day) requested in
data_dictionary.txt, sampled onto the project grid.

Requires: EARTHDATA_USERNAME / EARTHDATA_PASSWORD in .env (same Earthdata
account used by dem/fetch_dem.py).

GRID INPUT
----------
Reads data/processed/grid/grid_cells.parquet (columns: cell_id, lat, lon),
the output of grid/build_grid.py. If the boundary changes, rebuild the grid
and re-run this script (raw IMERG downloads are cached, so re-running is
cheap).

IMERG RUN SELECTION
-------------------
For each observation date the script tries the Final run first
(GPM_3IMERGHH, gauge-adjusted, ~3.5 month latency), then falls back to the
Late run (GPM_3IMERGHHL, ~14 hour latency, no gauge calibration). One run is
used for the WHOLE 7-day window of an observation date (never mixed inside a
window), and the run used is written to the `imerg_run` column so downstream
users know which rows are Final and which are Late. If neither run has a
complete window, that observation date is skipped and logged, not guessed.

WINDOW DEFINITION
-----------------
An observation date such as 2021-06-10 means 2021-06-10 00:00 UTC. Every
rainfall_Xh window covers the X hours BEFORE that instant, i.e.
[obs - X h, obs). Rain that falls on the observation date itself is not
counted.

MISSING DATA
------------
IMERG fill values (negative numbers, e.g. -9999.9) are treated as missing,
not zero. If any half-hour granule inside a window is missing, that window's
value for that cell is NaN rather than a partial sum or a zero.

WHAT THIS SCRIPT PRODUCES
-------------------------
One row per (cell_id, event_id, date) in
data/processed/rainfall/melamchi_rainfall.csv. Only events in config.EVENTS
with both pre_window and post_window set are processed.

NOTE: IMERG is ~0.1 deg (~10 km). A ~320 km2 watershed only covers a handful
of IMERG pixels, so rainfall features will show very little variation across
100 m grid cells. That is a real property of the source data.
"""
import re
import warnings
from datetime import datetime, timedelta, timezone
from pathlib import Path

warnings.filterwarnings("ignore", category=FutureWarning, module="earthaccess")

import h5py
import numpy as np
import pandas as pd
from dotenv import load_dotenv
from scipy.spatial import cKDTree
import earthaccess

from config import (
    EVENTS,
    DATA_RAW,
    DATA_PROCESSED,
    RAINFALL_WINDOWS_HOURS,
    CRS_GEOGRAPHIC,
    MELAMCHI_BBOX,
    RASUWA_BBOX,
)
from utils_metadata import log_metadata, log_skipped

load_dotenv()

RAW_DIR = DATA_RAW / "rainfall"
OUT_DIR = DATA_PROCESSED / "rainfall"
RAW_DIR.mkdir(parents=True, exist_ok=True)
OUT_DIR.mkdir(parents=True, exist_ok=True)
OUT_CSV = OUT_DIR / "melamchi_rainfall.csv"

GRID_PATH = DATA_PROCESSED / "grid" / "grid_cells.parquet"
GRID_ID_COL, GRID_LAT_COL, GRID_LON_COL = "cell_id", "lat", "lon"

# (short_name, label) in order of preference
IMERG_PRODUCTS = (
    ("GPM_3IMERGHH", "Final"),
    ("GPM_3IMERGHHL", "Late"),
)
IMERG_VERSION = "07"
IMERG_VAR_PATH = "Grid/precipitation"  # mm/hr (V07 name; was precipitationCal in V06)
MAX_WINDOW_HOURS = max(RAINFALL_WINDOWS_HOURS.values())  # 168h = 7 days
EXPECTED_GRANULES = int(round(MAX_WINDOW_HOURS * 2))  # half-hourly


def _load_grid() -> pd.DataFrame:
    if not GRID_PATH.exists():
        raise SystemExit(
            f"Grid file not found at {GRID_PATH}. Run grid/build_grid.py first."
        )
    grid = pd.read_parquet(GRID_PATH)
    missing = {GRID_ID_COL, GRID_LAT_COL, GRID_LON_COL} - set(grid.columns)
    if missing:
        raise SystemExit(f"Grid file is missing expected column(s): {missing}")
    return grid


def _login():
    auth = earthaccess.login(strategy="environment")
    if not auth.authenticated:
        raise SystemExit(
            "Earthdata login failed. Check EARTHDATA_USERNAME/PASSWORD in .env."
        )
    return auth


def _granule_timestamp(filename: str) -> datetime:
    """IMERG half-hourly filenames embed a UTC start time, e.g.
    3B-HHR.MS.MRG.3IMERG.20210615-S013000-E015959.0090.V07B.HDF5
    3B-HHR-L.MS.MRG.3IMERG.20260701-S000000-E002959.0000.V07B.HDF5"""
    m = re.search(r"\.(\d{8})-S(\d{6})-E\d{6}\.", filename)
    if not m:
        raise ValueError(f"Could not parse timestamp from IMERG filename: {filename}")
    date_str, start_str = m.groups()
    return datetime.strptime(date_str + start_str, "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)


def _find_granules(end_date: datetime, bbox):
    """Search Final, then Late. Return (results, run_label) for the first
    product that covers the whole lookback window, or None."""
    start = end_date - timedelta(hours=MAX_WINDOW_HOURS)
    temporal = (
        start.strftime("%Y-%m-%d %H:%M:%S"),
        end_date.strftime("%Y-%m-%d %H:%M:%S"),
    )
    for short_name, run in IMERG_PRODUCTS:
        results = earthaccess.search_data(
            short_name=short_name,
            version=IMERG_VERSION,
            temporal=temporal,
            bounding_box=bbox,
        )
        n = len(results)
        print(f"  {run} run ({short_name}): {n} granule(s) found, need >= {EXPECTED_GRANULES}")
        if n >= EXPECTED_GRANULES:
            return results, run
    return None


def _on_disk(name: str) -> bool:
    p = RAW_DIR / name
    return p.exists() and p.stat().st_size > 0


def _download(results) -> list[Path]:
    """Download only granules not already on disk, and never block forever.

    The download runs in a daemon thread with a timeout. Granules that are
    still missing afterwards are reported and left out; _accumulate_windows
    then sets every window that needs them to NaN. Nothing is guessed."""
    import threading

    wanted = {}  # filename -> search result
    for r in results:
        for link in r.data_links():
            if link.lower().endswith((".hdf5", ".h5")):
                wanted[link.rsplit("/", 1)[-1]] = r

    todo = {id(r): r for name, r in wanted.items() if not _on_disk(name)}
    if todo:
        timeout_s = 120 + 15 * len(todo)
        print(f"  {len(todo)} file(s) to download (timeout {timeout_s}s)...")

        def _worker():
            try:
                earthaccess.download(list(todo.values()), str(RAW_DIR))
            except Exception as exc:  # keep going; missing files handled below
                print(f"  download error: {exc}")

        t = threading.Thread(target=_worker, daemon=True)
        t.start()
        t.join(timeout_s)
        if t.is_alive():
            print("  WARNING: download timed out; continuing without unfinished file(s).")
    else:
        print("  All granules already on disk, nothing to download.")

    paths = sorted(RAW_DIR / n for n in wanted if _on_disk(n))
    still_missing = sorted(n for n in wanted if not _on_disk(n))
    if still_missing:
        msg = (
            f"{len(still_missing)} IMERG granule(s) unavailable, e.g. {still_missing[0]}. "
            f"Windows that need them are set to NaN."
        )
        print(f"  WARNING: {msg}")
        log_skipped(dataset="rainfall_missing_granules", reason=msg)
    return paths


def _read_granule_frame(path: Path, bbox) -> pd.DataFrame:
    """Read one IMERG granule into a long DataFrame of
    (lon, lat, precip_mm, timestamp) clipped to bbox. Fill values -> NaN."""
    minx, miny, maxx, maxy = bbox
    with h5py.File(path, "r") as f:
        precip = f[IMERG_VAR_PATH][0].astype("float64")  # (lon, lat), mm/hr
        lons = f["Grid/lon"][:]
        lats = f["Grid/lat"][:]

    lon_mask = (lons >= minx) & (lons <= maxx)
    lat_mask = (lats >= miny) & (lats <= maxy)
    sub = precip[np.ix_(lon_mask, lat_mask)]
    sub = np.where(sub < 0, np.nan, sub)  # fill value (-9999.9) is missing, NOT zero

    lon_grid, lat_grid = np.meshgrid(lons[lon_mask], lats[lat_mask], indexing="ij")
    df = pd.DataFrame({
        "lon": lon_grid.ravel(),
        "lat": lat_grid.ravel(),
        # HH product is mm/hr; each granule spans 30 min -> mm = rate * 0.5
        "precip_mm": sub.ravel() * 0.5,
    })
    df["timestamp"] = _granule_timestamp(path.name)
    return df


def _accumulate_windows(granule_frames: list[pd.DataFrame], end_date: datetime) -> pd.DataFrame:
    """Sum precip_mm per (lat, lon) over each lookback window [end - X h, end).
    A window value is NaN unless every expected half-hour granule was valid."""
    all_precip = pd.concat(granule_frames, ignore_index=True)
    # Granule starting exactly at end_date covers time AFTER the window
    all_precip = all_precip[all_precip["timestamp"] < end_date]

    out = None
    for col_name, hours in RAINFALL_WINDOWS_HOURS.items():
        window_start = end_date - timedelta(hours=hours)
        expected = int(round(hours * 2))
        sel = all_precip[all_precip["timestamp"] >= window_start]
        agg = (
            sel.groupby(["lat", "lon"])["precip_mm"]
            .agg(total="sum", n_valid="count")
            .reset_index()
        )
        agg[col_name] = agg["total"].where(agg["n_valid"] == expected)
        agg = agg[["lat", "lon", col_name]]
        out = agg if out is None else out.merge(agg, on=["lat", "lon"], how="outer")
    return out.reset_index(drop=True)


def _sample_to_grid(imerg_df: pd.DataFrame, grid: pd.DataFrame) -> pd.DataFrame:
    """Nearest-neighbor join: each grid cell gets the accumulation values
    of its nearest IMERG (~0.1deg) cell. NaN stays NaN."""
    tree = cKDTree(imerg_df[["lon", "lat"]].to_numpy())
    _, idx = tree.query(grid[[GRID_LON_COL, GRID_LAT_COL]].to_numpy(), k=1)

    value_cols = [c for c in imerg_df.columns if c not in ("lat", "lon")]
    sampled = imerg_df.iloc[idx][value_cols].reset_index(drop=True)
    return pd.concat([grid[[GRID_ID_COL]].reset_index(drop=True), sampled], axis=1)


def _process_observation_date(event_id: str, bbox, obs_date: datetime, grid: pd.DataFrame):
    print(f"Processing {event_id} observation date {obs_date.date()}...")
    found = _find_granules(obs_date, bbox)
    if found is None:
        reason = (
            f"No complete {EXPECTED_GRANULES}-granule IMERG window (Final or Late) "
            f"ending {obs_date.date()}; data likely not yet released."
        )
        log_skipped(dataset=f"rainfall_{event_id}_{obs_date.date()}", reason=reason)
        print(f"  SKIPPED: {reason}")
        return None

    results, run = found
    print(f"  Using {run} run. Downloading (existing files are skipped)...")
    granule_paths = _download(results)
    frames = [_read_granule_frame(p, bbox) for p in granule_paths]
    windows = _accumulate_windows(frames, obs_date)
    sampled = _sample_to_grid(windows, grid)
    sampled["event_id"] = event_id
    sampled["date"] = obs_date.date().isoformat()
    sampled["imerg_run"] = run
    return sampled


def fetch_all_events():
    _login()
    grid = _load_grid()
    bbox_by_region = {"melamchi": MELAMCHI_BBOX, "rasuwa": RASUWA_BBOX}

    all_rows = []
    runs_used = {}
    for event_id, spec in EVENTS.items():
        if not spec.get("pre_window") or not spec.get("post_window"):
            log_skipped(
                dataset=f"rainfall_{event_id}",
                reason=f"{event_id} has no pre_window/post_window set in config.py yet",
            )
            print(f"Skipping {event_id}: pre/post window not yet defined in config.py.")
            continue

        bbox = bbox_by_region[spec["region"]]
        for window_key in ("pre_window", "post_window"):
            _, window_end = spec[window_key]
            obs_date = datetime.strptime(window_end, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            rows = _process_observation_date(event_id, bbox, obs_date, grid)
            if rows is not None:
                all_rows.append(rows)
                runs_used[f"{event_id}@{obs_date.date()}"] = rows["imerg_run"].iloc[0]

    if not all_rows:
        raise SystemExit("No observation dates could be processed - nothing to save.")

    result = pd.concat(all_rows, ignore_index=True)
    result.to_csv(OUT_CSV, index=False)
    print(f"Saved {len(result)} rows to {OUT_CSV}")
    n_nan = int(result[list(RAINFALL_WINDOWS_HOURS)].isna().any(axis=1).sum())
    if n_nan:
        print(f"WARNING: {n_nan} rows have at least one NaN rainfall value (missing IMERG data).")

    log_metadata(
        dataset="rainfall_gpm_imerg",
        source="NASA GPM IMERG Half-Hourly v07 (GES DISC / Earthdata); Final run preferred, Late run fallback",
        resolution="~0.1 deg (~10km) native, sampled to grid via nearest-neighbor",
        crs=CRS_GEOGRAPHIC,
        processing=(
            "Downloaded half-hourly Grid/precipitation granules per observation date, "
            "fill values treated as missing, summed over [obs - X h, obs) into "
            "rainfall_1h..rainfall_7day (NaN if any granule in the window is missing), "
            "nearest-neighbor sampled onto the project grid"
        ),
        notes=f"IMERG run used per observation date: {runs_used}",
    )


if __name__ == "__main__":
    import os
    import sys

    fetch_all_events()
    # earthaccess leaves worker threads that can block a normal interpreter
    # exit (and Ctrl+C). All outputs are written by now, so exit immediately.
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(0)
