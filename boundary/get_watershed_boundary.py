"""
Produce melamchi_watershed.gpkg — the real hydrological watershed boundary,
not a bounding box.

Two ways to get this, in order of preference:

1. BEST: if the 2023 Melamchi flood study (the one reporting ~957.72 km2)
   published its watershed shapefile/boundary (as a supplementary file, or
   via HydroSHARE/Zenodo), use that directly — it's the authoritative
   boundary this project wants matched. Search for it first and drop it in
   data/raw/boundary/ as `source_watershed.shp`, `.gpkg`, or `.kml`, then
   just reproject/clean it with `load_existing_boundary()` below instead of
   delineating from scratch.

2. FALLBACK: delineate it yourself from the DEM using pysheds, given an
   outlet point (the Melamchi river gauge / confluence near Melamchi
   Bazar). This is what `delineate_from_dem()` does. Cross-check the
   resulting area against MELAMCHI_TARGET_AREA_KM2 (957.72 km2) — if it's
   off by more than ~10-15%, the outlet point needs adjusting (move it
   along the river network) or the DEM has voids/pit issues to fill first.

Run dem/fetch_dem.py BEFORE this if using the fallback.
"""
import geopandas as gpd
import numpy as np
import fiona

from shapely.geometry import shape
from config import BOUNDARY_GPKG, MELAMCHI_OUTLET_LATLON, MELAMCHI_TARGET_AREA_KM2, \
    CRS_GEOGRAPHIC, CRS_PROJECTED, DATA_RAW
from utils_metadata import log_metadata

# Compatibility shim: pysheds (last released for NumPy 1.x) calls the
# removed np.in1d — NumPy 2.x renamed it to np.isin with the same signature.
if not hasattr(np, "in1d"):
    np.in1d = np.isin


def load_existing_boundary(path):
    """Preferred path: load an authoritative published boundary."""
    if str(path).lower().endswith(".kml"):
        fiona.drvsupport.supported_drivers["KML"] = "rw"
        gdf = gpd.read_file(path, driver="KML")
    else:
        gdf = gpd.read_file(path)
    gdf = gdf.to_crs(CRS_GEOGRAPHIC)
    area_km2 = gdf.to_crs(CRS_PROJECTED).area.sum() / 1e6
    print(f"Loaded boundary area: {area_km2:.2f} km2")
    _save(gdf, source=f"Published boundary (Nepal-FRES, HydroShare): {path}")


def delineate_from_dem(dem_path, outlet_latlon=MELAMCHI_OUTLET_LATLON):
    """Fallback path: delineate from a filled/conditioned DEM using pysheds."""
    from pysheds.grid import Grid

    grid = Grid.from_raster(str(dem_path))
    dem = grid.read_raster(str(dem_path))

    # Standard DEM conditioning
    pit_filled = grid.fill_pits(dem)
    flooded = grid.fill_depressions(pit_filled)
    inflated = grid.resolve_flats(flooded)

    fdir = grid.flowdir(inflated)
    acc = grid.accumulation(fdir)

    lat, lon = outlet_latlon
    # Snap the outlet to the nearest high-accumulation (river) cell
    x_snap, y_snap = grid.snap_to_mask(acc > acc.max() * 0.001, (lon, lat))

    catch = grid.catchment(x=x_snap, y=y_snap, fdir=fdir, xytype="coordinate")
    grid.clip_to(catch)
    shapes = grid.polygonize()

    geoms = [shape(g) for g, v in shapes if v == 1]
    gdf = gpd.GeoDataFrame(geometry=geoms, crs=grid.crs)
    gdf = gdf.to_crs(CRS_GEOGRAPHIC)

    area_km2 = gdf.to_crs(CRS_PROJECTED).area.sum() / 1e6
    print(f"Delineated area: {area_km2:.2f} km2 (target: {MELAMCHI_TARGET_AREA_KM2} km2)")
    if abs(area_km2 - MELAMCHI_TARGET_AREA_KM2) / MELAMCHI_TARGET_AREA_KM2 > 0.15:
        print("WARNING: delineated area is >15% off the target study area. "
              "Adjust MELAMCHI_OUTLET_LATLON in config.py (nudge it onto the "
              "actual river centerline) and re-run before trusting this boundary.")

    _save(gdf, source=f"Delineated from DEM ({dem_path}), outlet {outlet_latlon}")


def _save(gdf, source):
    gdf.to_file(BOUNDARY_GPKG, driver="GPKG")
    log_metadata(
        dataset="melamchi_watershed_boundary",
        source=source,
        resolution="N/A (vector boundary)",
        crs=CRS_GEOGRAPHIC,
        processing="Delineated/loaded and reprojected to EPSG:4326; saved as GeoPackage",
        notes=f"Target area from 2023 Melamchi flood study: {MELAMCHI_TARGET_AREA_KM2} km2",
    )
    print(f"Saved {BOUNDARY_GPKG}")


if __name__ == "__main__":
    candidates = [
        DATA_RAW / "boundary" / "source_watershed.gpkg",
        DATA_RAW / "boundary" / "source_watershed.kml",
    ]
    existing = next((c for c in candidates if c.exists()), None)
    if existing:
        load_existing_boundary(existing)
    else:
        dem_path = DATA_RAW / "dem" / "melamchi_dem_30m.tif"
        if not dem_path.exists():
            raise SystemExit(
                f"No published boundary found at {candidates} and no DEM at "
                f"{dem_path}. Either drop the published watershed file "
                f"there, or run dem/fetch_dem.py first."
            )
        delineate_from_dem(dem_path)