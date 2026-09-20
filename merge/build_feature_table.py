"""
Merge every processed layer into the final ML feature table:
  melamchi_features.csv / melamchi_features.parquet

Join strategy:
  - Backbone = rainfall table (cell_id, event_id, date) — this is the only
    layer that's naturally per-event-per-date, so every other row hangs
    off it. If rainfall is missing entirely, falls back to building the
    backbone from grid x EVENTS with real windows instead (2 rows per
    event: pre/post), so the table isn't empty just because rainfall
    hasn't been run.
  - Terrain (static per cell_id) — left-joined on cell_id, replicated
    across every event/date row for that cell.
  - Hazards (static per cell_id: historical_landslide_density,
    distance_to_historical_landslide, distance_to_landslide_dam,
    landslide_label) — left-joined on cell_id.
  - Glacial lakes (static per cell_id) — left-joined on cell_id.
  - Sentinel-2 (per cell_id + event_id) — left-joined on [cell_id, event_id].
    NOTE: Sentinel-2/Sentinel-1 features are per-EVENT (one pre/post change
    value), not per-observation-date like rainfall; when joined onto the
    rainfall backbone (which has 2 date-rows per event), the same
    ndwi_change/sar_change value is repeated on both the pre and post date
    rows for that event — this is intentional, not a bug: those are
    change features that only have one meaningful value per event, but
    the table structure was specified as per-date.
  - Sentinel-1 (per cell_id + event_id) — left-joined on [cell_id, event_id].

Any column that ends up ENTIRELY NaN across the whole table (meaning that
data source was never produced for any event) is dropped from the final
table and logged via log_skipped — per the project's "don't fabricate,
don't leave fake placeholder columns" rule. Columns with SOME missing
values (e.g. one event's Sentinel-2 got skipped but others didn't) are
kept as-is with NaN for the missing rows — that's honest missingness, not
fabrication.

Run this LAST, after grid, terrain, rainfall, sentinel2, sentinel1,
hazards, glacial_lakes have all been run (run whichever subset you have —
this script works with partial inputs and just skips/logs what's absent).
"""
import pandas as pd

from config import (
    DATA_PROCESSED, FEATURE_TABLE_CSV, FEATURE_TABLE_PARQUET, EVENTS,
)
from utils_metadata import log_metadata, log_skipped

GRID_PARQUET = DATA_PROCESSED / "grid" / "grid_cells.parquet"
TERRAIN_PARQUET = DATA_PROCESSED / "dem" / "terrain_features.parquet"
RAINFALL_CSV = DATA_PROCESSED / "rainfall" / "melamchi_rainfall.csv"
SENTINEL2_CSV = DATA_PROCESSED / "sentinel2" / "melamchi_sentinel2.csv"
SENTINEL1_CSV = DATA_PROCESSED / "sentinel1" / "melamchi_sentinel1.csv"
HAZARDS_CSV = DATA_PROCESSED / "hazards" / "melamchi_hazards.csv"
GLACIAL_LAKES_CSV = DATA_PROCESSED / "glacial_lakes" / "melamchi_glacial_lakes.csv"

# Full column spec from the project brief — used only to decide what to
# report as "not produced" at the end, never to fabricate values for them.
SPEC_COLUMNS = [
    "cell_id", "event_id", "date", "latitude", "longitude",
    "rainfall_1h", "rainfall_3h", "rainfall_6h", "rainfall_12h", "rainfall_24h", "rainfall_3day", "rainfall_7day",
    "elevation", "slope", "aspect", "curvature", "flow_accumulation", "distance_to_river", "river_gradient",
    "ndwi_mean", "ndwi_change", "water_area", "water_area_change_pct",
    "sar_change", "displacement", "displacement_change",
    "historical_landslide_density", "distance_to_historical_landslide", "distance_to_landslide_dam",
    "distance_to_glacial_lake", "glacial_lake_area", "glacial_lake_area_change",
    "landslide_label",
]


def _read_if_exists(path, **kwargs):
    if path.exists():
        reader = pd.read_parquet if path.suffix == ".parquet" else pd.read_csv
        df = reader(path, **kwargs)
        print(f"Loaded {len(df)} rows from {path}")
        return df
    print(f"NOT FOUND (skipping): {path}")
    return None


def _build_backbone(grid: pd.DataFrame, rainfall) -> pd.DataFrame:
    if rainfall is not None:
        backbone = rainfall[["cell_id", "event_id", "date"]].drop_duplicates()
        return backbone.merge(grid[["cell_id", "lat", "lon"]], on="cell_id", how="left")

    print("No rainfall table found — building backbone from grid x event windows instead.")
    rows = []
    for event_id, spec in EVENTS.items():
        if not spec.get("pre_window") or not spec.get("post_window"):
            continue
        for window_key in ("pre_window", "post_window"):
            _, window_end = spec[window_key]
            for _, row in grid.iterrows():
                rows.append({"cell_id": row["cell_id"], "event_id": event_id,
                             "date": window_end, "lat": row["lat"], "lon": row["lon"]})
    if not rows:
        raise SystemExit(
            "No rainfall table AND no events with real pre/post windows in config.py — "
            "nothing to build a backbone from. Run rainfall first, or fill in event dates."
        )
    return pd.DataFrame(rows)


def build_feature_table():
    grid = _read_if_exists(GRID_PARQUET)
    if grid is None:
        raise SystemExit(f"{GRID_PARQUET} not found. Run grid/build_grid.py first — nothing to merge without it.")

    rainfall = _read_if_exists(RAINFALL_CSV)
    terrain = _read_if_exists(TERRAIN_PARQUET)
    sentinel2 = _read_if_exists(SENTINEL2_CSV)
    sentinel1 = _read_if_exists(SENTINEL1_CSV)
    hazards = _read_if_exists(HAZARDS_CSV)
    glacial_lakes = _read_if_exists(GLACIAL_LAKES_CSV)

    table = _build_backbone(grid, rainfall)
    table = table.rename(columns={"lat": "latitude", "lon": "longitude"})

    if rainfall is not None:
        table = table.merge(rainfall.drop(columns=["lat", "lon"], errors="ignore"),
                             on=["cell_id", "event_id", "date"], how="left")
    else:
        log_skipped(dataset="rainfall_in_final_table", reason="rainfall/melamchi_rainfall.csv not found at merge time")

    for name, df, join_cols in [
        ("terrain", terrain, ["cell_id"]),
        ("hazards", hazards, ["cell_id"]),
        ("glacial_lakes", glacial_lakes, ["cell_id"]),
        ("sentinel2", sentinel2, ["cell_id", "event_id"]),
        ("sentinel1", sentinel1, ["cell_id", "event_id"]),
    ]:
        if df is None:
            log_skipped(dataset=f"{name}_in_final_table", reason=f"{name} processed output not found at merge time")
            continue
        dedup_cols = [c for c in df.columns if c not in join_cols and c != "date"]
        merge_df = df[join_cols + dedup_cols].drop_duplicates(subset=join_cols)
        table = table.merge(merge_df, on=join_cols, how="left", suffixes=("", f"_{name}"))

    # Drop any spec column that is ENTIRELY missing — never fabricate a
    # placeholder for a data source that was never produced.
    for col in SPEC_COLUMNS:
        if col not in table.columns:
            log_skipped(dataset=f"column_{col}", reason=f"'{col}' was never produced by any upstream script")
            continue
        if table[col].isna().all():
            log_skipped(dataset=f"column_{col}", reason=f"'{col}' exists but is empty for every row — dropped rather than kept as all-NaN")
            table = table.drop(columns=[col])

    present_spec_cols = [c for c in SPEC_COLUMNS if c in table.columns]
    other_cols = [c for c in table.columns if c not in SPEC_COLUMNS]
    table = table[present_spec_cols + other_cols]

    FEATURE_TABLE_CSV.parent.mkdir(parents=True, exist_ok=True)
    table.to_csv(FEATURE_TABLE_CSV, index=False)
    table.to_parquet(FEATURE_TABLE_PARQUET, index=False)
    print(f"\nSaved final feature table: {len(table)} rows x {len(table.columns)} columns")
    print(f"  -> {FEATURE_TABLE_CSV}")
    print(f"  -> {FEATURE_TABLE_PARQUET}")
    print(f"Columns included: {list(table.columns)}")

    log_metadata(
        dataset="melamchi_features_final",
        source="Merged from grid, terrain, rainfall, sentinel2, sentinel1, hazards, glacial_lakes outputs",
        resolution="100m grid (see grid_cells metadata for source resolutions per layer)",
        crs="EPSG:4326 (latitude/longitude)",
        processing="Left-joined on cell_id (static layers) and cell_id+event_id (per-event layers) onto the rainfall/event backbone",
        notes=f"{len(table)} rows, {len(table.columns)} columns. See metadata.csv skip entries for any spec columns not produced.",
    )


if __name__ == "__main__":
    build_feature_table()
