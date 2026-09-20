import pandas as pd
import geopandas as gpd
from pathlib import Path

BASE = Path("data/data")

NEW_FILE = BASE / "raw/hazards/historical_landslides.csv"
OLD_FILE = BASE / "raw/hazards/historical_landslides_old.csv"

WATERSHED_FILE = BASE / "raw/geometry/melamchi_watershed.gpkg"


# Load historical records
new = pd.read_csv(NEW_FILE)
old = pd.read_csv(OLD_FILE)

df = pd.concat([new, old], ignore_index=True)

# Keep only landslides
df["hazard_type"] = df["hazard_type"].str.strip().str.lower()
df = df[df["hazard_type"] == "landslide"].copy()

# Remove exact duplicate records
df = df.drop_duplicates(
    subset=["lat", "lon", "event_date", "title"]
).copy()

print("Unique landslide records:", len(df))


# Convert to spatial points
points = gpd.GeoDataFrame(
    df,
    geometry=gpd.points_from_xy(df["lon"], df["lat"]),
    crs="EPSG:4326"
)


# Load watershed
watershed = gpd.read_file(WATERSHED_FILE)

# Use WGS84 for this inspection
watershed = watershed.to_crs("EPSG:4326")


# Spatial filter
inside = gpd.sjoin(
    points,
    watershed[["geometry"]],
    predicate="within",
    how="inner"
)


print("\nLandslides inside Melamchi watershed:", len(inside))

print("\nRecords:")
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


print("\nLocation accuracy:")
print(
    inside["location_accuracy"]
    .value_counts(dropna=False)
)


print("\nSource:")
print(
    inside["source"]
    .value_counts(dropna=False)
)