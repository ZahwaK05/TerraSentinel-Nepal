"""
Derive terrain features from the mosaicked DEM and sample them onto the
canonical grid (grid/build_grid.py must be run first).

Produces, per cell_id:
  elevation, slope, aspect, curvature, flow_accumulation,
  distance_to_river, river_gradient

Method:
  - The raw DEM (EPSG:4326, pixel size in DEGREES) is first reprojected to a
    metre-based CRS (CRS_PROJECTED, UTM 45N) at 30 m. richdem takes its cell
    size from the geotransform, so running it on a degree-based DEM makes
    slope ~90 deg everywhere and curvature ~1e11. Do not skip this step.
  - richdem for slope/aspect/curvature/flow accumulation (D8).
  - River network = cells whose flow accumulation exceeds a threshold
    (a proxy for channel initiation - not a substitute for a mapped river
    network, but reasonable for a ~30m DEM at this scale). If you have an
    authoritative river-line layer (e.g. from OSM or a national hydrology
    dataset), prefer that for distance_to_river instead - swap it in below.
  - distance_to_river: Euclidean distance (metres, projected CRS) from each
    grid cell to the nearest river-network cell.
  - river_gradient: slope (degrees) at the river-network cell nearest to each
    grid cell (a simplification - true channel gradient would trace the flow
    path over a longer segment).

Units: elevation m, slope deg, aspect deg (0-360), curvature = richdem's
"curvature" attribute (check richdem docs for its scaling), flow_accumulation
in DEM cells, distance_to_river m, river_gradient deg.

Output:
  data/processed/dem/terrain_features.parquet  (cell_id + 7 feature columns)
"""
import numpy as np
import rasterio
from rasterio.transform import rowcol
from rasterio.warp import calculate_default_transform, reproject, Resampling
from scipy.ndimage import distance_transform_edt
import pandas as pd
import geopandas as gpd

from config import DATA_RAW, DATA_PROCESSED, CRS_PROJECTED, CRS_GEOGRAPHIC
from utils_metadata import log_metadata, log_skipped

DEM_PATH = DATA_RAW / "dem" / "melamchi_dem_30m.tif"          # raw, EPSG:4326
DEM_UTM_PATH = DATA_RAW / "dem" / "melamchi_dem_30m_utm45.tif"  # derived, metres
TARGET_RES_M = 30
GRID_PARQUET = DATA_PROCESSED / "grid" / "grid_cells.parquet"
OUT_DIR = DATA_PROCESSED / "dem"
OUT_DIR.mkdir(parents=True, exist_ok=True)
OUT_PARQUET = OUT_DIR / "terrain_features.parquet"

# Flow-accumulation threshold (in # of contributing DEM cells) used as a
# stand-in "this cell is a river" mask. ~30m cells: 1000 cells ~= 0.9 km2
# contributing area - a reasonable channel-initiation threshold for this
# terrain, but sanity-check the resulting network against a real river
# layer/satellite basemap before trusting distance_to_river downstream.
RIVER_ACCUMULATION_THRESHOLD = 1000

UTM_NODATA = -9999.0


def ensure_projected_dem(src_path, dst_path, dst_crs=CRS_PROJECTED, res=TARGET_RES_M):
    """Reproject the geographic DEM to a metre-based CRS (cached on disk).

    Rebuilds if the source DEM is newer than the cached file.
    """
    if dst_path.exists() and dst_path.stat().st_mtime >= src_path.stat().st_mtime:
        return dst_path

    print(f"Reprojecting {src_path.name} to {dst_crs} at {res} m...")
    with rasterio.open(src_path) as src:
        transform, width, height = calculate_default_transform(
            src.crs, dst_crs, src.width, src.height, *src.bounds, resolution=res
        )
        meta = src.meta.copy()
        meta.update(
            driver="GTiff", crs=dst_crs, transform=transform,
            width=width, height=height, count=1,
            dtype="float32", nodata=UTM_NODATA,
        )
        with rasterio.open(dst_path, "w", **meta) as dst:
            reproject(
                source=rasterio.band(src, 1),
                destination=rasterio.band(dst, 1),
                src_nodata=src.nodata,
                dst_nodata=UTM_NODATA,
                resampling=Resampling.bilinear,
            )
    return dst_path


def derive_terrain():
    if not DEM_PATH.exists():
        raise SystemExit(f"{DEM_PATH} not found. Run dem/fetch_dem.py first.")
    if not GRID_PARQUET.exists():
        raise SystemExit(f"{GRID_PARQUET} not found. Run grid/build_grid.py first.")

    try:
        import richdem as rd
    except ImportError:
        raise SystemExit(
            "richdem is not installed (pip install richdem). It needs a C++ "
            "build toolchain on some platforms - see richdem docs if pip install fails."
        )

    dem_path = ensure_projected_dem(DEM_PATH, DEM_UTM_PATH)

    print(f"Loading DEM from {dem_path}...")
    with rasterio.open(dem_path) as src:
        dem_array = src.read(1).astype("float64")
        profile = src.profile
        transform = src.transform
        src_crs = src.crs

    # Guard against the degrees-as-metres bug: richdem needs metre pixels.
    if not src_crs.is_projected:
        raise SystemExit(
            f"DEM CRS {src_crs} is not projected; slope/curvature would be wrong. "
            "Reproject to a metre-based CRS first."
        )
    px_size_m = abs(transform.a)
    if abs(abs(transform.e) - px_size_m) > 1e-6:
        raise SystemExit(f"Non-square pixels: {transform.a} vs {transform.e}")
    print(f"DEM CRS {src_crs}, pixel size {px_size_m:.2f} m")

    nodata_val = profile.get("nodata")
    if nodata_val is None:
        nodata_val = UTM_NODATA
    rd_dem = rd.rdarray(dem_array, no_data=nodata_val)
    rd_dem.geotransform = transform.to_gdal()

    print("Filling depressions...")
    rd.FillDepressions(rd_dem, in_place=True)

    print("Computing slope, aspect, curvature...")
    slope = np.array(rd.TerrainAttribute(rd_dem, attrib="slope_degrees"))
    aspect = np.array(rd.TerrainAttribute(rd_dem, attrib="aspect"))
    curvature = np.array(rd.TerrainAttribute(rd_dem, attrib="curvature"))

    # Sanity check: on real Himalayan terrain the median slope is nowhere
    # near vertical. If it is, the units are wrong again.
    valid = (dem_array != nodata_val) & (slope != nodata_val)
    med_slope = float(np.median(slope[valid]))
    print(f"Slope over valid DEM cells: median {med_slope:.1f} deg, "
          f"mean {slope[valid].mean():.1f} deg, max {slope[valid].max():.1f} deg")
    if med_slope > 70:
        raise SystemExit(
            f"Median slope {med_slope:.1f} deg is implausible - check DEM units/CRS."
        )

    print("Computing D8 flow accumulation...")
    flow_acc = np.array(rd.FlowAccumulation(rd_dem, method="D8"))

    river_mask = flow_acc >= RIVER_ACCUMULATION_THRESHOLD
    n_river_cells = int(river_mask.sum())
    print(f"River-network proxy: {n_river_cells} cells above threshold "
          f"({RIVER_ACCUMULATION_THRESHOLD} contributing cells).")
    if n_river_cells == 0:
        raise SystemExit(
            "No cells exceeded RIVER_ACCUMULATION_THRESHOLD - lower it in "
            "derive_terrain.py, or the DEM/mosaic may have an issue."
        )

    # Distance-to-river: Euclidean distance transform in pixels, times the
    # pixel size in metres (pixels are square and metre-based after reprojection).
    print("Computing distance-to-river raster...")
    dist_px = distance_transform_edt(~river_mask)
    dist_to_river_m = dist_px * px_size_m

    # River gradient proxy: slope value AT the nearest river cell to each
    # pixel (see docstring - a simplification of true channel gradient).
    river_rows, river_cols = np.where(river_mask)
    river_slope_values = slope[river_mask]
    from scipy.spatial import cKDTree
    river_tree = cKDTree(np.column_stack([river_rows, river_cols]))

    print("Loading grid and sampling rasters at cell centroids...")
    grid = pd.read_parquet(GRID_PARQUET)
    grid_gdf = gpd.GeoDataFrame(
        grid, geometry=gpd.points_from_xy(grid["lon"], grid["lat"]), crs=CRS_GEOGRAPHIC
    ).to_crs(src_crs)  # sample in the DEM's own CRS (now UTM)

    rows_cols = [rowcol(transform, pt.x, pt.y) for pt in grid_gdf.geometry]
    rows = np.clip([rc[0] for rc in rows_cols], 0, dem_array.shape[0] - 1)
    cols = np.clip([rc[1] for rc in rows_cols], 0, dem_array.shape[1] - 1)

    _, nearest_river_idx = river_tree.query(np.column_stack([rows, cols]))

    out = pd.DataFrame({
        "cell_id": grid["cell_id"].values,
        "elevation": dem_array[rows, cols],
        "slope": slope[rows, cols],
        "aspect": aspect[rows, cols],
        "curvature": curvature[rows, cols],
        "flow_accumulation": flow_acc[rows, cols],
        "distance_to_river": dist_to_river_m[rows, cols],
        "river_gradient": river_slope_values[nearest_river_idx],
    })

    terrain_cols = ["elevation", "slope", "aspect", "curvature",
                    "flow_accumulation", "distance_to_river", "river_gradient"]

    # DEM nodata / fill values should not silently become a fake feature value
    bad = out["elevation"] == nodata_val
    if bad.any():
        print(f"WARNING: {bad.sum()} grid cells sampled DEM nodata - "
              f"setting their terrain features to NaN rather than a fake value.")
        out.loc[bad, terrain_cols] = np.nan

    # richdem writes its own nodata value on edge cells of the derived rasters
    for col in ("slope", "aspect", "curvature", "river_gradient"):
        edge = out[col] == nodata_val
        if edge.any():
            print(f"WARNING: {edge.sum()} cells have richdem nodata in {col}; setting to NaN.")
            out.loc[edge, col] = np.nan

    out.to_parquet(OUT_PARQUET, index=False)
    print(f"Saved terrain features for {len(out)} cells to {OUT_PARQUET}")
    print(out[terrain_cols].describe().round(3).to_string())

    log_metadata(
        dataset="terrain_features",
        source=f"Derived from {DEM_PATH.name}, reprojected to {DEM_UTM_PATH.name}",
        resolution=f"{TARGET_RES_M} m DEM (UTM), sampled to grid cell centroids",
        crs=str(src_crs),
        processing=(
            f"DEM reprojected EPSG:4326 -> {src_crs} at {TARGET_RES_M} m (bilinear); "
            "richdem: FillDepressions, TerrainAttribute(slope/aspect/curvature), "
            f"FlowAccumulation(D8); river network = flow_acc >= {RIVER_ACCUMULATION_THRESHOLD}; "
            "distance_to_river = Euclidean distance transform to nearest river cell (m); "
            "river_gradient = slope (deg) at nearest river cell (proxy, not true channel gradient)"
        ),
        notes=(
            f"River network is a flow-accumulation proxy, not a mapped river layer - "
            f"cross-check distance_to_river against satellite imagery before trusting it. "
            f"{n_river_cells} river cells identified. "
            "Earlier version computed slope/curvature on a degree-based DEM and was wrong; "
            "fixed by reprojecting before richdem."
        ),
    )


if __name__ == "__main__":
    derive_terrain()
