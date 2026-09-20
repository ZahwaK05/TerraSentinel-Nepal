"""
TerraSentinel-Nepal: Lambda 1 - process-data
Ingests, validates, and normalizes raw satellite, meteorological, and geospatial telemetry.
"""
import os
import json
import logging
from datetime import datetime, timezone

try:
    import boto3
    from botocore.exceptions import ClientError
    s3_client = boto3.client("s3")
except ImportError:
    boto3 = None
    ClientError = Exception
    s3_client = None

logger = logging.getLogger()
logger.setLevel(logging.INFO)

S3_BUCKET = os.environ.get("S3_DATA_BUCKET", "terrasentinel-geodata-local")

BASIN_METADATA = {
    "melamchi-basin": {
        "name": "Melamchi River Basin",
        "district": "Sindhupalchok",
        "coordinates": {"lat": 27.8311, "lon": 85.5804},
        "default_slope": 37.2
    },
    "bhotekoshi-basin": {
        "name": "Bhotekoshi River Basin",
        "district": "Sindhupalchok",
        "coordinates": {"lat": 27.9388, "lon": 85.8922},
        "default_slope": 39.5
    },
    "tamur-basin": {
        "name": "Tamur River Basin",
        "district": "Taplejung",
        "coordinates": {"lat": 27.3500, "lon": 87.7167},
        "default_slope": 34.0
    },
    "marsyangdi-basin": {
        "name": "Marsyangdi River Basin",
        "district": "Lamjung / Manang",
        "coordinates": {"lat": 28.2167, "lon": 84.3833},
        "default_slope": 36.8
    }
}

def parse_incoming_event(event):
    """
    Extracts raw payload from either direct event invocations, 
    EventBridge S3 Put notifications, or Step Function inputs.
    """
    # 1. EventBridge S3 event
    if "detail" in event and "bucket" in event["detail"] and "object" in event["detail"]:
        bucket = event["detail"]["bucket"]["name"]
        key = event["detail"]["object"]["key"]
        logger.info(f"Fetching raw data from s3://{bucket}/{key}")
        try:
            response = s3_client.get_object(Bucket=bucket, Key=key)
            content = response["Body"].read().decode("utf-8")
            return json.loads(content)
        except Exception as e:
            logger.error(f"Failed to read from S3: {str(e)}")
            raise e

    # 2. S3 direct event notification
    if "Records" in event and len(event["Records"]) > 0 and "s3" in event["Records"][0]:
        bucket = event["Records"][0]["s3"]["bucket"]["name"]
        key = event["Records"][0]["s3"]["object"]["key"]
        logger.info(f"Fetching raw data from direct S3 notification: {bucket}/{key}")
        response = s3_client.get_object(Bucket=bucket, Key=key)
        return json.loads(response["Body"].read().decode("utf-8"))

    # 3. Direct JSON payload (from simulation or API Gateway)
    if "raw_data" in event or "zone_id" in event:
        return event

    return event

def lambda_handler(event, context):
    """
    Lambda entry point for process-data
    """
    logger.info(f"Received raw ingest event: {json.dumps(event)}")
    payload = parse_incoming_event(event)

    zone_id = payload.get("zone_id", "melamchi-basin")
    timestamp = payload.get("timestamp", datetime.now(timezone.utc).isoformat())
    meta = BASIN_METADATA.get(zone_id, BASIN_METADATA["melamchi-basin"])

    raw_data = payload.get("raw_data", payload)

    # Normalize rainfall readings
    rainfall_history = raw_data.get("rainfall_history_mm", [])
    if not rainfall_history and "precipitation_mm" in raw_data:
        p = raw_data["precipitation_mm"]
        rainfall_history = p if isinstance(p, list) else [p]
    elif not rainfall_history and "rainfall_24h" in raw_data:
        rainfall_history = [raw_data["rainfall_24h"]]

    # Normalize terrain slope
    slope = float(raw_data.get("slope", raw_data.get("dem_slope_degrees", meta["default_slope"])))

    # Normalize glacial lake expansion / NDWI delta
    ndwi_delta = raw_data.get("lake_change", raw_data.get("ndwi_delta", None))
    if ndwi_delta is None:
        ndwi_curr = float(raw_data.get("ndwi_current", 0.60))
        ndwi_base = float(raw_data.get("ndwi_baseline", 0.40))
        ndwi_delta = round(ndwi_curr - ndwi_base, 3)
    else:
        ndwi_delta = float(ndwi_delta)

    # Normalize SAR displacement (interferometry)
    displacement = float(raw_data.get("displacement", raw_data.get("sar_displacement_m", 0.08)))

    normalized_payload = {
        "event_id": payload.get("event_id", f"evt-{int(datetime.now(timezone.utc).timestamp())}"),
        "zone_id": zone_id,
        "zone_name": meta["name"],
        "district": meta["district"],
        "coordinates": meta["coordinates"],
        "timestamp": timestamp,
        "normalized_inputs": {
            "rainfall_readings_mm": rainfall_history,
            "dem_slope": slope,
            "ndwi_expansion_delta": ndwi_delta,
            "sar_displacement_m": displacement
        },
        "simulation_step": payload.get("simulation_step", 1),
        "source": payload.get("source", "sentinel-pipeline-v1")
    }

    # Store normalized object to S3 processed-data/ if S3 is accessible
    processed_key = f"processed-data/{zone_id}/{timestamp.replace(':', '-')}.json"
    try:
        s3_client.put_object(
            Bucket=S3_BUCKET,
            Key=processed_key,
            Body=json.dumps(normalized_payload, indent=2),
            ContentType="application/json"
        )
        normalized_payload["processed_s3_uri"] = f"s3://{S3_BUCKET}/{processed_key}"
        logger.info(f"Stored processed data to {normalized_payload['processed_s3_uri']}")
    except (ClientError, Exception) as e:
        # Gracefully log warning so local offline testing continues smoothly
        logger.warning(f"Could not persist to S3 (running in local/mock mode?): {str(e)}")
        normalized_payload["processed_s3_uri"] = f"mock://{S3_BUCKET}/{processed_key}"

    return normalized_payload
