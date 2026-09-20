# TerraSentinel-Nepal Backend: Building a Cloud-Native Disaster Intelligence Pipeline

## Introduction

Natural hazards in Himalayan river basins can develop through a combination of environmental conditions such as intense rainfall, terrain instability, glacial-lake changes, and ground displacement. Turning these signals into useful emergency information requires more than an individual machine-learning model. It requires a complete pipeline that can ingest data, process it, generate risk assessments, identify potentially affected infrastructure and communities, and expose the results to a decision-support application.

This is the role of the TerraSentinel-Nepal backend.

The backend is designed as a serverless, event-driven AWS architecture that connects geospatial data processing, risk inference, impact analysis, alert generation, data persistence, and REST APIs.

The overall workflow is:

```text
COLLECT DATA
      ↓
PROCESS GEOSPATIAL DATA
      ↓
GENERATE RISK
      ↓
ANALYZE IMPACT
      ↓
ALERT
      ↓
RESCUE
```

---

# 1. Backend Architecture

The TerraSentinel-Nepal backend is implemented using AWS serverless services and Python-based Lambda functions.

At a high level, the architecture follows:

```text
Environmental / Geospatial Data
              |
              v
          Amazon S3
              |
              v
       AWS Step Functions
              |
      +-------+-------+
      |       |       |
      v       v       v
   Process Calculate  Risk
    Data    Features  Model
      |       |       |
      +-------+-------+
              |
              v
       Generate Alert
              |
      +-------+-------+
      |       |       |
      v       v       v
    Risk  Infrastructure
   Events     Alerts
      \       /
       \     /
     Rescue Cases
              |
              v
        API Gateway
              |
              v
        Next.js Frontend
```

The infrastructure is defined using AWS SAM, allowing the cloud resources and application configuration to be managed as infrastructure-as-code.

---

# 2. Why a Pipeline Architecture?

Disaster intelligence involves multiple processing stages.

Instead of implementing the entire workflow inside one large backend function, TerraSentinel separates the processing into independent Lambda functions.

The main backend functions are:

```text
process_data
calculate_features
run_risk_model
generate_alert
api_handler
```

The first four functions participate in the main risk-processing workflow, while the API handler exposes backend capabilities to the frontend and supports simulation workflows.

This separation makes individual components easier to develop, test, deploy, and maintain.

---

# 3. Data Processing

The first stage of the backend pipeline is handled by:

```text
backend/functions/process_data/app.py
```

This function processes incoming environmental and geospatial information and converts it into a consistent structure for downstream processing.

The backend architecture works with environmental information such as:

- Rainfall
- Terrain slope
- NDWI-related changes
- SAR displacement
- Geographic coordinates
- Basin information
- Event timestamps

The normalized structure can contain information such as:

```json
{
  "event_id": "event-id",
  "zone_id": "melamchi-basin",
  "zone_name": "Melamchi River Basin",
  "district": "Sindhupalchok",
  "coordinates": {
    "lat": 27.8311,
    "lon": 85.5804
  },
  "normalized_inputs": {
    "rainfall_readings_mm": [],
    "dem_slope": 37.2,
    "ndwi_expansion_delta": 0.21,
    "sar_displacement_m": 0.14
  }
}
```

The processing stage creates a consistent boundary between incoming environmental information and model-ready information.

The backend also supports storing processed information in Amazon S3.

---

# 4. Feature Calculation

The second stage is implemented by:

```text
backend/functions/calculate_features/app.py
```

This function transforms normalized environmental information into features used by the risk-inference stage.

Important indicators include:

```text
24-hour rainfall
Terrain slope
NDWI change
SAR ground displacement
```

These features represent different environmental conditions that may contribute to elevated risk.

Conceptually:

```text
Heavy Rainfall
      +
Terrain Conditions
      +
Water-body Change
      +
Ground Displacement
      ↓
Risk Features
```

The feature-calculation stage therefore acts as the bridge between environmental observations and the risk-inference component.

---

# 5. Risk Inference

The third stage is implemented in:

```text
backend/functions/run_risk_model/app.py
```

This Lambda is responsible for generating the risk assessment.

The model input follows the core feature structure:

```json
{
  "rainfall_24h": 142,
  "slope": 37.2,
  "lake_change": 0.21,
  "displacement": 0.14
}
```

The expected output follows the TerraSentinel risk format:

```json
{
  "risk_score": 82,
  "risk_level": "CRITICAL"
}
```

The primary inference mechanism is Amazon SageMaker.

The Lambda invokes the configured SageMaker endpoint and converts the returned model result into the standardized TerraSentinel risk representation.

---

# 6. Risk Classification

The backend converts the continuous risk score into four risk levels:

```text
0–39    → LOW
40–64   → MODERATE
65–79   → HIGH
80–100  → CRITICAL
```

For example:

```text
Risk Score: 32
Risk Level: LOW
```

or:

```text
Risk Score: 82
Risk Level: CRITICAL
```

The risk score is used as a spatial risk-prioritization value rather than being interpreted as a calibrated probability of disaster.

---

# 7. Fallback Risk Inference

An important aspect of the backend is that the demonstration pipeline does not depend entirely on the availability of the SageMaker endpoint.

If SageMaker is unavailable, the risk-model Lambda contains a fallback inference mechanism.

The fallback uses the main environmental factors:

```text
Rainfall
Lake expansion
Slope
Ground displacement
```

The implementation also considers combinations of environmental conditions when calculating the fallback risk.

This provides a mechanism for continuing local development and demonstration when the external machine-learning inference endpoint is unavailable.

The inference response also identifies the inference mechanism being used.

---

# 8. Alert Generation

After risk inference, the pipeline moves to:

```text
backend/functions/generate_alert/app.py
```

This function evaluates the generated risk information and produces downstream alert and response information.

The alert stage connects risk information with:

- Infrastructure
- Alerts
- Rescue cases
- Notification services
- Voice generation

The resulting workflow becomes:

```text
Risk Score
     ↓
Risk Level
     ↓
Impact Analysis
     ↓
Alert
     ↓
Response Information
```

This allows the backend to move beyond simply producing a numerical risk score.

---

# 9. Infrastructure Impact Analysis

The backend maintains infrastructure information using DynamoDB.

The infrastructure layer supports assets such as:

- Hydropower facilities
- Water-intake infrastructure
- Bridges
- Highways
- Dams

An infrastructure record can contain information such as:

```json
{
  "infra_id": "bridge-melamchi-pul",
  "name": "Melamchi Motor Bridge",
  "type": "Bridge / Highway",
  "zone_id": "melamchi-basin",
  "status": "EMERGENCY_LOCKDOWN",
  "risk_score": 82,
  "criticality": "CRITICAL",
  "coordinates": {
    "lat": 27.8285,
    "lon": 85.5780
  }
}
```

This allows environmental risk to be associated with potentially exposed physical infrastructure.

---

# 10. Population and Evacuation Information

The backend also maintains settlement and evacuation information.

A settlement record can contain information such as:

```text
Settlement
Population
Household count
Elevation
Vulnerability
Evacuation safe zone
Safe-zone elevation
Safe-zone capacity
Travel time
```

This creates an additional relationship between environmental risk and population exposure:

```text
Environmental Risk
       ↓
Affected Zone
       ↓
Population Exposure
       ↓
Evacuation Information
```

The backend's demonstration data includes settlement and evacuation information for the Melamchi region.

---

# 11. Alerts and Voice Generation

The alert-generation component has access to AWS notification and voice services including:

```text
Amazon SNS
Amazon Polly
```

Amazon SNS provides notification capabilities, while Amazon Polly provides text-to-speech functionality.

The backend also supports bilingual alert information in:

```text
English
Nepali
```

This provides a foundation for delivering disaster information in multiple communication formats.

---

# 12. Rescue Cases

The final operational stage is the rescue layer.

The backend maintains a dedicated DynamoDB table:

```text
TerraSentinel-RescueCases
```

A rescue case can contain information such as:

```text
Case ID
Priority
Status
Target location
Coordinates
People affected
Evacuation safe zone
Assigned response units
```

The conceptual workflow is:

```text
Environmental Data
       ↓
Risk
       ↓
Impact
       ↓
Alert
       ↓
Rescue Priority
```

This connects environmental intelligence with emergency-response information.

---

# 13. Step Functions Orchestration

The complete risk pipeline is orchestrated using AWS Step Functions.

The state-machine definition is located at:

```text
backend/statemachine/risk_pipeline.asl.json
```

The workflow follows:

```text
Start
  ↓
PreprocessData
  ↓
CalculateFeatures
  ↓
RunRiskInference
  ↓
EvaluateAndGenerateAlerts
  ↓
PipelineCompleted
```

Each processing stage is implemented as an independent Lambda task.

The state machine also provides retry behavior for selected transient Lambda and AWS SDK errors.

If the pipeline encounters an unrecoverable error, the workflow transitions to:

```text
PipelineFailed
```

This provides explicit workflow-level error handling.

---

# 14. Data Persistence with DynamoDB

The backend defines four primary DynamoDB tables:

```text
TerraSentinel-RiskEvents
TerraSentinel-Infrastructure
TerraSentinel-Alerts
TerraSentinel-RescueCases
```

These tables represent different categories of operational information.

```text
RiskEvents
    ↓
Current risk information

Infrastructure
    ↓
Potentially exposed assets

Alerts
    ↓
Generated warnings and notifications

RescueCases
    ↓
Emergency-response cases
```

The backend architecture uses DynamoDB's on-demand billing model for these tables.

---

# 15. API Gateway

The backend exposes its functionality through an HTTP API.

The API handler supports routes including:

```text
GET  /risk
GET  /risk/{zone}
GET  /infrastructure
GET  /population
GET  /alerts
GET  /rescue
POST /simulate-event
GET  /risk-map/{year}
```

This allows the frontend to consume backend information through a defined API layer rather than accessing AWS data stores directly.

The architecture becomes:

```text
Next.js
   ↓
API Gateway
   ↓
API Lambda
   ↓
DynamoDB / Step Functions
```

This provides separation between the user interface and backend infrastructure.

---

# 16. Disaster Simulation

The backend includes a scenario simulation mechanism.

The endpoint:

```text
POST /simulate-event
```

can receive:

```json
{
  "scenario": "melamchi_2021"
}
```

The demonstration scenario represents a sequence of changing environmental conditions:

```text
T-12h
Monsoon Rain Accumulation
Risk: 25
        ↓
T-6h
Cloudburst in Upper Catchment
Risk: 54
        ↓
T-2h
Moraine Instability & Dam Formation
Risk: 74
        ↓
T-0
Cascading Breach & Debris Surge
Risk: 82
        ↓
T+3h
Aftermath & Structural Damage
Risk: 88
```

The simulation provides an interactive way to demonstrate how risk information can change over the course of an event.

The API also supports custom telemetry inputs for simulation workflows.

---

# 17. Local Development

The backend contains local development and simulation utilities.

Important scripts include:

```text
backend/scripts/local_server.py
backend/scripts/trigger_simulation.py
```

The local API server can be started using:

```bash
python scripts/local_server.py --port 8000
```

The local simulation can be triggered using:

```bash
python scripts/trigger_simulation.py --mode local
```

This makes it possible to develop and demonstrate the backend without requiring every AWS service to be continuously active.

The local workflow becomes:

```text
Local Data
   ↓
Process Data
   ↓
Calculate Features
   ↓
Risk Inference
   ↓
Alert Generation
   ↓
Local API
   ↓
Frontend
```

---

# 18. Infrastructure as Code

The backend infrastructure is defined in:

```text
backend/template.yaml
```

AWS SAM is used to define and deploy the required cloud resources.

The architecture includes services such as:

```text
Amazon S3
AWS Lambda
Amazon DynamoDB
Amazon API Gateway
AWS Step Functions
Amazon SageMaker integration
Amazon SNS
Amazon Polly
IAM permissions
```

The backend can be built using:

```bash
sam build
```

and deployed using:

```bash
sam deploy --guided
```

Using infrastructure-as-code makes the cloud environment reproducible and easier to manage.

---

# 19. Backend Testing

The repository contains backend tests in:

```text
backend/tests/test_pipeline.py
```

The test suite can be executed using:

```bash
python -m unittest discover -s tests
```

Testing is important because the backend contains several connected stages:

```text
Data Processing
      ↓
Feature Calculation
      ↓
Risk Inference
      ↓
Alert Generation
      ↓
API
```

The tests provide a way to validate the pipeline components independently before deployment.

---

# 20. Backend-to-Frontend Integration

The backend ultimately provides data to the TerraSentinel decision-support dashboard.

The complete application architecture is:

```text
                ENVIRONMENTAL DATA
                        |
                        v
                    Amazon S3
                        |
                        v
                AWS Step Functions
                        |
        +---------------+---------------+
        |               |               |
        v               v               v
  Process Data   Calculate Features  Risk Model
        |               |               |
        +---------------+---------------+
                        |
                        v
                 Generate Alert
                        |
             +----------+----------+
             |          |          |
             v          v          v
          RiskEvents Infrastructure Alerts
                                    |
                                    v
                              Rescue Cases
                        |
                        v
                  Amazon API Gateway
                        |
                        v
                    Next.js UI
```

The result is an end-to-end path from environmental information to a human-facing decision-support interface.

---

# 21. Technology Stack

## Backend

```text
Python
AWS Lambda
AWS Step Functions
Amazon S3
Amazon DynamoDB
Amazon SageMaker
Amazon API Gateway
Amazon SNS
Amazon Polly
AWS SAM
```

## Data and Intelligence

```text
Geospatial Data
Environmental Data
Rainfall
Terrain Features
NDWI
SAR Displacement
Risk Inference
Spatial Risk Analysis
```

## Frontend Integration

```text
Next.js
React
TypeScript
REST API
```

---

# 22. Backend Repository Structure

```text
backend/
│
├── functions/
│   ├── api_handler/
│   ├── process_data/
│   ├── calculate_features/
│   ├── run_risk_model/
│   └── generate_alert/
│
├── statemachine/
│   └── risk_pipeline.asl.json
│
├── scripts/
│   ├── local_server.py
│   ├── trigger_simulation.py
│   ├── seed_nepal_data.py
│   └── nepal_seed_data.json
│
├── tests/
│   └── test_pipeline.py
│
├── template.yaml
└── samconfig.toml
```

---

# 23. End-to-End Workflow

The TerraSentinel backend can be summarized through six major stages.

## Stage 1: Collect Data

Environmental and geospatial information enters the system.

```text
Rainfall
Terrain
Satellite-derived information
Geospatial features
```

## Stage 2: Process Geospatial Data

The incoming information is validated and normalized.

```text
Raw Data
   ↓
Validation
   ↓
Normalization
   ↓
Processed Data
```

## Stage 3: Generate Risk

The processed features are sent to the risk-inference layer.

```text
Processed Features
        ↓
SageMaker / Fallback Model
        ↓
Risk Score
        ↓
Risk Level
```

## Stage 4: Analyze Impact

The risk information is connected with:

```text
Infrastructure
Population
Settlements
Evacuation Zones
```

## Stage 5: Alert

The system generates warning information and supports notification and voice-generation capabilities.

```text
Risk
 ↓
Alert
 ↓
Notification
```

## Stage 6: Rescue

The system creates and exposes response information through rescue cases.

```text
Alert
 ↓
Response Priority
 ↓
Rescue Case
 ↓
Decision Support
```

---

# 24. Design Philosophy

The TerraSentinel backend follows a simple principle:

> Risk information becomes more useful when it is connected to the assets, communities, alerts, and response information surrounding the event.

Therefore, the backend does not stop at risk inference.

Instead, it connects:

```text
Environmental Data
        ↓
Geospatial Processing
        ↓
Risk Inference
        ↓
Impact Analysis
        ↓
Alert Generation
        ↓
Rescue Information
```

This creates a single pipeline from environmental observation to emergency decision support.

---

# 25. Future Backend Development

The current backend establishes the core cloud architecture and demonstration workflow.

Future development can extend the system with:

```text
Real-time satellite ingestion
        ↓
Automated geospatial processing
        ↓
Continuous risk updates
        ↓
Improved supervised ML models
        ↓
Real-time alert delivery
        ↓
Advanced rescue optimization
```

Additional Himalayan river basins can also be integrated using the same architecture.

Future versions can also incorporate stronger event inventories, improved model validation, additional environmental data sources, real-time sensor streams, and more advanced infrastructure-impact analysis.

---

# Conclusion

The TerraSentinel-Nepal backend provides a cloud-native foundation for transforming environmental and geospatial information into disaster decision-support information.

Its core workflow is:

```text
COLLECT DATA
      ↓
PROCESS GEOSPATIAL DATA
      ↓
GENERATE RISK
      ↓
ANALYZE IMPACT
      ↓
ALERT
      ↓
RESCUE
```

By combining AWS Lambda, Step Functions, S3, DynamoDB, SageMaker, API Gateway, SNS, and Polly, the backend connects data processing, risk inference, impact analysis, alert generation, and emergency-response information into a single architecture.

The backend is therefore more than an API layer. It provides the processing and cloud infrastructure required to move from environmental observations to structured risk intelligence and operational decision support.

---

## TerraSentinel-Nepal Backend

```text
DATA
  ↓
GEOSPATIAL PROCESSING
  ↓
RISK INTELLIGENCE
  ↓
IMPACT ANALYSIS
  ↓
ALERTS
  ↓
RESCUE
```

**A cloud-native backend for transforming geospatial disaster data into actionable decision-support information.**
