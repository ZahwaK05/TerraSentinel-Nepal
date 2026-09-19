# Architecture Overview

## System Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          TerraSentinel-Nepal                                │
│                                                                             │
│  External Sources                                                           │
│  ┌──────────┐  ┌────────┐  ┌────────┐  ┌────────────┐                     │
│  │ Sentinel │  │  NASA  │  │  JAXA  │  │  OSM / DHM │                     │
│  │ SAR/S2   │  │  GPM   │  │  DEM   │  │  Infra/WL  │                     │
│  └────┬─────┘  └───┬────┘  └───┬────┘  └─────┬──────┘                     │
│       └────────────┴───────────┴──────────────┘                            │
│                          │                                                  │
│                   ┌──────▼──────┐                                           │
│                   │  Data       │  Lambda + S3                              │
│                   │  Ingestion  │  (demo: reads data/sample/)               │
│                   └──────┬──────┘                                           │
│                          │  Raw data → S3                                   │
│                   ┌──────▼──────────────────┐                              │
│                   │  Geospatial Processing   │  Python / GDAL / rasterio   │
│                   │  - SAR backscatter       │                              │
│                   │  - NDWI water change     │                              │
│                   │  - DEM flow corridors    │                              │
│                   │  - Flood extent polygon  │                              │
│                   └──────┬──────────────────┘                              │
│                          │  GeoJSON features → S3                           │
│                   ┌──────▼──────────────────┐                              │
│                   │  ML Risk Scorer          │  SageMaker / scikit-learn   │
│                   │  - Grid-cell risk score  │                              │
│                   │  - Feature importance    │                              │
│                   │  - Impact zone polygon   │                              │
│                   └──────┬──────────────────┘                              │
│                          │  Risk GeoJSON → S3 + API                        │
│              ┌───────────┼────────────────────┐                            │
│       ┌──────▼──────┐    │              ┌──────▼──────┐                    │
│       │  Alert      │    │              │  Frontend   │                    │
│       │  Dispatcher │    │              │  Dashboard  │                    │
│       │  (Lambda)   │    │              │  (Next.js)  │                    │
│       │  mock mode  │    │              │  Leaflet/   │                    │
│       └─────────────┘    │              │  Mapbox     │                    │
│                          │              └─────────────┘                    │
│                   ┌──────▼──────────────────┐                              │
│                   │  API Gateway             │  REST + WebSocket            │
│                   └─────────────────────────┘                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Component Responsibilities

| Component | Location | Responsibility |
|-----------|----------|----------------|
| Data Ingestion | `services/data-ingestion/` | Fetch, validate, and store raw source data |
| Geospatial Processing | `geospatial/` | Transform rasters to flood features |
| ML Risk Scorer | `ml/` | Assign risk scores with explainability |
| Alert Dispatcher | `services/alert-dispatcher/` | Generate and (mock) deliver Nepali alerts |
| Frontend Dashboard | `frontend/` | Interactive risk map and timeline |
| Infrastructure | `infrastructure/` | AWS resource definitions (IaC) |

## Data Flow Guarantees

1. Every data product carries a `data_mode` attribute: `HISTORICAL`, `SIMULATED`, or `LIVE`.
2. The alert dispatcher will not send messages to real contacts unless `ALERT_MODE=live` is explicitly set and confirmed.
3. All model decisions are logged with input features, output score, and feature importance.

## AWS Services Used

| Service | Purpose |
|---------|---------|
| S3 | Data lake for raw, processed, and model output data |
| Lambda | Serverless processing for ingestion, scoring, and alert dispatch |
| SageMaker | Model training and inference endpoints |
| API Gateway | REST and WebSocket API for frontend |
| CloudFront | CDN for frontend static assets |
| Polly | Nepali voice synthesis (mock in demo mode) |
| CloudWatch | Logging, metrics, and alerting |
