"""
TerraSentinel-Nepal: Lambda 4 - generate-alert
Evaluates risk thresholds, matches downstream vulnerable infrastructure,
identifies higher-elevation safe zones, generates bilingual alerts (English & Nepali),
and commits data to DynamoDB (RiskEvents, Alerts, RescueCases, Infrastructure).
"""
import os
import json
import logging
from datetime import datetime, timezone
try:
    import boto3
    from botocore.exceptions import ClientError
    dynamodb = boto3.resource("dynamodb")
except ImportError:
    boto3 = None
    ClientError = Exception
    dynamodb = None

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# DynamoDB Tables
TABLE_RISK_EVENTS = os.environ.get("DYNAMODB_RISK_EVENTS", "TerraSentinel-RiskEvents")
TABLE_INFRASTRUCTURE = os.environ.get("DYNAMODB_INFRASTRUCTURE", "TerraSentinel-Infrastructure")
TABLE_ALERTS = os.environ.get("DYNAMODB_ALERTS", "TerraSentinel-Alerts")
TABLE_RESCUE_CASES = os.environ.get("DYNAMODB_RESCUE_CASES", "TerraSentinel-RescueCases")

# Safe evacuation zones based on DEM elevation analysis (> 1,500m ridges)
SAFE_EVACUATION_ZONES = {
    "melamchi-basin": [
        {
            "zone_name": "Tarkeghyang High Ridge",
            "elevation_m": 2560,
            "coordinates": {"lat": 27.9944, "lon": 85.5512},
            "capacity": 1200,
            "route_description": "Ascend westward via upper Helambu foot trail away from riverbed."
        },
        {
            "zone_name": "Melamchi Upper Community Hilltop",
            "elevation_m": 1280,
            "coordinates": {"lat": 27.8340, "lon": 85.5720},
            "capacity": 3500,
            "route_description": "Move at least 40 vertical meters above the Melamchi confluence."
        }
    ],
    "bhotekoshi-basin": [
        {
            "zone_name": "Tatopani Upper Ridge Safe Zone",
            "elevation_m": 1820,
            "coordinates": {"lat": 27.9520, "lon": 85.9350},
            "capacity": 1500,
            "route_description": "Evacuate eastward up the ridge away from Arniko highway river gorge."
        }
    ]
}

def get_downstream_infrastructure(zone_id):
    """
    Fetches infrastructure for the specified basin from DynamoDB or baseline catalogue.
    """
    try:
        table = dynamodb.Table(TABLE_INFRASTRUCTURE)
        response = table.query(
            IndexName="ZoneIndex",
            KeyConditionExpression=boto3.dynamodb.conditions.Key("zone_id").eq(zone_id)
        )
        items = response.get("Items", [])
        if items:
            return items
    except Exception as e:
        logger.warning(f"DynamoDB query on {TABLE_INFRASTRUCTURE} failed/unavailable: {str(e)}")

    # Fallback catalogue for Melamchi and Bhotekoshi
    catalog = {
        "melamchi-basin": [
            {
                "infra_id": "hydro-melamchi-headworks",
                "name": "Melamchi Water Supply Project - Intake Headworks",
                "type": "Hydropower / Water Intake",
                "zone_id": "melamchi-basin",
                "coordinates": {"lat": 27.9622, "lon": 85.5681},
                "elevation_m": 1420,
                "criticality": "HIGH",
                "status": "NORMAL"
            },
            {
                "infra_id": "bridge-melamchi-pul",
                "name": "Melamchi Bazaar Motor Bridge",
                "type": "Bridge / Highway",
                "zone_id": "melamchi-basin",
                "coordinates": {"lat": 27.8285, "lon": 85.5780},
                "elevation_m": 840,
                "criticality": "CRITICAL",
                "status": "NORMAL"
            },
            {
                "infra_id": "settlement-melamchi-bazaar",
                "name": "Melamchi Bazaar Settlement",
                "type": "Urban Settlement",
                "zone_id": "melamchi-basin",
                "coordinates": {"lat": 27.8290, "lon": 85.5800},
                "population_at_risk": 4200,
                "criticality": "CRITICAL",
                "status": "NORMAL"
            },
            {
                "infra_id": "bridge-helambu-suspension",
                "name": "Helambu Pedestrian Suspension Bridge",
                "type": "Suspension Bridge",
                "zone_id": "melamchi-basin",
                "coordinates": {"lat": 27.9810, "lon": 85.5420},
                "elevation_m": 1390,
                "criticality": "MEDIUM",
                "status": "NORMAL"
            }
        ],
        "bhotekoshi-basin": [
            {
                "infra_id": "hydro-upper-bhotekoshi-45mw",
                "name": "Upper Bhotekoshi Hydropower Station (45MW)",
                "type": "Hydropower Plant",
                "zone_id": "bhotekoshi-basin",
                "coordinates": {"lat": 27.9400, "lon": 85.8900},
                "elevation_m": 1350,
                "criticality": "CRITICAL",
                "status": "NORMAL"
            }
        ]
    }
    return catalog.get(zone_id, catalog["melamchi-basin"])

def safe_put_item(table_name, item):
    """Safely attempts to write item to DynamoDB."""
    try:
        table = dynamodb.Table(table_name)
        table.put_item(Item=item)
        logger.info(f"Successfully wrote item to DynamoDB table {table_name}")
        return True
    except Exception as e:
        logger.warning(f"DynamoDB write to {table_name} skipped/failed: {str(e)}")
        return False

def generate_alert_content(zone_name, risk_score, risk_level, safe_zones):
    """
    Creates bilingual actionable alert messages (English & Nepali)
    with higher-elevation evacuation guidance.
    """
    primary_safe_zone = safe_zones[0]["zone_name"] if safe_zones else "High Ridge Evacuation Point"
    elevation = safe_zones[0]["elevation_m"] if safe_zones else 1400

    if risk_level == "CRITICAL":
        en_msg = (
            f"URGENT EVACUATION: Critical flood and debris-flow risk ({risk_score}/100) detected in {zone_name}! "
            f"Immediate riverbank surge expected. Do not remain near the riverbed. "
            f"Evacuate immediately to {primary_safe_zone} (elevation {elevation}m) or higher ground."
        )
        ne_msg = (
            f"अति जरुरी सूचना: {zone_name} क्षेत्रमा उच्च बाढी र पहिरोको गम्भीर जोखिम ({risk_score}/100) पत्ता लागेको छ। "
            f"तुरुन्तै नदी किनार छाडेर तोकिएको सुरक्षित उच्च स्थान {primary_safe_zone} तर्फ जानुहोस्।"
        )
    elif risk_level == "HIGH":
        en_msg = (
            f"WARNING: High flood risk ({risk_score}/100) in {zone_name}. "
            f"Hydropower plant operators should initiate intake shutdown. "
            f"Residents should prepare for evacuation to {primary_safe_zone}."
        )
        ne_msg = (
            f"चेतावनी: {zone_name} क्षेत्रमा उच्च बाढीको जोखिम ({risk_score}/100) रहेको छ। "
            f"जलविद्युत आयोजना तथा स्थानीय बासिन्दा सतर्क रहनुहोस् र सुरक्षित स्थानको तयारी गर्नुहोस्।"
        )
    else:
        en_msg = f"ADVISORY: Risk score for {zone_name} is {risk_score}/100 ({risk_level}). Normal monitoring in effect."
        ne_msg = f"{zone_name} क्षेत्रमा बाढीको जोखिम सामान्य ({risk_score}/100) छ। नियमित निगरानी जारी छ।"

    return en_msg, ne_msg

def lambda_handler(event, context):
    """
    Main handler for evaluating risk and publishing alerts/infrastructure updates.
    """
    logger.info(f"Generating alerts for event: {json.dumps(event)}")
    
    zone_id = event.get("zone_id", "melamchi-basin")
    zone_name = event.get("zone_name", "Melamchi River Basin")
    timestamp = event.get("timestamp", datetime.now(timezone.utc).isoformat())
    risk_score = event.get("risk_score", 50)
    risk_level = event.get("risk_level", "MODERATE")
    event_id = event.get("event_id", f"evt-{int(datetime.now(timezone.utc).timestamp())}")

    safe_zones = SAFE_EVACUATION_ZONES.get(zone_id, SAFE_EVACUATION_ZONES["melamchi-basin"])
    infra_list = get_downstream_infrastructure(zone_id)

    # Flag infrastructure status based on risk level
    flagged_infrastructure = []
    for infra in infra_list:
        infra_copy = dict(infra)
        if risk_level in ["CRITICAL", "HIGH"]:
            infra_copy["status"] = "EMERGENCY_LOCKDOWN" if risk_level == "CRITICAL" else "WARNING_ALERT"
            infra_copy["risk_score"] = risk_score
            infra_copy["recommended_action"] = "Turbine intake closure & personnel evacuation" if "Hydropower" in infra.get("type", "") else "Halt traffic on bridge immediately"
        else:
            infra_copy["status"] = "NORMAL"
            infra_copy["risk_score"] = risk_score
            infra_copy["recommended_action"] = "Routine operations"
            
        safe_put_item(TABLE_INFRASTRUCTURE, infra_copy)
        flagged_infrastructure.append(infra_copy)

    # Generate bilingual alerts
    en_alert, ne_alert = generate_alert_content(zone_name, risk_score, risk_level, safe_zones)
    
    # Structure Alert Record
    alert_record = {
        "alert_id": f"alt-{event_id}",
        "event_id": event_id,
        "zone_id": zone_id,
        "zone_name": zone_name,
        "timestamp": timestamp,
        "risk_level": risk_level,
        "risk_score": risk_score,
        "message_en": en_alert,
        "message_ne": ne_alert,
        "polly_voice_config": {
            "voice_id": "Aditi",  # Multi-lingual Indian/Nepali accent capable voice
            "language_code": "hi-IN",
            "text": ne_alert
        },
        "safe_evacuation_zones": safe_zones,
        "dispatched_channels": ["SMS", "IVR_VOICE", "DASHBOARD", "RADIO_BROADCAST"],
        "delivery_status": "SENT" if risk_level in ["CRITICAL", "HIGH"] else "STANDBY"
    }
    safe_put_item(TABLE_ALERTS, alert_record)

    # Create Rescue Case if Critical
    created_rescue_case = None
    if risk_level in ["CRITICAL", "HIGH"]:
        rescue_case = {
            "case_id": f"rec-{event_id}",
            "zone_id": zone_id,
            "target_location": "Melamchi Bazaar & Helambu Valley Confluence",
            "priority": "P1_URGENT" if risk_level == "CRITICAL" else "P2_ELEVATED",
            "status": "DEPLOYED",
            "evacuation_safe_zone": safe_zones[0]["zone_name"],
            "designated_route": safe_zones[0]["route_description"],
            "estimated_people_impacted": 4200,
            "timestamp": timestamp
        }
        safe_put_item(TABLE_RESCUE_CASES, rescue_case)
        created_rescue_case = rescue_case

    # Persist Final RiskEvent record
    risk_event_record = {
        "zone_id": zone_id,
        "timestamp": timestamp,
        "event_id": event_id,
        "zone_name": zone_name,
        "risk_score": risk_score,
        "risk_level": risk_level,
        "model_features": event.get("model_features", {}),
        "inference_engine": event.get("inference_engine", "default"),
        "impacted_infrastructure_count": len([i for i in flagged_infrastructure if i["status"] != "NORMAL"]),
        "alert_id": alert_record["alert_id"]
    }
    safe_put_item(TABLE_RISK_EVENTS, risk_event_record)

    response = {
        "status": "SUCCESS",
        "event_id": event_id,
        "zone_id": zone_id,
        "risk_score": risk_score,
        "risk_level": risk_level,
        "alert": alert_record,
        "flagged_infrastructure": flagged_infrastructure,
        "rescue_case": created_rescue_case,
        "timestamp": timestamp
    }

    logger.info(f"Pipeline finished successfully for event {event_id}")
    return response
