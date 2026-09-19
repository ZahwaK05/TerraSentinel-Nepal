# 🌏 TerraSentinel-Nepal

> **Cloud-native platform for predicting cascading floods and glacial lake outburst floods (GLOFs), identifying exposed infrastructure, and delivering location-specific safety alerts in Nepal.**

[![Project Status](https://img.shields.io/badge/status-MVP%20Development-orange)](https://github.com/your-org/TerraSentinel-Nepal)
[![License](https://img.shields.io/badge/license-MIT-blue)](LICENSE)
[![Data: Historical](https://img.shields.io/badge/data-historical%20%7C%20simulated-yellow)]()

---

## 📋 Table of Contents

- [Purpose](#purpose)
- [Architecture](#architecture)
- [Quick Start](#quick-start)
- [Demonstration Flow (Melamchi Scenario)](#demonstration-flow-melamchi-scenario)
- [Directory Structure](#directory-structure)
- [Data Sources & Licensing](#data-sources--licensing)
- [Project Status](#project-status)
- [Team & Contact](#team--contact)

---

## Purpose

TerraSentinel-Nepal ingests satellite imagery (SAR/optical), rainfall measurements, digital elevation models (DEMs), and critical infrastructure data to:

1. **Predict** flood extent and GLOF propagation corridors using a risk-scoring model.
2. **Identify** exposed roads, bridges, hospitals, and communities within predicted impact zones.
3. **Deliver** location-specific safety alerts in Nepali (text and synthesized voice) without contacting real citizens during testing.
4. **Record** all data sources, model assumptions, limitations, and system decisions for full auditability.

> ⚠️ **Data Transparency Notice**
> All data displayed in the current demo is **historical or simulated**. No real-time data feeds or live citizen notifications are active during the demonstration phase.

---

## Architecture

```
Data Ingestion (Lambda) → Geospatial Processing (SAR/NDWI/DEM) → ML Risk Scorer → Alert Dispatcher → Frontend Dashboard
```

Cloud: AWS (S3, Lambda, SageMaker, API Gateway, CloudFront)
IaC:   Terraform / CloudFormation

---

## Quick Start

### Prerequisites

| Tool | Minimum Version |
|------|----------------|
| Node.js | 18 LTS |
| Python | 3.11 |
| AWS CLI | 2.x |
| Terraform | 1.6+ |
| Docker | 24+ |

### 1. Clone & configure

```bash
git clone https://github.com/your-org/TerraSentinel-Nepal.git
cd TerraSentinel-Nepal
cp .env.example .env
```

### 2. Install dependencies

```bash
cd frontend && npm install
pip install -r services/requirements.txt
pip install -r ml/requirements.txt
pip install -r geospatial/requirements.txt
```

### 3. Run locally (demo mode)

```bash
cd frontend && npm run dev
python services/risk-scorer/run_local.py --scenario melamchi --mode demo
```

Open http://localhost:3000

---

## Demonstration Flow (Melamchi Scenario)

The MVP demonstrates the **June 2021 Melamchi flood** as a historical replay:

| Step | Component | What Happens |
|------|-----------|-------------|
| 1 | Data Ingestion | Load sample SAR, rainfall, DEM, infrastructure from data/sample/melamchi/ |
| 2 | Geospatial Processing | Compute NDWI water change, flood extent polygon, DEM-derived flow corridors |
| 3 | Risk Scoring | Generate risk score per grid cell with feature-importance breakdown |
| 4 | Impact Identification | Intersect flood polygon with infrastructure; list exposed assets |
| 5 | Alert Generation | Produce mock Nepali text and audio alerts (no real delivery) |
| 6 | Dashboard Display | Show all layers, timeline slider, risk scores, alert previews |

**Success Criteria:**
- Pipeline completes end-to-end in under 5 minutes.
- All sample data loads without manual intervention.
- Map displays risk zones, impact corridor, and at least 3 exposed infrastructure assets.
- Alert panel shows Nepali text and playable audio for at least 2 mock zones.
- Data-source labels identify [HISTORICAL] or [SIMULATED] on every layer.

---

## Directory Structure

```
TerraSentinel-Nepal/
├── frontend/          # React/Next.js command dashboard
├── services/          # Lambda functions & application services
├── ml/                # SageMaker training & inference code
├── geospatial/        # SAR, NDWI, DEM, impact-corridor processing
├── infrastructure/    # AWS IaC (Terraform & CloudFormation)
├── data/sample/       # Small, approved demonstration datasets only
├── tests/             # Integration & end-to-end tests
├── docs/              # Architecture, data, risk methodology, guides
└── .github/           # CI/CD workflows, issue & PR templates
```

---

## Data Sources & Licensing

| Dataset | Source | License | Status |
|---------|--------|---------|--------|
| Sentinel-1 SAR | ESA Copernicus | Open – CC BY-SA | Sample included |
| ALOS DEM 30m | JAXA | Free for research | Sample included |
| GPM Rainfall | NASA | Open | Sample included |
| OSM Infrastructure | OpenStreetMap | ODbL | Sample included |
| Melamchi river gauge | DHM Nepal | Requires attribution | Sample included |

---

## Project Status

| Milestone | Target | Status |
|-----------|--------|--------|
| Repository setup & architecture | Days 1–2 | Done |
| Melamchi dataset pipeline | Days 3–7 | In Progress |
| Module integration & tests | Week 2 | Planned |
| Dashboard, alerts, voice | Week 3 | Planned |
| Integration & security testing | Week 4 | Planned |
| v1.0.0-demo release | Final days | Planned |

---

## Team & Contact

Maintain team contact details in the project wiki. For security issues, see SECURITY.md. For contribution guidelines, see CONTRIBUTING.md.
