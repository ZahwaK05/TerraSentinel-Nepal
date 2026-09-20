# 🌍 TerraSentinel-Nepal

> **AI-Powered Geospatial Disaster Intelligence & Decision Support Platform for the Himalayas**

TerraSentinel-Nepal is a cloud-native disaster intelligence platform designed to support disaster preparedness, risk assessment, and emergency response in disaster-prone Himalayan regions.

The platform combines **AI/ML, geospatial analysis, satellite observations, environmental data, and AWS cloud infrastructure** to transform fragmented disaster-related data into actionable spatial intelligence.

---

## 🚨 The Problem

Himalayan regions are exposed to cascading hazards including:

- 🌧️ Extreme rainfall and flooding
- 🏔️ Landslides
- 🧊 Glacial-lake-related hazards
- 🌊 Debris flows and cascading disasters
- 🏗️ Damage to critical infrastructure
- 🚑 Difficult post-disaster search and rescue

Disaster-management and emergency-response teams often need to make decisions using fragmented environmental, satellite, terrain, and hazard information.

TerraSentinel brings these signals together into a unified decision-support platform.

---

## 💡 Our Solution

TerraSentinel follows a:

**Predict → Protect → Locate → Rescue**

workflow.

### 1. Predict
Analyze rainfall, terrain, satellite and environmental information to identify areas requiring greater attention.

### 2. Protect
Identify potentially exposed infrastructure and settlements and provide risk information for decision support.

### 3. Locate
Use post-disaster geospatial information to identify areas requiring search and assessment.

### 4. Rescue
Combine available damage and ground/drone observations to prioritize emergency search and rescue operations.

---

## 🗺️ Current Study Area

The current implementation focuses on the **Melamchi watershed in Nepal**.

The project includes scenario-based analysis associated with:

- **Melamchi 2021**
- **Melamchi 2026**

The current geospatial risk engine operates on:

- **32,435 grid cells**
- **100m × 100m spatial resolution**

---

# 🤖 AI / ML Risk Intelligence

The current V1 risk engine generates a **0–100 spatial risk-prioritization score** for each grid cell.

> **Important:** The score is a spatial prioritization index, not a calibrated probability of a landslide.

The V1 score combines three components:

```text
             Rainfall Trigger
                    +
          Terrain Susceptibility
                    +
        Glacial-Lake Proximity
                    │
                    ▼
          V1 Risk Score (0–100)
