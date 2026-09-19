# Risk Score Methodology

> **Status: Draft — Open for team review.**
> Assumptions and thresholds listed here must be validated against historical data before demo.

---

## Overview

The TerraSentinel risk score is a per-grid-cell value in [0, 1] that represents the probability of flood impact given current or predicted conditions. The score is decomposed into contributing features to support explainability.

---

## Input Features

| Feature | Source | Weight (v1) | Notes |
|---------|--------|------------|-------|
| NDWI water change | Sentinel-2 / Sentinel-1 | 0.30 | Normalised difference water index delta vs. baseline |
| Rainfall accumulation (72 h) | NASA GPM | 0.25 | Cumulative mm over the upstream catchment |
| DEM slope | ALOS DEM 30 m | 0.15 | Steeper slopes increase flow velocity |
| DEM flow accumulation | ALOS DEM 30 m | 0.15 | Upstream contributing area |
| Distance to river channel | OSM / DHM | 0.10 | Proximity in metres |
| Infrastructure density | OSM | 0.05 | Count of assets per km² |

> **Open Question:** Are these weights validated against the 2021 Melamchi event ground truth? Current weights are expert-estimated. A calibration exercise is required before claiming predictive accuracy.

---

## Risk Score Formula (v1)

```
risk_score = sigmoid( w · x + b )

where:
  x = normalised feature vector (z-score per feature)
  w = feature weight vector (see table above)
  b = bias term (fitted on training data)
```

The sigmoid function maps the linear combination to [0, 1].

---

## Risk Thresholds

| Level | Score Range | Action |
|-------|------------|--------|
| Low | 0.0 – 0.40 | Monitor; no alert |
| Medium | 0.40 – 0.70 | Preparedness alert |
| High | 0.70 – 1.00 | Evacuation alert |

> **Open Question:** These thresholds have not been agreed by the team. They are placeholders derived from literature. Adjusting them changes the false-positive and false-negative rates significantly.

---

## Explainability Output

For each grid cell, the system produces:

```json
{
  "cell_id": "NP-28.2-85.5-30m",
  "risk_score": 0.82,
  "risk_level": "HIGH",
  "data_mode": "HISTORICAL",
  "feature_contributions": {
    "ndwi_change": 0.31,
    "rainfall_72h": 0.24,
    "dem_slope": 0.12,
    "flow_accumulation": 0.09,
    "distance_to_river": 0.04,
    "infrastructure_density": 0.02
  },
  "model_version": "v1",
  "timestamp_utc": "2021-06-15T03:00:00Z"
}
```

---

## Limitations

1. **Training data:** Model v1 is fitted on a small historical dataset. Generalisation to new GLOFs is unknown.
2. **Resolution:** 30 m DEM may miss micro-topographic features important for rapid flash floods.
3. **Temporal:** Rainfall integration window (72 h) may not capture antecedent soil saturation adequately.
4. **Infrastructure:** OSM coverage in rural Nepal is incomplete; some assets may be unlabelled.
5. **Uncertainty:** No confidence intervals are provided in v1. This is a known limitation.

---

## Assumptions

- NDWI computed using Green and NIR bands from Sentinel-2 L2A surface reflectance.
- GPM IMERG Late Run used for near-real-time; Final Run for historical validation.
- DEM hydrological conditioning (pit-filling, breach) applied before flow accumulation.
- Infrastructure layer filtered to: roads (OSM highway tag), bridges, hospitals, schools.

---

## Open Questions for Team Review

| # | Question |
|---|---------|
| 1 | Is a logistic regression sufficient or do we need a gradient boosting model? |
| 2 | Should GLOF risk be scored separately from riverine flood risk? |
| 3 | What ground-truth dataset validates the 2021 Melamchi predictions? |
| 4 | How do we handle missing satellite data due to cloud cover? |
| 5 | What is the minimum acceptable F1 score before the demo? |
