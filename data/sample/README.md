# Sample Demonstration Data

This directory contains **small, approved datasets** for local development and demonstration purposes only.

## Contents

| Directory | Dataset | Size | Source | License |
|-----------|---------|------|--------|---------|
| `melamchi/` | Sentinel-1 SAR subset (June 2021) | ~4 MB | ESA Copernicus | CC BY-SA |
| `dem/` | ALOS DEM 30 m subset (Melamchi catchment) | ~2 MB | JAXA | Non-commercial research |
| `rainfall/` | GPM IMERG subset (June 10–20 2021) | ~1 MB | NASA | Open |
| `infrastructure/` | OSM extract — roads, bridges, hospitals | ~500 KB | OpenStreetMap | ODbL |

## Rules

1. **Do not add files > 10 MB** to this directory. Use Git LFS or S3 for large datasets.
2. **Do not add proprietary or restricted data.** See `docs/data-sources/data_sources.md` for licensing guidance.
3. **Do not add any data containing PII.**
4. All files here must be labelled `[HISTORICAL]` in pipeline metadata.

## Data Mode Label

All outputs generated from these files must carry:
```json
{ "data_mode": "HISTORICAL" }
```
