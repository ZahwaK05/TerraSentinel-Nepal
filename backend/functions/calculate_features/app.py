"""
TerraSentinel-Nepal: Lambda 2 - calculate-features
Transforms normalized geospatial telemetry into high-signal feature vectors for ML inference:
- 24-hour cumulative precipitation (mm)
- DEM slope gradient (degrees)
- NDWI glacial lake surface area expansion delta
- Sentinel-1 SAR interferometry displacement (m)
"""
import json
import logging

logger = logging.getLogger()
logger.setLevel(logging.INFO)

def calculate_24h_rainfall(readings):
    """
    Computes 24h cumulative rainfall from time series or single metric.
    """
    if not readings:
        return 45.0  # Default moderate baseline
    if isinstance(readings, (int, float)):
        return float(readings)
    if isinstance(readings, list):
        # If readings is a list of hourly or 6-hourly values, sum them
        return round(float(sum(readings)), 2)
    return 45.0

def lambda_handler(event, context):
    """
    Extracts and scales the four primary features expected by SageMaker:
    {
      "rainfall_24h": 142,
      "slope": 37.2,
      "lake_change": 0.21,
      "displacement": 0.14
    }
    """
    logger.info(f"Extracting features from payload: {json.dumps(event)}")
    
    normalized = event.get("normalized_inputs", event)
    
    # Feature 1: rainfall_24h
    rainfall_raw = normalized.get("rainfall_readings_mm", normalized.get("rainfall_24h", 85.0))
    rainfall_24h = calculate_24h_rainfall(rainfall_raw)

    # Feature 2: slope (DEM terrain gradient)
    slope = float(normalized.get("dem_slope", normalized.get("slope", 35.0)))
    slope = round(max(0.0, min(80.0, slope)), 2)

    # Feature 3: lake_change (NDWI delta / glacial lake expansion ratio)
    lake_change = float(normalized.get("ndwi_expansion_delta", normalized.get("lake_change", 0.10)))
    lake_change = round(max(-0.5, min(1.0, lake_change)), 3)

    # Feature 4: displacement (SAR surface drift in meters)
    displacement = float(normalized.get("sar_displacement_m", normalized.get("displacement", 0.05)))
    displacement = round(max(0.0, min(2.5, displacement)), 3)

    # Compute composite saturation index as auxiliary metadata
    antecedent_moisture = round(min(1.0, (rainfall_24h / 200.0) * 0.7 + (lake_change * 1.5)), 3)

    feature_vector = {
        "rainfall_24h": rainfall_24h,
        "slope": slope,
        "lake_change": lake_change,
        "displacement": displacement
    }

    response_payload = {
        "event_id": event.get("event_id", "evt-default"),
        "zone_id": event.get("zone_id", "melamchi-basin"),
        "zone_name": event.get("zone_name", "Melamchi River Basin"),
        "district": event.get("district", "Sindhupalchok"),
        "coordinates": event.get("coordinates", {"lat": 27.8311, "lon": 85.5804}),
        "timestamp": event.get("timestamp"),
        "simulation_step": event.get("simulation_step", 1),
        "model_features": feature_vector,
        "auxiliary_features": {
            "antecedent_moisture_index": antecedent_moisture,
            "debris_flow_velocity_est_mps": round(2.5 + (slope / 10.0) * 1.2 + (displacement * 8.0), 2)
        }
    }

    logger.info(f"Calculated feature vector: {json.dumps(feature_vector)}")
    return response_payload
