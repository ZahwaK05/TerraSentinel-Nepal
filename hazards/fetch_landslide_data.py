"""
Build historical-hazard features (historical_landslide_density,
distance_to_historical_landslide, distance_to_landslide_dam) and the
landslide_label target from a DATED landslide inventory, joined to the
project grid, once per event in config.EVENTS.

THIS IS A MANUAL-DOWNLOAD STEP - there is no authenticated API for Nepal-wide
landslide points, so place an inventory under data/raw/hazards/ first.

Likely sources (record the one you used in HAZARD_SOURCE_NOTE below):
  - NASA COOLR (Cooperative Open Online Landslide Repository), point-based,
    CSV/shapefile export: https://gpm.nasa.gov/landslides/
  - BIPAD Portal (Nepal DRR portal), incident records: https://bipadportal.gov.np
  - ICIMOD RDS - some landslide-dam layers

Expected input files (all shapefile parts, or geojson, or csv):
  data/raw/hazards/historical_landslides.(shp|geojson|csv)
      points or polygons, WITH a date column (event_date, date, landslide_date,
      incident_date, event_time, datetime or time; a full date, not just a year)
  data/raw/hazards/landslide_dams.(shp|geojson|csv)   (optional, also dated)

WHY DATES ARE REQUIRED (leakage rules, per event in config.EVENTS):
  history features  use only landslides dated on or before the END of the
                    event's pre_window - what was known before the event.
  landslide_label   uses only landslides dated AFTER the end of the pre_window
                    and up to the end of the post_window (or the start of it,
                    if LABEL_INCLUDES_POST_WINDOW is False).
The two sets never overlap. Without dates the label and the history features
would be built from the same points, and distance_to_historical_landslide
would simply reveal the label.

OUTPUT: one row per (event_id, cell_id), for events whose region matches the
grid's region (GRID_REGION). If an event has no landslide dated inside its
label window, its label is left EMPTY (NaN), never 0 - an all-zero label
would train the model that nothing happened. Filter those rows out before
training; they are still usable for inference.

GRID INPUT: data/processed/grid/grid_cells.parquet (cell_id, lat, lon).
"""
from pathlib import Path

import numpy as np
import geopandas as gpd
import pandas as pd
from shapely.geometry import Point

from config import (DATA_RAW, DATA_PROCESSED, CRS_GEOGRAPHIC, CRS_PROJECTED,
                    GRID_CELL_SIZE_M, EVENTS)
from utils_metadata import log_metadata, log_skipped

RAW_DIR = DATA_RAW / "hazards"
OUT_DIR = DATA_PROCESSED / "hazards"
RAW_DIR.mkdir(parents=True, exist_ok=True)
OUT_DIR.mkdir(parents=True, exist_ok=True)
OUT_CSV = OUT_DIR / "melamchi_hazards.csv"

GRID_PATH = DATA_PROCESSED / "grid" / "grid_cells.parquet"
GRID_ID_COL, GRID_LAT_COL, GRID_LON_COL = "cell_id", "lat", "lon"
GRID_REGION = "melamchi"  # only events with this region are built for this grid

LANDSLIDE_INPUT_CANDIDATES = [RAW_DIR / f"historical_landslides.{e}" for e in ("shp", "geojson", "csv")]
DAM_INPUT_CANDIDATES = [RAW_DIR / f"landslide_dams.{e}" for e in ("shp", "geojson", "csv")]
DATE_COL_CANDIDATES = ("event_date", "date", "landslide_date", "incident_date",
                       "event_time", "datetime", "time")

# True: label = landslides after pre_window end, up to the END of post_window
#       (the post-event composite covers the whole post window).
# False: label = only the gap between pre_window end and post_window start.
LABEL_INCLUDES_POST_WINDOW = True

# Fill in with the source you used - goes into metadata.csv.
HAZARD_SOURCE_NOTE = "TODO: record actual source (e.g. NASA COOLR export, BIPAD Portal query, date range)"

DENSITY_RADIUS_KM = 10.0  # matched to the location accuracy of news-based inventories (5-10 km)

# News-based catalogs (NASA GLC/COOLR) locate most landslides only to 1-50 km ("location_accuracy").
# Records less precise than this are dropped before any feature is built. None = keep everything.
MAX_LOCATION_ERROR_KM = 10.0

# Distance to the nearest past landslide is only meaningful if locations are far more precise than
# the 100 m grid. With km-level accuracy it is mostly noise and just encodes position, so it is off
# by default (logged as skipped). Set True for a precisely located inventory.
INCLUDE_DISTANCE_FEATURE = False


class UndatedInventory(Exception):
    """Raised when an inventory has no usable date column."""


def _load_grid() -> gpd.GeoDataFrame:
    if not GRID_PATH.exists():
        raise SystemExit(f"{GRID_PATH} not found. Run grid/build_grid.py first.")
    df = pd.read_parquet(GRID_PATH) if GRID_PATH.suffix == ".parquet" else pd.read_csv(GRID_PATH)
    missing = {GRID_ID_COL, GRID_LAT_COL, GRID_LON_COL} - set(df.columns)
    if missing:
        raise SystemExit(f"Grid file is missing expected column(s): {missing}")
    geometry = [Point(xy) for xy in zip(df[GRID_LON_COL], df[GRID_LAT_COL])]
    return gpd.GeoDataFrame(df, geometry=geometry, crs=CRS_GEOGRAPHIC)


def _find_input(candidates: list[Path]) -> Path | None:
    return next((p for p in candidates if p.exists()), None)


def _grid_spacing_m(grid_m: gpd.GeoDataFrame, sample: int = 200) -> float:
    """Median nearest-neighbour distance between cell centroids (sampled)."""
    x, y = grid_m.geometry.x.to_numpy(), grid_m.geometry.y.to_numpy()
    idx = np.random.default_rng(0).choice(len(x), size=min(sample, len(x)), replace=False)
    nearest = []
    for i in idx:
        d = np.hypot(x - x[i], y - y[i])
        d[i] = np.inf
        nearest.append(d.min())
    return float(np.median(nearest))


def _load_dated_points(path: Path, what: str) -> gpd.GeoDataFrame:
    """Load an inventory as points with a normalized `event_date` column."""
    if path.suffix.lower() == ".csv":
        df = pd.read_csv(path)
        lat = next((c for c in df.columns if c.lower() in ("lat", "latitude")), None)
        lon = next((c for c in df.columns if c.lower() in ("lon", "lng", "longitude")), None)
        if not lat or not lon:
            raise SystemExit(f"{path} has no recognizable lat/lon columns: {list(df.columns)}")
        gdf = gpd.GeoDataFrame(df, geometry=[Point(xy) for xy in zip(df[lon], df[lat])], crs=CRS_GEOGRAPHIC)
    else:
        gdf = gpd.read_file(path)
        if gdf.crs is None:
            raise SystemExit(f"{path} has no CRS defined.")
        gdf = gdf.to_crs(CRS_GEOGRAPHIC)

    if not (gdf.geometry.geom_type == "Point").all():  # polygons etc. -> one point each
        pts = gdf.to_crs(CRS_PROJECTED).geometry.representative_point()
        gdf["geometry"] = gpd.GeoSeries(pts, crs=CRS_PROJECTED).to_crs(CRS_GEOGRAPHIC)

    acc_col = next((c for c in gdf.columns if c.lower() == "location_accuracy" or c.lower().startswith("location_a")), None)
    if acc_col is not None and MAX_LOCATION_ERROR_KM is not None:
        err_km = gdf[acc_col].astype(str).str.lower().str.extract(r"([\d.]+)\s*km")[0].astype(float)
        err_km = err_km.where(~gdf[acc_col].astype(str).str.lower().str.contains("exact"), 0.0)
        keep = err_km <= MAX_LOCATION_ERROR_KM   # unknown / unparseable accuracy counts as too coarse
        print(f"  {what}: keeping {int(keep.sum())} of {len(gdf)} records located within "
              f"{MAX_LOCATION_ERROR_KM:g} km ('{acc_col}'); dropped {int((~keep).sum())} coarser/unknown.")
        gdf = gdf[keep].reset_index(drop=True)

    col = next((c for c in gdf.columns if c.lower() in DATE_COL_CANDIDATES), None)
    if col is None:
        raise UndatedInventory(f"{what} {path.name} has no date column; columns: {list(gdf.columns)}")
    if pd.api.types.is_numeric_dtype(gdf[col]):
        raise UndatedInventory(
            f"{what} {path.name}: date column '{col}' is numeric (year only?). "
            f"A full date is needed to place a landslide before or after each event."
        )
    dates = pd.to_datetime(gdf[col], errors="coerce", utc=True).dt.tz_convert(None).dt.normalize()
    n_bad = int(dates.isna().sum())
    gdf = gdf.assign(event_date=dates).dropna(subset=["event_date"]).reset_index(drop=True)
    print(f"Loaded {len(gdf)} dated {what} record(s) from {path} "
          f"({n_bad} dropped: missing or unparseable '{col}'). "
          f"Dates span {gdf.event_date.min().date()} to {gdf.event_date.max().date()}.")
    for c in gdf.columns:
        if "accu" in c.lower():
            print(f"  '{c}' values (records coarser than ~1 km cannot be placed in a "
                  f"{GRID_CELL_SIZE_M} m cell):\n{gdf[c].value_counts(dropna=False).to_string()}")
    return gdf


def _density(buffers: gpd.GeoDataFrame, pts_m: gpd.GeoDataFrame, radius_km: float) -> pd.Series:
    """Landslides per km^2 within radius_km of each cell centroid."""
    if len(pts_m) == 0:
        return pd.Series(0.0, index=buffers[GRID_ID_COL])
    joined = gpd.sjoin(pts_m[["geometry"]], buffers, predicate="within", how="inner")
    counts = joined.groupby(GRID_ID_COL).size()
    return buffers[GRID_ID_COL].map(counts).fillna(0).set_axis(buffers[GRID_ID_COL]) / (np.pi * radius_km ** 2)


def _distance(grid_m: gpd.GeoDataFrame, pts_m: gpd.GeoDataFrame) -> pd.Series:
    """Distance (m) from each cell centroid to the nearest point; NaN if no points."""
    if len(pts_m) == 0:
        return pd.Series(np.nan, index=grid_m[GRID_ID_COL])
    nearest = gpd.sjoin_nearest(grid_m[[GRID_ID_COL, "geometry"]], pts_m[["geometry"]], distance_col="dist_m")
    nearest = nearest.sort_values("dist_m").drop_duplicates(subset=GRID_ID_COL)
    return grid_m[GRID_ID_COL].map(nearest.set_index(GRID_ID_COL)["dist_m"]).set_axis(grid_m[GRID_ID_COL])


def _label(cells: gpd.GeoDataFrame, pts_m: gpd.GeoDataFrame) -> pd.Series:
    """1 if a label-window landslide falls inside the cell footprint, else 0."""
    hit = set(gpd.sjoin(pts_m[["geometry"]], cells, predicate="within", how="inner")[GRID_ID_COL])
    return cells[GRID_ID_COL].isin(hit).astype(int).set_axis(cells[GRID_ID_COL])


def _event_cutoffs(cfg: dict) -> tuple[pd.Timestamp, pd.Timestamp]:
    pre_end = pd.Timestamp(cfg["pre_window"][1])
    label_end = pd.Timestamp(cfg["post_window"][1 if LABEL_INCLUDES_POST_WINDOW else 0])
    return pre_end, label_end


def build_hazard_features():
    grid = _load_grid()
    grid_m = grid.to_crs(CRS_PROJECTED)
    ids = grid_m[GRID_ID_COL]

    # The label footprint should match the real grid spacing, not just the config value.
    spacing = _grid_spacing_m(grid_m)
    cell_size = GRID_CELL_SIZE_M
    if abs(spacing - GRID_CELL_SIZE_M) > 0.1 * GRID_CELL_SIZE_M:
        print(f"WARNING: grid centroids are ~{spacing:.0f} m apart but GRID_CELL_SIZE_M = "
              f"{GRID_CELL_SIZE_M}. Using {spacing:.0f} m for the label footprint so no landslide "
              f"falls in a gap between cells. Check grid/build_grid.py and config.")
        cell_size = spacing
    cells = gpd.GeoDataFrame({GRID_ID_COL: ids}, crs=CRS_PROJECTED,
                             geometry=grid_m.geometry.buffer(cell_size / 2, cap_style=3))
    buffers = gpd.GeoDataFrame({GRID_ID_COL: ids}, crs=CRS_PROJECTED,
                               geometry=grid_m.geometry.buffer(DENSITY_RADIUS_KM * 1000))

    events = {k: v for k, v in EVENTS.items() if v.get("region") == GRID_REGION}
    skipped = [k for k in EVENTS if k not in events]
    print(f"Building for {list(events)}; skipping {skipped} (different region than this grid).")

    ls_path, dam_path = _find_input(LANDSLIDE_INPUT_CANDIDATES), _find_input(DAM_INPUT_CANDIDATES)
    landslides = dams = None

    if ls_path is None:
        log_skipped(dataset="historical_hazards", reason=(
            "No landslide inventory under data/raw/hazards/ (expected "
            "historical_landslides.shp/.geojson/.csv). Download a dated one and re-run."))
        print("No landslide inventory found - skipping density, distance and label.")
    else:
        try:
            landslides = _load_dated_points(ls_path, "landslide")
        except UndatedInventory as e:
            log_skipped(dataset="historical_hazards", reason=str(e))
            print(f"SKIPPING landslide features and label: {e}")

    if dam_path is None:
        log_skipped(dataset="distance_to_landslide_dam",
                    reason="No landslide-dam inventory under data/raw/hazards/ (landslide_dams.*).")
        print("No landslide-dam inventory found - skipping distance_to_landslide_dam.")
    else:
        try:
            dams = _load_dated_points(dam_path, "landslide-dam")
        except UndatedInventory as e:
            log_skipped(dataset="distance_to_landslide_dam", reason=str(e))
            print(f"SKIPPING distance_to_landslide_dam: {e}")

    if landslides is None and dams is None:
        raise SystemExit("Nothing to write: no usable dated inventory. See messages above.")

    blocks, summary = [], []
    for event_id, cfg in events.items():
        pre_end, label_end = _event_cutoffs(cfg)
        block = pd.DataFrame({"event_id": event_id, GRID_ID_COL: ids.to_numpy()}).set_index(GRID_ID_COL, drop=False)
        row = {"event": event_id, "history<=": pre_end.date(), "label window": f"({pre_end.date()}, {label_end.date()}]"}

        if landslides is not None:
            hist = landslides[landslides.event_date <= pre_end]
            lab = landslides[(landslides.event_date > pre_end) & (landslides.event_date <= label_end)]
            assert (hist.event_date <= pre_end).all() and (lab.event_date > pre_end).all()  # no overlap
            hist_m, lab_m = hist.to_crs(CRS_PROJECTED), lab.to_crs(CRS_PROJECTED)

            block["historical_landslide_density"] = _density(buffers, hist_m, DENSITY_RADIUS_KM)
            if INCLUDE_DISTANCE_FEATURE:
                block["distance_to_historical_landslide"] = _distance(grid_m, hist_m)
            if len(lab) == 0:
                block["landslide_label"] = pd.array([pd.NA] * len(block), dtype="Int64")
                print(f"WARNING {event_id}: no landslide dated in {row['label window']}. Label left EMPTY "
                      f"(not 0). The inventory may not cover this event yet.")
                log_skipped(dataset=f"landslide_label_{event_id}", reason=(
                    f"No inventory landslide dated in {row['label window']}; label left empty."))
            else:
                block["landslide_label"] = _label(cells, lab_m).astype("Int64")
            pos = block["landslide_label"] == 1
            row.update({"history pts": len(hist), "label pts": len(lab), "positive cells": int(pos.sum()),
                        "positive rate": round(float(pos.mean()), 5) if len(lab) else np.nan})
            if len(lab) and len(hist) and pos.any() and "distance_to_historical_landslide" in block:
                d = block["distance_to_historical_landslide"]
                row.update({"median dist pos (m)": round(float(d[pos].median())),
                            "median dist neg (m)": round(float(d[~pos].median()))})

        if dams is not None:
            dh = dams[dams.event_date <= pre_end].to_crs(CRS_PROJECTED)
            block["distance_to_landslide_dam"] = _distance(grid_m, dh)
            row["dam pts"] = len(dh)
        blocks.append(block.reset_index(drop=True))
        summary.append(row)

    result = pd.concat(blocks, ignore_index=True)
    window_note = (f"history = inventory records dated <= pre_window end; label = records dated after "
                   f"pre_window end up to {'post_window end' if LABEL_INCLUDES_POST_WINDOW else 'post_window start'}; "
                   f"cell footprint {cell_size:.0f} m square; density radius {DENSITY_RADIUS_KM} km; "
                   f"records kept only if location error <= {MAX_LOCATION_ERROR_KM} km")
    if HAZARD_SOURCE_NOTE.startswith("TODO"):
        print("NOTE: HAZARD_SOURCE_NOTE still says TODO - fill it in so the source lands in metadata.csv.")
    if landslides is not None and not INCLUDE_DISTANCE_FEATURE:
        log_skipped(dataset="distance_to_historical_landslide", reason=(
            "Inventory locations are only accurate to km level (news-based), far coarser than the "
            "100 m grid; the distance would be noise. Set INCLUDE_DISTANCE_FEATURE = True for a precise inventory."))
    if landslides is not None:
        log_metadata(dataset="historical_landslide_features_and_label", source=str(ls_path),
                     resolution="dated point inventory, per event", crs=CRS_GEOGRAPHIC,
                     processing=window_note, notes=HAZARD_SOURCE_NOTE)
    if dams is not None:
        log_metadata(dataset="distance_to_landslide_dam", source=str(dam_path),
                     resolution="dated point inventory, per event", crs=CRS_GEOGRAPHIC,
                     processing="sjoin_nearest distance from cell centroid, dams dated <= pre_window end",
                     notes=HAZARD_SOURCE_NOTE)

    result.to_csv(OUT_CSV, index=False)
    print(f"Saved {len(result)} rows ({result.event_id.nunique()} event(s) x {len(ids)} cells) to {OUT_CSV}")
    print(pd.DataFrame(summary).to_string(index=False))
    print("If 'median dist pos' is near 0, history and label share records (duplicates or "
          "reactivations) - inspect before training.")


if __name__ == "__main__":
    build_hazard_features()
