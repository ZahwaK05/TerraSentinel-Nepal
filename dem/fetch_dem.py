"""
Fetch NASADEM (~30m) covering the Melamchi bbox from NASA Earthdata, mosaic
tiles into one GeoTIFF. This bbox is intentionally larger than the expected
watershed so there's margin for the watershed delineation (Phase 1) to trace
ridgelines correctly near the edges.

Requires: EARTHDATA_USERNAME / EARTHDATA_PASSWORD in .env, and the GES DISC
app linked on your Earthdata profile (see Phase 0 step 1).
"""
import os
import zipfile
from pathlib import Path
from dotenv import load_dotenv
import earthaccess
import rasterio
from rasterio.merge import merge

from config import MELAMCHI_BBOX, DATA_RAW, CRS_GEOGRAPHIC
from utils_metadata import log_metadata

load_dotenv()

OUT_DIR = DATA_RAW / "dem"
OUT_DIR.mkdir(parents=True, exist_ok=True)
MOSAIC_PATH = OUT_DIR / "melamchi_dem_30m.tif"


def fetch_and_mosaic():
    auth = earthaccess.login(strategy="environment")  # reads EARTHDATA_USERNAME/PASSWORD
    if not auth.authenticated:
        raise SystemExit(
            "Earthdata login failed. Check EARTHDATA_USERNAME/PASSWORD in .env "
            "and that GES DISC is linked in your Earthdata profile."
        )

    results = earthaccess.search_data(
        short_name="NASADEM_HGT",  # NASADEM elevation, ~30m, void-filled
        bounding_box=MELAMCHI_BBOX,
    )
    if not results:
        print("No NASADEM granules found for this bbox — falling back to SRTMGL1.")
        results = earthaccess.search_data(
            short_name="SRTMGL1",
            bounding_box=MELAMCHI_BBOX,
        )
    if not results:
        raise SystemExit("No DEM granules found for the Melamchi bbox from either source.")

    print(f"Found {len(results)} DEM granule(s). Downloading...")
    files = earthaccess.download(results, str(OUT_DIR))

    # NASADEM/SRTM granules from Earthdata are delivered as .zip archives
    # containing the actual .hgt (and .num) files — extract before reading.
    raster_paths = []
    for f in files:
        f = Path(f)
        if f.suffix.lower() == ".zip":
            with zipfile.ZipFile(f) as zf:
                zf.extractall(OUT_DIR)
                for name in zf.namelist():
                    if name.lower().endswith((".tif", ".hgt")):
                        raster_paths.append(OUT_DIR / name)
        elif f.suffix.lower() in (".tif", ".hgt"):
            raster_paths.append(f)

    # Mosaic all downloaded tiles into a single GeoTIFF
    srcs = [rasterio.open(p) for p in raster_paths]
    if not srcs:
        raise SystemExit(f"Downloaded files but none were readable rasters: {files}")

    mosaic, transform = merge(srcs)
    meta = srcs[0].meta.copy()
    meta.update({
        "driver": "GTiff",  # source .hgt files use the SRTMHGT driver, which
                             # only accepts a handful of fixed tile sizes —
                             # force GTiff since we're writing a mosaicked .tif
        "height": mosaic.shape[1],
        "width": mosaic.shape[2],
        "transform": transform,
        "crs": CRS_GEOGRAPHIC,
    })
    with rasterio.open(MOSAIC_PATH, "w", **meta) as dst:
        dst.write(mosaic)
    for s in srcs:
        s.close()

    print(f"Saved mosaicked DEM to {MOSAIC_PATH}")

    log_metadata(
        dataset="dem_melamchi",
        source="NASADEM_HGT (NASA Earthdata / LP DAAC)",
        resolution="~30m (1 arc-second)",
        crs=CRS_GEOGRAPHIC,
        processing=f"Downloaded {len(files)} granule(s) via earthaccess, mosaicked with rasterio.merge",
        notes=f"bbox used: {MELAMCHI_BBOX}",
    )


if __name__ == "__main__":
    fetch_and_mosaic()
