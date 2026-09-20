"""
Central configuration for the TerraSentinel-Nepal data pipeline.
Every script imports from here so the study area, grid, and event windows
stay consistent across all data sources (per the "don't build separate
grids" and "don't mix events" rules).
"""
from pathlib import Path

# ---------------------------------------------------------------- Paths ---
ROOT = Path(__file__).parent
DATA_RAW = ROOT / "data" / "raw"
DATA_PROCESSED = ROOT / "data" / "processed"
BOUNDARY_GPKG = ROOT / "melamchi_watershed.gpkg"
METADATA_CSV = ROOT / "metadata.csv"
DATA_DICT_TXT = ROOT / "data_dictionary.txt"
FEATURE_TABLE_CSV = DATA_PROCESSED / "melamchi_features.csv"
FEATURE_TABLE_PARQUET = DATA_PROCESSED / "melamchi_features.parquet"

# --------------------------------------------------------- Study area -----
# Approximate bounding box for the Melamchi watershed, Nepal (WGS84).
# This is ONLY used as a search/download bbox — the actual analysis mask
# is the hydrological boundary in melamchi_watershed.gpkg, produced by
# boundary/get_watershed_boundary.py. Do not use this bbox as the boundary.
MELAMCHI_BBOX = (85.45, 27.75, 85.75, 28.05)  # (minx, miny, maxx, maxy)
MELAMCHI_TARGET_AREA_KM2 = 957.72  # from the 2023 Melamchi flood study
# Outlet point used for watershed delineation (Melamchi river gauge /
# confluence point near Melamchi Bazar) — VERIFY against the source paper
# before running delineation; this is a starting estimate, not ground truth.
MELAMCHI_OUTLET_LATLON = (27.8283, 85.5495)

RASUWA_BBOX = (85.15, 28.05, 85.55, 28.35)  # Rasuwa/Trishuli, rough — refine before use

# CRS: do all metric analysis (grid, distances, slope) in a projected CRS.
# UTM zone 45N covers this part of Nepal.
CRS_GEOGRAPHIC = "EPSG:4326"
CRS_PROJECTED = "EPSG:32645"  # WGS84 / UTM zone 45N

GRID_CELL_SIZE_M = 100  # per spec: ~100m x 100m ML grid

# ------------------------------------------------------------- Events -----
EVENTS = {
    "MELAMCHI_2021": {
        "region": "melamchi",
        "pre_window": ("2021-05-01", "2021-06-10"),
        "post_window": ("2021-06-16", "2021-07-15"),
        "description": "2021 Melamchi flood/debris-flow event",
    },
    "MELAMCHI_2026": {
        "region": "melamchi",
        # Flood damaged the Melamchi Water Supply Project's temporary intake
        # in Helambu, Sindhupalchok on the night of Thu 2 Jul 2026 (turbidity
        # began ~9pm local). Source: Kathmandu Post, 3 Jul 2026,
        # https://kathmandupost.com/valley/2026/07/03/melamchi-water-supply-halted-after-flood-damages-temporary-intake-dam
        "pre_window": ("2026-05-20", "2026-07-01"),
        "post_window": ("2026-07-03", "2026-08-02"),
        "description": "2026 Melamchi flooding (Helambu intake damage, 2 Jul 2026)",
    },
    "RASUWA_2026": {
        "region": "rasuwa",
        # Rock-ice avalanche near Langtang Lirung triggered a catastrophic
        # debris flood down the Lhende Khola-Bhote Koshi/Trishuli system on
        # the morning of 26 Aug 2026 — a SEPARATE river basin from Melamchi,
        # affecting Rasuwa, Nuwakot, Dhading. Over 1,400 deaths reported in
        # Nepal. Source: Wikipedia "2026 Nepal-Tibet floods";
        # https://en.wikipedia.org/wiki/2026_Nepal%E2%80%93Tibet_floods
        "pre_window": ("2026-07-15", "2026-08-25"),
        "post_window": ("2026-08-27", "2026-09-26"),
        "description": "2026 Rasuwa/Trishuli flood (Bhote Koshi debris flood, 26 Aug 2026)",
    },
}

# Rainfall accumulation windows requested for the ML feature table.
RAINFALL_WINDOWS_HOURS = {
    "rainfall_1h": 1,
    "rainfall_3h": 3,
    "rainfall_6h": 6,
    "rainfall_12h": 12,
    "rainfall_24h": 24,
    "rainfall_3day": 72,
    "rainfall_7day": 168,
}

for d in (DATA_RAW, DATA_PROCESSED):
    d.mkdir(parents=True, exist_ok=True)
