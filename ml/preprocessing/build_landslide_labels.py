import pandas as pd
import geopandas as gpd
from pathlib import Path

# --------------------------------------------------
# Paths
# --------------------------------------------------

BASE = Path("data/data")

NEW_FILE = BASE / "raw/hazards/historical_landslides.csv"
OLD_FILE = BASE / "raw/hazards/historical_landslides_old.csv"

WATERSHED_FILE = BASE / "processed/geometry/melamchi_watershed.gpkg"
GRID_FILE = BASE / "processed/geometry/grid_cells.gpkg"

OUTPUT_DIR = BASE / "processed/hazards"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


# --------------------------------------------------
# 1. Load historical records
# --------------------------------------------------

new = pd.read_csv(NEW_FILE)
old = pd.read_csv(OLD_FILE)

df = pd.concat([new, old], ignore_index=True)

print(f"Raw records: {len(df)}")


# --------------------------------------------------
# 2. Keep only landslides
# --------------------------------------------------

df["hazard_type"] = df["hazard_type"].str.strip().str.lower()

df = df[df["hazard_type"] == "landslide"].copy()

print(f"Landslide records before deduplication: {len(df)}")


# --------------------------------------------------
# 3. Remove duplicate records
# --------------------------------------------------

df = df.drop_duplicates(
    subset=[
        "lat",
        "lon",
        "event_date",
        "title"
    ]
).copy()

print(f"Unique landslide records: {len(df)}")


# --------------------------------------------------
# 4. Convert to GeoDataFrame
# --------------------------------------------------

points = gpd.GeoDataFrame(
    df,
    geometry=gpd.points_from_xy(
        df["lon"],
        df["lat"]
    ),
    crs="EPSG:4326"
)


# --------------------------------------------------
# 5. Load Melamchi watershed
# --------------------------------------------------

watershed = gpd.read_file(WATERSHED_FILE)

print("\nWatershed CRS:", watershed.crs)

watershed = watershed.to_crs("EPSG:4326")


# --------------------------------------------------
# 6. Find landslide records inside watershed
# --------------------------------------------------

inside = gpd.sjoin(
    points,
    watershed,
    predicate="within",
    how="inner"
)

print(f"\nLandslides inside Melamchi watershed: {len(inside)}")

print(
    inside[
        [
            "lat",
            "lon",
            "event_date",
            "title",
            "location_accuracy",
            "source"
        ]
    ].to_string(index=False)
)


# --------------------------------------------------
# 7. Save filtered historical records
# --------------------------------------------------

inside.to_file(
    OUTPUT_DIR / "melamchi_historical_landslides.gpkg",
    driver="GPKG"
)

inside.drop(columns="geometry").to_csv(
    OUTPUT_DIR / "melamchi_historical_landslides.csv",
    index=False
)


# --------------------------------------------------
# 8. Load 100m grid
# --------------------------------------------------

grid = gpd.read_file(GRID_FILE)

print("\nGrid CRS:", grid.crs)

grid = grid.to_crs("EPSG:4326")


# --------------------------------------------------
# 9. Spatial join landslides → grid cells
# --------------------------------------------------

grid_hits = gpd.sjoin(
    grid,
    inside[["geometry", "event_date", "title", "location_accuracy"]],
    predicate="contains",
    how="left"
)


# --------------------------------------------------
# 10. Count unique landslide events per cell
# --------------------------------------------------

event_counts = (
    grid_hits
    .dropna(subset=["event_date"])
    .groupby(grid_hits.index)["event_date"]
    .nunique()
)

grid["historical_landslide_count"] = (
    event_counts
    .reindex(grid.index)
    .fillna(0)
    .astype(int)
)

grid["landslide_label"] = (
    grid["historical_landslide_count"] > 0
).astype(int)


# --------------------------------------------------
# 11. Save grid labels
# --------------------------------------------------

grid.to_file(
    OUTPUT_DIR / "melamchi_grid_landslide_labels.gpkg",
    driver="GPKG"
)

print("\nFinal label distribution:")
print(grid["landslide_label"].value_counts())

print("\nPositive cells:")
print((grid["landslide_label"] == 1).sum())

print("\nDone.")