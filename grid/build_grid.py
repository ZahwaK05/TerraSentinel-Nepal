"""
Build the canonical ML grid over the Melamchi watershed.

Every other script in this pipeline (terrain, rainfall, Sentinel-1/2,
hazards, glacial lakes) samples/aggregates its data onto THIS grid, joined
on cell_id — per the project rule "don't independently create different
grids for different datasets."

Output:
  data/processed/grid/grid_cells.gpkg     (cell_id, geometry=polygon cell)
  data/processed/grid/grid_cells.parquet  (cell_id, lat, lon — centroid table,
                                            the thing every other script merges on)

Run this AFTER boundary/get_watershed_boundary.py.
"""
import numpy as np
import geopandas as gpd
from shapely.geometry import box

from config import (
    BOUNDARY_GPKG, DATA_PROCESSED, GRID_CELL_SIZE_M,
    CRS_GEOGRAPHIC, CRS_PROJECTED,
)
from utils_metadata import log_metadata

OUT_DIR = DATA_PROCESSED / "grid"
OUT_DIR.mkdir(parents=True, exist_ok=True)
GRID_GPKG = OUT_DIR / "grid_cells.gpkg"
GRID_PARQUET = OUT_DIR / "grid_cells.parquet"


def build_grid():
    if not BOUNDARY_GPKG.exists():
        raise SystemExit(
            f"{BOUNDARY_GPKG} not found. Run boundary/get_watershed_boundary.py first — "
            f"the grid is built over the real watershed, not a bounding box."
        )

    watershed = gpd.read_file(BOUNDARY_GPKG).to_crs(CRS_PROJECTED)
    # Dissolve in case the boundary has multiple polygons/holes from delineation
    watershed_union = watershed.geometry.union_all()

    minx, miny, maxx, maxy = watershed_union.bounds
    xs = np.arange(minx, maxx, GRID_CELL_SIZE_M)
    ys = np.arange(miny, maxy, GRID_CELL_SIZE_M)

    print(f"Building {GRID_CELL_SIZE_M}m grid over bounds {watershed_union.bounds} "
          f"({len(xs)} x {len(ys)} candidate cells before clipping)...")

    cells = []
    for x in xs:
        for y in ys:
            cell = box(x, y, x + GRID_CELL_SIZE_M, y + GRID_CELL_SIZE_M)
            # Keep a cell if its centroid falls inside the watershed — avoids
            # slivers of edge cells that are mostly outside the catchment.
            if watershed_union.contains(cell.centroid):
                cells.append(cell)

    if not cells:
        raise SystemExit(
            "No grid cells fell inside the watershed boundary. Check that "
            f"{BOUNDARY_GPKG} actually contains a valid polygon (open it in QGIS)."
        )

    gdf = gpd.GeoDataFrame(geometry=cells, crs=CRS_PROJECTED)
    gdf["cell_id"] = [f"CELL_{i:06d}" for i in range(len(gdf))]

    # Centroid lat/lon in geographic CRS — this is what the ML table joins on
    centroids = gdf.geometry.centroid.to_crs(CRS_GEOGRAPHIC)
    gdf["lat"] = centroids.y
    gdf["lon"] = centroids.x

    gdf = gdf[["cell_id", "lat", "lon", "geometry"]]

    gdf.to_file(GRID_GPKG, driver="GPKG")
    gdf.drop(columns="geometry").to_parquet(GRID_PARQUET, index=False)

    print(f"Built {len(gdf)} grid cells covering the watershed.")
    print(f"Saved polygons to {GRID_GPKG}")
    print(f"Saved centroid table to {GRID_PARQUET}")

    log_metadata(
        dataset="grid_cells",
        source=f"Derived from {BOUNDARY_GPKG.name}",
        resolution=f"{GRID_CELL_SIZE_M}m x {GRID_CELL_SIZE_M}m",
        crs=f"{CRS_PROJECTED} (cell geometry), {CRS_GEOGRAPHIC} (centroid lat/lon)",
        processing=(
            f"Regular {GRID_CELL_SIZE_M}m grid generated over watershed bounding box, "
            f"kept cells whose centroid falls inside the watershed polygon"
        ),
        notes=f"{len(gdf)} cells; cell_id is the join key for every other dataset",
    )

    return gdf


if __name__ == "__main__":
    build_grid()
