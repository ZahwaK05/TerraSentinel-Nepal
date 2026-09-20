"""
Quick sanity check of the merged feature table.
Save in the project root (D:\\TerraSentinel-Nepal) and run:
    python check_merge.py
"""
from pathlib import Path

import pandas as pd

pd.set_option("display.width", 200)
pd.set_option("display.max_columns", 50)
pd.set_option("display.max_rows", 200)

P = Path("data/processed")
df = pd.read_parquet(P / "melamchi_features.parquet")

print(f"Table: {len(df)} rows x {len(df.columns)} columns\n")

print("=== Rows per event / window ===")
print(df.groupby(["event_id", "window"]).size(), "\n")

cols = [c for c in ["rainfall_24h", "ndwi_mean", "ndwi_change", "water_area",
                    "water_area_change_pct", "sar_change",
                    "historical_landslide_density", "landslide_label"]
        if c in df.columns]
print("=== Share of non-null values per event / window ===")
print(df.groupby(["event_id", "window"])[cols].apply(lambda g: g.notna().mean()).round(3), "\n")

if "landslide_label" in df.columns:
    print("=== Positive landslide labels per event / window ===")
    print(df.groupby(["event_id", "window"])["landslide_label"].sum(), "\n")

print("=== merge_report.csv ===")
print(pd.read_csv(P / "merge_report.csv").to_string(index=False), "\n")

hz = P / "hazards" / "melamchi_hazards.csv"
if hz.exists():
    print("=== Columns in melamchi_hazards.csv ===")
    print(list(pd.read_csv(hz, nrows=0).columns))
