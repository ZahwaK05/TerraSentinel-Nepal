# TerraSentinel-Nepal — V1 Geospatial Risk Engine

## 1. Overview

The V1 risk engine is a transparent, physics-informed spatial risk index for the Melamchi watershed, Nepal.

It produces a relative risk score from 0 to 100 for each 100 m × 100 m grid cell.

The score is a spatial prioritization index and is not a calibrated probability of landslide occurrence.

## 2. Study Area

Primary study area: Melamchi watershed, Nepal.

Events evaluated:

- MELAMCHI_2021
- MELAMCHI_2026

Analysis grid:

- 32,435 cells
- 100 m × 100 m
- CRS: EPSG:32645

## 3. Risk Components

The V1 score contains three equally weighted components:

1. Rainfall trigger
2. Terrain susceptibility
3. Glacial-lake proximity

### Rainfall

Rainfall features:

- rainfall_1h
- rainfall_3h
- rainfall_24h
- rainfall_7day

Rainfall values are normalized within each event using percentile ranking.

IMERG rainfall has approximately 0.1° (~10 km) native spatial resolution. Values are mapped to the 100 m analysis grid and therefore represent regional rainfall trigger conditions rather than independent 100 m rainfall observations.

### Terrain

The terrain component uses:

- slope
- flow accumulation
- distance to river

The component is constructed using percentile-based directional scores:

- higher slope → higher score
- higher flow accumulation → higher score
- smaller distance to river → higher score

### Glacial-Lake Proximity

Distance to the nearest inventoried glacial lake is converted to a proximity score:

- closer lake → higher score

## 4. V1 Risk Formula

The final score is:

Risk Score =
( Rainfall Component
+ Terrain Component
+ Lake Proximity Component ) / 3

The result is multiplied by 100 to produce the displayed 0–100 risk index.

## 5. Features Excluded from V1

### Historical landslide density

Historical landslide density was investigated but excluded from V1 because its values changed substantially between the 2021 and 2026 event snapshots despite being documented as a historical/reference feature.

### Landslide label

The available `landslide_label` contains only two positive rows out of 129,740 observations and was therefore not considered a reliable supervised-learning target.

### SAR

SAR change features were excluded because missingness and observation validity could not be reliably established for the available data.

### Water-area change

Water-area change was excluded because the feature was effectively unavailable in the current dataset.

### Glacial-lake area change

Glacial-lake area change was excluded because of substantial missingness.

## 6. Validation and QC

The V1 workflow included:

- missing-value inspection
- target-distribution inspection
- feature-correlation analysis
- rainfall-window selection
- static-feature consistency checks
- spatial ranking checks
- component variability checks
- spatial grid join verification
- visual inspection of 2021 and 2026 risk maps

Both exported risk layers contain 32,435 cells with zero missing risk scores.

## 7. Important Limitations

The V1 score is a relative spatial risk index.

It should not be interpreted as:

- a probability of landslide occurrence
- a calibrated prediction
- proof that a high-risk cell experienced a landslide
- evidence that one event was more hazardous than another

The current dataset does not contain a sufficiently reliable supervised target for training and evaluating a conventional landslide classifier.

## 8. Output Files

The V1 outputs are:

- `melamchi_2021_risk_v1.gpkg`
- `melamchi_2021_risk_v1.csv`
- `melamchi_2026_risk_v1.gpkg`
- `melamchi_2026_risk_v1.csv`

CSV schema:

- cell_id
- lat
- lon
- risk_score
- rainfall_score
- terrain_score
- lake_proximity_score