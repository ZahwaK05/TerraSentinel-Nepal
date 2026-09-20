"""
Merge all processed TerraSentinel tables into ONE feature table laid out
exactly as in the brief (section 10).

Run from the project root (your TerraSentinel-Nepal folder):
    python merge/merge_features.py
    python merge/merge_features.py --region rasuwa
    python merge/merge_features.py --src rainfall=data/processed/rainfall/melamchi_rainfall.csv

Rules kept from the brief:
- Never fabricate: no data -> NaN; columns with no data at all are NOT written.
- event_id is always kept (no mixing of Melamchi 2021 / Melamchi 2026 / Rasuwa 2026).
- Duplicate keys raise an error instead of being collapsed.
- Every dropped / never-produced column is logged to metadata.csv via log_skipped.

Outputs (data/processed/):
    melamchi_features.parquet / .csv   the ML table (region=melamchi)
    <region>_features.parquet / .csv   same, for any other region (never overwrites melamchi)
    merge_report.csv                   column, source table, % non-null
    missing_columns.txt                brief columns that could not be produced

Changes vs the first version:
- logs skipped columns/tables and the final table to metadata.csv (utils_metadata)
- other regions write to their own files instead of overwriting melamchi_features.*
- window-end dates from config.EVENTS may be strings OR date/datetime objects
- CRS_PROJECTED and EVENTS[...]["region"] are optional in config.py (fallbacks + warning)
"""
import argparse
import logging
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import config  # noqa: E402
from config import (  # noqa: E402
    DATA_PROCESSED,
    EVENTS,
    FEATURE_TABLE_CSV,
    FEATURE_TABLE_PARQUET,
)
from utils_metadata import log_metadata, log_skipped  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
log = logging.getLogger("merge")

# Projected CRS used only to compute centroids if the grid has no lat/lon columns.
# UTM 45N covers the Melamchi / Helambu area; override by defining CRS_PROJECTED in config.py.
CRS_PROJECTED = getattr(config, "CRS_PROJECTED", None)
if CRS_PROJECTED is None:
    CRS_PROJECTED = "EPSG:32645"
    log.warning("config.CRS_PROJECTED not defined; falling back to %s for centroid computation", CRS_PROJECTED)


def _region_of(event_id, cfg):
    """Region tag for an event: config value if present, else the event_id prefix."""
    return cfg.get("region") or event_id.split("_")[0].lower()


REGION_OF = {e: _region_of(e, c) for e, c in EVENTS.items()}

# Column layout requested in the brief, in order.
BRIEF_COLUMNS = [
    "cell_id", "event_id", "date", "latitude", "longitude",
    "rainfall_1h", "rainfall_3h", "rainfall_6h", "rainfall_12h",
    "rainfall_24h", "rainfall_3day", "rainfall_7day",
    "elevation", "slope", "aspect", "curvature", "flow_accumulation",
    "distance_to_river", "river_gradient",
    "ndwi_mean", "ndwi_change", "water_area", "water_area_change_pct",
    "sar_change", "displacement", "displacement_change",
    "historical_landslide_density", "distance_to_historical_landslide",
    "distance_to_landslide_dam",
    "distance_to_glacial_lake", "glacial_lake_area", "glacial_lake_area_change",
    "landslide_label",  # ML target, from the hazards step
]

# ---- EDIT HERE if needed (or use --src name=path) ---------------------------
SOURCES = {
    "grid": ["*grid*"],
    "terrain": ["*terrain*"],
    "hazards": ["*hazard*", "*landslide*"],
    "glacial_lakes": ["*glacial*"],
    "rainfall": ["*rainfall*"],
    "ndwi": ["*ndwi*", "*sentinel2*", "*s2_*"],
    "sar": ["*sar_*", "*sentinel1*", "*s1_*"],
}
EVENT_KEYS = ["cell_id", "event_id", "window"]
# Never pick up our own outputs as inputs.
SKIP_NAMES = tuple({"melamchi_features", "merge_report", "missing_columns"}
                   | {f"{r}_features" for r in REGION_OF.values()})
# -----------------------------------------------------------------------------


def _out_paths(region):
    """melamchi keeps the config paths; every other region gets its own files."""
    if region == "melamchi":
        return FEATURE_TABLE_CSV, FEATURE_TABLE_PARQUET, "merge_report.csv", "missing_columns.txt"
    return (
        FEATURE_TABLE_CSV.with_name(f"{region}_features.csv"),
        FEATURE_TABLE_PARQUET.with_name(f"{region}_features.parquet"),
        f"merge_report_{region}.csv",
        f"missing_columns_{region}.txt",
    )


def _find(name, patterns):
    exts = (".parquet", ".csv") + ((".gpkg",) if name == "grid" else ())
    for pat in patterns:
        for ext in exts:
            hits = []
            for h in sorted(DATA_PROCESSED.rglob(pat + ext)):
                if h.name.startswith("_") or "DO_NOT_USE" in h.name:
                    continue
                if h.name.startswith(SKIP_NAMES):
                    continue
                hits.append(h)
            if hits:
                if len(hits) > 1:
                    log.warning("%s: several files match, using %s (others: %s)",
                                name, hits[-1].name, [h.name for h in hits[:-1]])
                return hits[-1]
    return None


def _load(path, name):
    if path.suffix == ".gpkg":
        import geopandas as gpd
        df = gpd.read_file(path)
    elif path.suffix == ".parquet":
        try:
            import geopandas as gpd
            df = gpd.read_parquet(path)  # works for GeoParquet
        except Exception:
            df = pd.read_parquet(path)
    else:
        df = pd.read_csv(path)
    if "cell_id" not in df.columns:
        raise KeyError(f"{path.name} has no 'cell_id' column")
    df = df.rename(columns={"date": "obs_date", "observation_date": "obs_date"})
    if name != "grid" and "geometry" in df.columns:
        df = df.drop(columns="geometry")
    return df


def _latlon(grid):
    """Return grid with latitude/longitude columns, or warn if impossible."""
    low = {c.lower(): c for c in grid.columns}
    for la, lo in [("latitude", "longitude"), ("lat", "lon"), ("lat", "lng"),
                   ("centroid_lat", "centroid_lon")]:
        if la in low and lo in low:
            return grid.rename(columns={low[la]: "latitude", low[lo]: "longitude"})
    crs = getattr(grid, "crs", None)
    if "geometry" in grid.columns and crs is not None:
        cen = grid.geometry.to_crs(CRS_PROJECTED).centroid.to_crs("EPSG:4326")
        grid = pd.DataFrame(grid.drop(columns="geometry"))
        grid["latitude"], grid["longitude"] = cen.y.values, cen.x.values
        log.info("latitude/longitude computed from grid geometry centroids")
        return grid
    log.warning("grid has no latitude/longitude columns and no usable geometry -> "
                "those two columns will be MISSING. Add centroid lat/lon to the grid file.")
    return grid


def _norm_date(x):
    """Normalise str / date / datetime / Timestamp to 'YYYY-MM-DD'."""
    return pd.to_datetime(x).strftime("%Y-%m-%d")


def _add_window(df, name):
    """Map obs_date -> pre/post using the window end dates in config.EVENTS."""
    if "window" in df.columns or "obs_date" not in df.columns:
        return df
    lookup = {}
    for ev, cfg in EVENTS.items():
        for w in ("pre", "post"):
            span = cfg.get(f"{w}_window")
            if span:
                lookup[(ev, _norm_date(span[1]))] = w
    dates = pd.to_datetime(df["obs_date"]).dt.strftime("%Y-%m-%d")
    df = df.copy()
    df["window"] = [lookup.get((e, d)) for e, d in zip(df["event_id"], dates)]
    unmatched = df["window"].isna().to_numpy()
    if unmatched.any():
        sample = sorted(set(zip(df["event_id"][unmatched], dates[unmatched])))[:5]
        log.warning("%s: %d rows have an obs_date matching no window end in config.EVENTS "
                    "(examples: %s)", name, int(unmatched.sum()), sample)
    return df


def _check_unique(df, keys, name):
    dup = df.duplicated(keys).sum()
    if dup:
        raise ValueError(f"{name}: {dup} duplicate rows on keys {keys}. Fix upstream, not here.")


def _suffix_clashes(df, seen, name):
    clash = (set(df.columns) & seen) - set(EVENT_KEYS)
    if clash:
        log.warning("%s: column clash %s -> suffixed _%s", name, sorted(clash), name)
        df = df.rename(columns={c: f"{c}_{name}" for c in clash})
    return df


def main(region, overrides):
    region_events = {e for e, r in REGION_OF.items() if r == region}
    if not region_events:
        raise SystemExit(f"No events with region '{region}' in config.EVENTS")
    out_csv, out_parquet, report_name, missing_name = _out_paths(region)

    tables, missing = {}, []
    for name, pats in SOURCES.items():
        path = Path(overrides[name]) if name in overrides else _find(name, pats)
        if path is None:
            log.warning("MISSING table %-14s (patterns %s under %s)", name, pats, DATA_PROCESSED)
            missing.append(name)
            log_skipped(dataset=f"{name}_in_final_table",
                        reason=f"{name} processed output not found at merge time")
            continue
        tables[name] = _load(path, name)
        log.info("loaded  %-14s %-40s rows=%d", name, path.name, len(tables[name]))

    if "grid" not in tables:
        raise SystemExit("Grid table is required and was not found.")

    grid = _latlon(tables.pop("grid"))
    _check_unique(grid, ["cell_id"], "grid")
    if "geometry" in grid.columns:
        grid = pd.DataFrame(grid.drop(columns="geometry"))
    n_cells = len(grid)
    source_of = {c: "grid" for c in grid.columns}
    seen = set(grid.columns)

    static = {n: d for n, d in tables.items() if "event_id" not in d.columns}
    event = {n: d for n, d in tables.items() if "event_id" in d.columns}

    out = grid
    for name, df in static.items():
        _check_unique(df, ["cell_id"], name)
        orphans = (~df["cell_id"].isin(grid["cell_id"])).sum()
        if orphans:
            log.warning("%s: %d cell_ids not in grid (dropped)", name, orphans)
        df = _suffix_clashes(df, seen, name)
        source_of.update({c: name for c in df.columns if c != "cell_id"})
        seen |= set(df.columns)
        out = out.merge(df, on="cell_id", how="left")
        log.info("static  %-14s covers %.1f%% of grid cells", name,
                 100 * df["cell_id"].isin(grid["cell_id"]).sum() / n_cells)

    ev = None
    for name, df in event.items():
        dropped = df[~df["event_id"].isin(region_events)]["event_id"].unique()
        if len(dropped):
            log.info("%s: ignoring events from other regions: %s", name, sorted(dropped))
        df = df[df["event_id"].isin(region_events)]
        if df.empty:
            log.warning("%s: no rows for region '%s'", name, region)
            log_skipped(dataset=f"{name}_in_final_table",
                        reason=f"{name} has no rows for region '{region}'")
            continue
        df = _add_window(df, name)
        keys = [k for k in EVENT_KEYS if k in df.columns]
        _check_unique(df, keys, name)
        df = _suffix_clashes(df, seen, name)
        source_of.update({c: name for c in df.columns if c not in EVENT_KEYS and c != "obs_date"})
        seen |= set(df.columns)
        if ev is None:
            ev = df
        else:
            shared = [k for k in EVENT_KEYS if k in ev.columns and k in df.columns]
            if "obs_date" in df.columns and "obs_date" in ev.columns:
                df = df.rename(columns={"obs_date": f"obs_date_{name}"})
            ev = ev.merge(df, on=shared, how="outer")
        log.info("event   %-14s events=%s", name, sorted(df["event_id"].unique()))

    if ev is not None:
        orphans = (~ev["cell_id"].isin(grid["cell_id"])).sum()
        if orphans:
            log.warning("event tables: %d rows with cell_id not in this grid (dropped)", orphans)
        out = out.merge(ev, on="cell_id", how="inner")  # only cells that have event rows
    else:
        log.warning("No event tables found: output has no event_id/date.")

    if "obs_date" in out.columns:
        out = out.rename(columns={"obs_date": "date"})
        source_of["date"] = "rainfall/event tables"

    # drop columns with no data at all (never fabricate)
    keep_always = set(EVENT_KEYS) | {"date"}
    empty = [c for c in out.columns if c not in keep_always and out[c].isna().all()]
    if empty:
        log.warning("dropping 100%% empty columns: %s", empty)
        for c in empty:
            log_skipped(dataset=f"column_{c}",
                        reason=f"'{c}' exists but is empty for every row — dropped rather than kept as all-NaN")
        out = out.drop(columns=empty)

    # column layout exactly as the brief, extras (window, x, y, ...) at the end
    front = [c for c in BRIEF_COLUMNS if c in out.columns]
    out = out[front + [c for c in out.columns if c not in front]]
    sort_keys = [c for c in ("event_id", "date", "cell_id") if c in out.columns]
    out = out.sort_values(sort_keys).reset_index(drop=True)

    out_csv.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(out_csv, index=False)
    out.to_parquet(out_parquet, index=False)

    report = pd.DataFrame({
        "column": out.columns,
        "source": [source_of.get(c, "key") for c in out.columns],
        "non_null_pct": [round(100 * out[c].notna().mean(), 1) for c in out.columns],
    })
    report.to_csv(DATA_PROCESSED / report_name, index=False)

    absent = [c for c in BRIEF_COLUMNS if c not in out.columns]
    with open(DATA_PROCESSED / missing_name, "w") as f:
        f.write(f"Brief columns NOT in {out_parquet.name} (region={region}):\n")
        f.write("\n".join(f"- {c}" for c in absent) or "(none)")
        f.write("\n\nMissing source tables: " + (", ".join(missing) or "(none)") + "\n")

    # log brief columns that no upstream table produced (empty ones were logged above)
    for c in absent:
        if c not in empty:
            log_skipped(dataset=f"column_{c}",
                        reason=f"'{c}' was never produced by any upstream table (region={region})")

    log_metadata(
        dataset=f"{region}_features_final",
        source="Merged from grid, terrain, rainfall, sentinel2, sentinel1, hazards, glacial_lakes outputs",
        resolution="100m grid (see grid_cells metadata for source resolutions per layer)",
        crs="EPSG:4326 (latitude/longitude)",
        processing=("Static layers left-joined on cell_id; per-event layers merged on "
                    "cell_id+event_id(+window) and inner-joined to the grid; duplicate keys raise"),
        notes=f"region={region}; {len(out)} rows, {len(out.columns)} columns; "
              f"{len(BRIEF_COLUMNS) - len(absent)}/{len(BRIEF_COLUMNS)} brief columns present. "
              f"See metadata.csv skip entries for the rest.",
    )

    log.info("wrote %s: %d rows x %d cols", out_parquet.name, *out.shape)
    log.info("brief columns present: %d/%d", len(BRIEF_COLUMNS) - len(absent), len(BRIEF_COLUMNS))
    if absent:
        log.warning("brief columns still missing: %s", absent)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--region", default="melamchi", choices=sorted(set(REGION_OF.values())))
    ap.add_argument("--src", action="append", default=[], metavar="NAME=PATH",
                    help="explicit file for a table, e.g. rainfall=data/processed/rainfall/melamchi_rainfall.csv")
    a = ap.parse_args()
    main(a.region, dict(s.split("=", 1) for s in a.src))
