# 🌍 TerraSentinel-Nepal: Cloud-Native Geospatial Backend (Member 3 — Manas)

> **Cascading Flood & GLOF Early Warning, Critical Infrastructure Protection, and Citizen Safety Platform**  
> *Developed for Nepal's Himalayan River Basins (Melamchi, Bhotekoshi, Tamur, Marsyangdi)*

---

## 🏛️ Architecture Overview

```
             [ Geospatial & Sensor Feed (SAR, NDWI, Weather) ]
                                     │
                                     ▼
                   Amazon S3: terrasentinel-geodata-...
                                     │
                                     ▼ (EventBridge S3 PutObject)
                      AWS Step Functions State Machine
                                     │
     ┌───────────────────────────────┼───────────────────────────────┐
     ▼                               ▼                               ▼
Lambda 1: process-data        Lambda 2: calculate-features    Lambda 3: run-risk-model
(validate & normalize)       (slope, rain, NDWI, SAR)        (Amazon SageMaker inference)
                                                                     │
                                                                     ▼
                                                              Lambda 4: generate-alert
                                                             (thresholds, Polly speech,
                                                              impacted infrastructure)
                                                                     │
                     ┌───────────────────────────────────────────────┼───────────────────────┐
                     ▼                                               ▼                       ▼
           DynamoDB: RiskEvents                            DynamoDB: Infrastructure        DynamoDB: Alerts / Rescue
                     │                                               │                       │
                     └───────────────────────────────────────────────┼───────────────────────┘
                                                                     ▼
                                                         Amazon API Gateway (HTTP)
                                                    (GET /risk, GET /infrastructure, etc.)
                                                                     ▲
                                                                     │
                                                      Frontend (Next.js / React UI)
```

---

## 📁 Repository Structure

```
terrasentinel-backend/
├── template.yaml                  # AWS SAM IaC (S3, 4x DynamoDB, 5x Lambdas, Step Functions, API Gateway)
├── statemachine/
│   └── risk_pipeline.asl.json     # AWS Step Functions Amazon States Language definition
├── functions/
│   ├── process_data/              # Lambda 1: S3 raw file ingest & geospatial normalization
│   │   ├── app.py
│   │   └── requirements.txt
│   ├── calculate_features/        # Lambda 2: 24h rainfall, slope, NDWI delta, displacement
│   │   ├── app.py
│   │   └── requirements.txt
│   ├── run_risk_model/            # Lambda 3: SageMaker endpoint invocation + dual fallback
│   │   ├── app.py
│   │   └── requirements.txt
│   ├── generate_alert/            # Lambda 4: Bilingual alerts (EN + Nepali), Polly, safe zones
│   │   ├── app.py
│   │   └── requirements.txt
│   └── api_handler/               # Lambda 5: REST API Gateway router & simulation engine
│       ├── app.py
│       └── requirements.txt
├── scripts/
│   ├── local_server.py            # Zero-dependency local mock server (runs on http://127.0.0.1:8000)
│   ├── seed_nepal_data.py         # Seeds authentic Nepal infrastructure, basins, alerts to DynamoDB
│   ├── trigger_simulation.py      # CLI tool to test pipeline locally or in AWS
│   └── nepal_seed_data.json       # Pre-built snapshot of Nepal assets
└── tests/
    └── test_pipeline.py           # Unit & end-to-end integration test suite
```

---

## ⚡ Quick Start (Local Demo Mode — Zero AWS Setup)

You can run the full backend locally right now without waiting for AWS deployment so your frontend teammate can start connecting immediately.

### 1. Run Unit Tests
```bash
python -m unittest discover -s tests
```

### 2. Run the Local Pipeline Simulation
Simulates the entire 4-stage pipeline (Preprocess ➔ Features ➔ ML ➔ Alerts):
```bash
python scripts/trigger_simulation.py --mode local
```

### 3. Start the Local API Server
Serves all REST endpoints on port 8000 with CORS enabled for your Next.js frontend (`http://localhost:3000`):
```bash
python scripts/local_server.py --port 8000
```

---

## 🚀 Deploying to AWS (SHIP IT)

### Prerequisites
- [AWS CLI](https://aws.amazon.com/cli/) configured (`aws configure`)
- [AWS SAM CLI](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/install-sam-cli.html) installed

### Step 1: Build the Serverless Application
```bash
sam build
```

### Step 2: Deploy to your AWS Account
```bash
sam deploy --guided
```
When prompted:
- **Stack Name:** `terrasentinel-backend`
- **AWS Region:** `ap-south-1` (Mumbai) or `us-east-1`
- **Parameter SageMakerEndpointName:** `terrasentinel-risk-model`
- Confirm authorization for IAM role creation and unauthenticated HTTP API access.

### Step 3: Seed Nepal Infrastructure & Baseline Events
Once deployment completes, copy the table names and run:
```bash
python scripts/seed_nepal_data.py --env aws
```

---

## 📡 API Reference for Frontend Teammate

Base URL:
- **Local:** `http://127.0.0.1:8000`
- **AWS:** `https://{api-id}.execute-api.{region}.amazonaws.com/prod`

All endpoints return standard CORS headers (`Access-Control-Allow-Origin: *`).

---

### 1. `GET /risk`
Returns risk summaries across all monitored river basins.

**Sample Response:**
```json
{
  "status": "success",
  "count": 4,
  "basins": [
    {
      "zone_id": "melamchi-basin",
      "zone_name": "Melamchi River Basin",
      "district": "Sindhupalchok",
      "risk_score": 82,
      "risk_level": "CRITICAL",
      "primary_threat": "Cascading Slope Collapse & Debris Flood Surge",
      "telemetry": {
        "rainfall_24h": 142.0,
        "slope": 37.2,
        "lake_change": 0.21,
        "displacement": 0.14
      },
      "coordinates": { "lat": 27.8311, "lon": 85.5804 }
    }
  ]
}
```

---

### 2. `GET /risk/{zone}`
Returns details and 6-hour historical trend points for charting.

**Example:** `GET /risk/melamchi-basin`

**Sample Response:**
```json
{
  "zone_id": "melamchi-basin",
  "details": { ... },
  "time_series_trend": [
    { "timestamp": "...", "risk_score": 37, "rainfall_mm": 18.0, "risk_level": "LOW" },
    { "timestamp": "...", "risk_score": 52, "rainfall_mm": 42.0, "risk_level": "MODERATE" },
    { "timestamp": "...", "risk_score": 67, "rainfall_mm": 88.5, "risk_level": "HIGH" },
    { "timestamp": "...", "risk_score": 82, "rainfall_mm": 142.0, "risk_level": "CRITICAL" }
  ]
}
```

---

### 3. `GET /infrastructure`
Returns status of hydropower stations, bridges, highways, and intake dams.

**Sample Response:**
```json
{
  "count": 5,
  "infrastructure": [
    {
      "infra_id": "hydro-melamchi-headworks",
      "name": "Melamchi Water Supply Project - Intake Headworks",
      "type": "Hydropower / Water Intake",
      "zone_id": "melamchi-basin",
      "status": "EMERGENCY_LOCKDOWN",
      "risk_score": 82,
      "criticality": "CRITICAL",
      "coordinates": { "lat": 27.9622, "lon": 85.5681 },
      "elevation_m": 1420,
      "recommended_action": "Close headworks hydraulic gates & evacuate operational staff."
    },
    {
      "infra_id": "hydro-upper-bhotekoshi-45mw",
      "name": "Upper Bhotekoshi Hydropower Station (45MW)",
      "type": "Hydropower Plant",
      "zone_id": "bhotekoshi-basin",
      "status": "WARNING_ALERT",
      "risk_score": 58,
      "coordinates": { "lat": 27.9400, "lon": 85.8900 },
      "elevation_m": 1350
    }
  ]
}
```

---

### 4. `GET /population`
Returns settlements and designated DEM-based higher-elevation evacuation zones.

**Sample Response:**
```json
{
  "total_population_at_risk": 6050,
  "settlements": [
    {
      "settlement_id": "settlement-melamchi-bazaar",
      "name": "Melamchi Bazaar",
      "population": 4200,
      "elevation_m": 845,
      "vulnerability": "EXTREME",
      "evacuation_safe_zone": {
        "name": "Melamchi Upper Community Hilltop Ridge",
        "elevation_m": 1280,
        "coordinates": { "lat": 27.8340, "lon": 85.5720 },
        "capacity": 3500,
        "travel_time_minutes": 15
      }
    }
  ]
}
```

---

### 5. `GET /alerts`
Returns bilingual active alerts with Amazon Polly voice instructions.

**Sample Response:**
```json
{
  "count": 1,
  "alerts": [
    {
      "alert_id": "alt-melamchi-001",
      "risk_level": "CRITICAL",
      "risk_score": 82,
      "message_en": "URGENT EVACUATION: Critical flood and debris surge (82/100) detected in Melamchi Basin! Move to Melamchi Upper Community Hilltop Ridge (1280m) immediately.",
      "message_ne": "अति जरुरी सूचना: मेलम्ची क्षेत्रमा उच्च बाढी र पहिरोको गम्भीर जोखिम (82/100) पत्ता लागेको छ। तुरुन्तै सुरक्षित उच्च स्थान मेलम्ची डाँडातर्फ जानुहोस्।",
      "polly_voice_config": {
        "voice_id": "Aditi",
        "language_code": "hi-IN",
        "text": "अति जरुरी सूचना: मेलम्ची क्षेत्रमा उच्च बाढी र पहिरोको गम्भीर जोखिम पत्ता लागेको छ।"
      },
      "delivery_status": "SENT",
      "channels": ["SMS", "POLICE_RADIO", "POLLY_VOICE", "SIRENS"]
    }
  ]
}
```

---

### 6. `GET /rescue`
Returns emergency evacuation deployment cases.

**Sample Response:**
```json
{
  "count": 1,
  "rescue_cases": [
    {
      "case_id": "rec-case-001",
      "zone_id": "melamchi-basin",
      "priority": "P1_URGENT",
      "status": "DEPLOYED",
      "target_location": "Melamchi Bazaar Riverside Market",
      "evacuation_safe_zone": "Melamchi Upper Community Hilltop Ridge (1280m)",
      "people_to_evacuate": 4200,
      "assigned_units": ["Nepal Army Disaster Management", "APF Unit 22"]
    }
  ]
}
```

---

### 7. `POST /simulate-event` (🔥 Hackathon Slider Superpower)
Feeds the interactive time-series slider on the frontend dashboard.

**Request Body (Preset Historical Scenario):**
```json
{
  "scenario": "melamchi_2021"
}
```

**Response:**
Returns 5 sequential disaster progression steps:
1. `Step 1`: T-12h Monsoon Rain Accumulation (Risk: 25 - LOW)
2. `Step 2`: T-6h Cloudburst in Upper Catchment (Risk: 54 - MODERATE)
3. `Step 3`: T-2h Moraine Instability & Dam Formation (Risk: 74 - HIGH)
4. `Step 4`: T-0 Cascading Breach & Debris Surge (Risk: 82 - CRITICAL) ➔ Hydropower & Bridges in Lockdown
5. `Step 5`: T+3h Aftermath & Structural Damage (Risk: 88 - CRITICAL)

Or send custom telemetry inputs:
```json
{
  "rainfall_24h": 142,
  "slope": 37.2,
  "lake_change": 0.21,
  "displacement": 0.14
}
```
Output:
```json
{
  "scenario": "custom",
  "risk_score": 82,
  "risk_level": "CRITICAL"
}
```
