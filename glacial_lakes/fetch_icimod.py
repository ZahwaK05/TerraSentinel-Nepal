"""
Build glacial-lake features (distance_to_glacial_lake, glacial_lake_area,
glacial_lake_area_change) from an ICIMOD glacial lake inventory, joined to
the project grid.

THIS IS A MANUAL-DOWNLOAD STEP, same as hazards/fetch_landslide_data.py -
no authenticated API for this; download from ICIMOD's data portal.

Source (ICIMOD RDS, https://rds.icimod.org):
  - Glacial Lakes of Nepal 2011 (Landsat 2005/06 imagery)
  - Glacial lakes in the Koshi, Gandaki and Karnali river basins of Nepal,
    the Tibet Autonomous Region of China, and India (Landsat 2015-16 imagery)

Expected input files (name them by IMAGERY year, all shapefile parts):
  data/raw/glacial_lakes/glacial_lakes_2005.(shp|geojson|csv)
  data/raw/glacial_lakes/glacial_lakes_2015.(shp|geojson|csv)
The year is read from the filename to decide which inventory is older.
glacial_lake_area_change matches lakes between the two years by polygon overlap
(merged/split lakes are compared as a group); a lake with no counterpart in the
older inventory gets NaN rather than being compared with a different lake.
Lake area is computed from the polygon geometry in the projected CRS, so no
unit guessing on an area attribute.

GRID INPUT: data/processed/grid/grid_cells.parquet (cell_id, lat, lon) -
same convention as every other script in this pipeline.
"""
from pathlib import Path
import re

import geopandas as gpd
import pandas as pd
from shapely.geometry import Point

from config import DATA_RAW, DATA_PROCESSED, CRS_GEOGRAPHIC, CRS_PROJECTED
from utils_metadata import log_metadata, log_skipped

RAW_DIR = DATA_RAW / "glacial_lakes"
OUT_DIR = DATA_PROCESSED / "glacial_lakes"
RAW_DIR.mkdir(parents=True, exist_ok=True)
OUT_DIR.mkdir(parents=True, exist_ok=True)
OUT_CSV = OUT_DIR / "melamchi_glacial_lakes.csv"

GRID_PARQUET = DATA_PROCESSED / "grid" / "grid_cells.parquet"

# Goes into metadata.csv
ICIMOD_SOURCE_NOTE = (
    "ICIMOD RDS: Glacial Lakes of Nepal 2011 (Landsat 2005/06, doi 10.26066/rds.20831); "
    "Glacial lakes in the Koshi, Gandaki and Karnali river basins of Nepal, TAR China "
    "and India (Landsat 2015-16, doi 10.26066/RDS.1971946); CC BY 4.0"
)


def _load_grid() -> gpd.GeoDataFrame:
    if not GRID_PARQUET.exists():
        raise SystemExit(f"{GRID_PARQUET} not found. Run grid/build_grid.py first.")
    df = pd.read_parquet(GRID_PARQUET)
    geometry = [Point(xy) for xy in zip(df["lon"], df["lat"])]
    return gpd.GeoDataFrame(df, geometry=geometry, crs=CRS_GEOGRAPHIC)


def _find_inventory_files() -> list[Path]:
    if not RAW_DIR.exists():
        return []
    files = list(RAW_DIR.glob("glacial_lakes_*.shp")) + \
            list(RAW_DIR.glob("glacial_lakes_*.geojson")) + \
            list(RAW_DIR.glob("glacial_lakes_*.csv"))
    return sorted(files)


def _extract_year(path: Path) -> int | None:
    m = re.search(r"(\d{4})", path.stem)
    return int(m.group(1)) if m else None


def _load_lakes(path: Path) -> gpd.GeoDataFrame:
    if path.suffix.lower() == ".csv":
        df = pd.read_csv(path)
        lat_col = next((c for c in df.columns if c.lower() in ("lat", "latitude")), None)
        lon_col = next((c for c in df.columns if c.lower() in ("lon", "lng", "longitude")), None)
        if not lat_col or not lon_col:
            raise SystemExit(f"{path} has no recognizable lat/lon columns: {list(df.columns)}")
        geometry = [Point(xy) for xy in zip(df[lon_col], df[lat_col])]
        gdf = gpd.GeoDataFrame(df, geometry=geometry, crs=CRS_GEOGRAPHIC)
    else:
        gdf = gpd.read_file(path)
        if gdf.crs is None:
            raise SystemExit(f"{path} has no CRS defined.")
        gdf = gdf.to_crs(CRS_GEOGRAPHIC)

    # Area from the polygon geometry in the projected CRS (m2), not from an
    # attribute column whose units are a guess.
    if not gdf.geometry.geom_type.isin(["Polygon", "MultiPolygon"]).all():
        raise SystemExit(
            f"{path}: expected polygon lakes to compute area from geometry "
            f"(found {list(gdf.geometry.geom_type.unique())})."
        )
    gdf["lake_area_m2"] = gdf.to_crs(CRS_PROJECTED).geometry.area
    return gdf[["geometry", "lake_area_m2"]]


# Lakes from the two inventories count as "the same lake" if their polygons
# come within this distance of each other (digitising offsets between surveys).
MATCH_TOL_M = 50.0


def _match_lake_change(new_m: gpd.GeoDataFrame, old_m: gpd.GeoDataFrame,
                       tol_m: float = MATCH_TOL_M) -> gpd.GeoDataFrame:
    """Add glacial_lake_area_change (%) to each lake in new_m, matched by overlap.

    New and old lakes that overlap (within tol_m) are linked, and each connected
    group is compared as a whole: sum of new areas vs sum of old areas. That
    handles a lake that merged from several (many old -> one new) and one that
    split (one old -> many new) without double counting. A new lake with no old
    lake overlapping it gets NaN, never a comparison with some other lake.
    Also adds lakes_in_group (new + old lakes in the group) for diagnostics.
    """
    new = new_m.reset_index(drop=True).copy()
    old = old_m.reset_index(drop=True)
    n_new = len(new)

    old_buf = old[["geometry"]].copy()
    old_buf["geometry"] = old_buf.geometry.buffer(tol_m)
    pairs = gpd.sjoin(new[["geometry"]], old_buf, how="inner", predicate="intersects")

    parent = list(range(n_new + len(old)))

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    for i, j in zip(pairs.index, pairs["index_right"]):
        ri, rj = find(int(i)), find(n_new + int(j))
        if ri != rj:
            parent[rj] = ri

    new_sum, old_sum, count = {}, {}, {}
    new_roots = [find(i) for i in range(n_new)]
    for i, r in enumerate(new_roots):
        new_sum[r] = new_sum.get(r, 0.0) + float(new.at[i, "lake_area_m2"])
        count[r] = count.get(r, 0) + 1
    for j in range(len(old)):
        r = find(n_new + j)
        if r in new_sum:  # old lakes with no new lake nearby never enter a group
            old_sum[r] = old_sum.get(r, 0.0) + float(old.at[j, "lake_area_m2"])
            count[r] += 1

    new["glacial_lake_area_change"] = [
        (new_sum[r] - old_sum[r]) / old_sum[r] * 100 if old_sum.get(r, 0.0) > 0 else float("nan")
        for r in new_roots
    ]
    new["lakes_in_group"] = [count[r] for r in new_roots]
    return new


def build_glacial_lake_features():
    grid = _load_grid()
    inventory_files = _find_inventory_files()

    if not inventory_files:
        log_skipped(
            dataset="glacial_lakes",
            reason=(
                "No glacial lake inventory found under data/raw/glacial_lakes/ "
                "(expected glacial_lakes_<year>.shp/.geojson/.csv). Download from "
                "ICIMOD RDS (rds.icimod.org) and re-run."
            ),
        )
        print("No glacial lake inventory found - skipping distance_to_glacial_lake, "
              "glacial_lake_area, glacial_lake_area_change entirely.")
        return

    # Use the most recent inventory as the "current" layer for distance/area
    files_by_year = [(f, _extract_year(f)) for f in inventory_files]
    files_by_year = [(f, y) for f, y in files_by_year if y is not None] or [(inventory_files[-1], None)]
    files_by_year.sort(key=lambda t: (t[1] is None, t[1] or 0))
    latest_path, latest_year = files_by_year[-1]

    lakes = _load_lakes(latest_path)
    print(f"Loaded {len(lakes)} glacial lake(s) from {latest_path} (year: {latest_year}).")

    grid_m = grid.to_crs(CRS_PROJECTED)
    lakes_m = lakes.to_crs(CRS_PROJECTED).reset_index(drop=True)

    # Area change: only possible with >= 2 dated inventories. Lakes are matched
    # between years by polygon overlap, so a cell's change value always belongs
    # to the same lake that supplies its distance and area.
    has_two_years = len(files_by_year) >= 2 and all(y is not None for _, y in files_by_year)
    if has_two_years:
        earliest_path, earliest_year = files_by_year[0]
        earlier_lakes = _load_lakes(earliest_path).to_crs(CRS_PROJECTED)
        print(f"Loaded {len(earlier_lakes)} glacial lake(s) from {earliest_path} (year: {earliest_year}).")
        lakes_m = _match_lake_change(lakes_m, earlier_lakes)
        matched = lakes_m["glacial_lake_area_change"].notna()
        print(f"Matched {int(matched.sum())} of {len(lakes_m)} {latest_year} lakes to a "
              f"{earliest_year} lake by overlap; {int((~matched).sum())} have no {earliest_year} "
              f"counterpart (new lakes, or outside the {earliest_year} inventory's coverage) -> NaN.")
        print(f"{int((lakes_m['lakes_in_group'] > 2).sum())} {latest_year} lakes are in merge/split "
              f"groups (more than one lake in either year).")

    nearest = gpd.sjoin_nearest(
        grid_m[["cell_id", "geometry"]], lakes_m, distance_col="dist_m"
    ).sort_values("dist_m").drop_duplicates(subset="cell_id")

    keep = ["cell_id", "dist_m", "lake_area_m2"] + (["glacial_lake_area_change"] if has_two_years else [])
    result = grid[["cell_id"]].merge(nearest[keep], on="cell_id", how="left").rename(columns={"dist_m": "distance_to_glacial_lake", "lake_area_m2": "glacial_lake_area"})

    log_metadata(
        dataset="glacial_lake_distance_area",
        source=str(latest_path),
        resolution=f"polygon inventory, imagery year: {latest_year or 'unknown'}; area from polygon geometry (m2)",
        crs=CRS_GEOGRAPHIC,
        processing="sjoin_nearest distance (m) from cell centroid to nearest lake polygon; area of that lake",
        notes=ICIMOD_SOURCE_NOTE,
    )

    if has_two_years:
        log_metadata(
            dataset="glacial_lake_area_change",
            source=f"{earliest_path} ({earliest_year}) vs {latest_path} ({latest_year})",
            resolution="polygon inventory, two imagery years",
            crs=CRS_GEOGRAPHIC,
            processing=(
                f"% area change per {latest_year} lake, matched to {earliest_year} lakes by polygon "
                f"overlap (tolerance {MATCH_TOL_M:.0f} m); merged/split lakes compared as a group "
                f"(sum of areas); NaN where no {earliest_year} lake overlaps. Each cell takes the "
                f"value of its nearest {latest_year} lake. The two inventories use different "
                f"imagery and mapping methods, so some change may be mapping artefact."
            ),
            notes=ICIMOD_SOURCE_NOTE,
        )
    else:
        # No placeholder column: an all-NaN column would ship as if it were data.
        log_skipped(
            dataset="glacial_lake_area_change",
            reason=(
                "Only one dated glacial lake inventory found - area change needs at least "
                "two survey years. Add another year's inventory file to data/raw/glacial_lakes/ "
                "(filename must contain the year, e.g. glacial_lakes_2005.shp) to enable this."
            ),
        )

    result.to_csv(OUT_CSV, index=False)
    print(f"Saved {len(result)} rows to {OUT_CSV}")
    print(result.drop(columns="cell_id").describe().round(1).to_string())


if __name__ == "__main__":
    build_glacial_lake_features()
