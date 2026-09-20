"""
TerraSentinel-Nepal: DynamoDB Seeder Script
Seeds authentic geographic, infrastructure, population, and alert datasets for:
- Melamchi River Basin (Sindhupalchok)
- Bhotekoshi River Basin (Sindhupalchok / Tibet border)
- Tamur River Basin (Taplejung)
- Marsyangdi River Basin (Lamjung / Manang)

Usage:
  python scripts/seed_nepal_data.py [--env aws|local]
"""
import sys
import json
import argparse
from datetime import datetime, timezone

# Ensure UTF-8 output on Windows consoles
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

try:
    import boto3
except ImportError:
    boto3 = None


INFRASTRUCTURE_DATA = [
    {
        "infra_id": "hydro-melamchi-headworks",
        "name": "Melamchi Water Supply Project - Intake Headworks",
        "type": "Hydropower / Water Intake",
        "zone_id": "melamchi-basin",
        "zone_name": "Melamchi River Basin",
        "status": "EMERGENCY_LOCKDOWN",
        "risk_score": 82,
        "criticality": "CRITICAL",
        "coordinates": {"lat": 27.9622, "lon": 85.5681},
        "elevation_m": 1420,
        "capacity_specs": "170 MLD Water Diversion to Kathmandu Valley",
        "estimated_replacement_cost_usd": "35,000,000",
        "recommended_action": "Close headworks hydraulic gates & evacuate operational staff to higher ridge."
    },
    {
        "infra_id": "bridge-melamchi-pul",
        "name": "Melamchi Motor Bridge",
        "type": "Bridge / Highway",
        "zone_id": "melamchi-basin",
        "zone_name": "Melamchi River Basin",
        "status": "EMERGENCY_LOCKDOWN",
        "risk_score": 82,
        "criticality": "CRITICAL",
        "coordinates": {"lat": 27.8285, "lon": 85.5780},
        "elevation_m": 840,
        "capacity_specs": "Single-span prestressed concrete bridge",
        "recommended_action": "Halt vehicular traffic and close pedestrian barriers immediately."
    },
    {
        "infra_id": "bridge-helambu-suspension",
        "name": "Helambu Pedestrian Suspension Bridge",
        "type": "Suspension Bridge",
        "zone_id": "melamchi-basin",
        "zone_name": "Melamchi River Basin",
        "status": "WARNING_ALERT",
        "risk_score": 75,
        "criticality": "HIGH",
        "coordinates": {"lat": 27.9810, "lon": 85.5420},
        "elevation_m": 1390,
        "capacity_specs": "120m Footbridge connecting Kiul to Nakote",
        "recommended_action": "Post local ward police to prevent crossing."
    },
    {
        "infra_id": "settlement-melamchi-bazaar",
        "name": "Melamchi Bazaar Commercial Hub",
        "type": "Urban Settlement",
        "zone_id": "melamchi-basin",
        "zone_name": "Melamchi River Basin",
        "status": "EMERGENCY_LOCKDOWN",
        "risk_score": 82,
        "criticality": "CRITICAL",
        "coordinates": {"lat": 27.8290, "lon": 85.5800},
        "elevation_m": 845,
        "population_at_risk": 4200,
        "recommended_action": "Immediate evacuation via Upper Ward route."
    },
    {
        "infra_id": "hydro-upper-bhotekoshi-45mw",
        "name": "Upper Bhotekoshi Hydropower Station (45MW)",
        "type": "Hydropower Plant",
        "zone_id": "bhotekoshi-basin",
        "zone_name": "Bhotekoshi River Basin",
        "status": "WARNING_ALERT",
        "risk_score": 58,
        "criticality": "HIGH",
        "coordinates": {"lat": 27.9400, "lon": 85.8900},
        "elevation_m": 1350,
        "capacity_specs": "45 Megawatts Run-of-River (Bhotekoshi Power Company)",
        "recommended_action": "Place powerhouse operators on standby for intake closure."
    },
    {
        "infra_id": "hydro-middle-bhotekoshi-102mw",
        "name": "Middle Bhotekoshi Hydro (102MW)",
        "type": "Hydropower Plant",
        "zone_id": "bhotekoshi-basin",
        "zone_name": "Bhotekoshi River Basin",
        "status": "NORMAL",
        "risk_score": 42,
        "criticality": "HIGH",
        "coordinates": {"lat": 27.8800, "lon": 85.8600},
        "elevation_m": 1150,
        "capacity_specs": "102 Megawatts Under Chilime/NEA",
        "recommended_action": "Standard monitoring."
    },
    {
        "infra_id": "bridge-arniko-miteri",
        "name": "Arniko Highway Miteri Bridge",
        "type": "International Transit Bridge",
        "zone_id": "bhotekoshi-basin",
        "zone_name": "Bhotekoshi River Basin",
        "status": "NORMAL",
        "risk_score": 38,
        "criticality": "HIGH",
        "coordinates": {"lat": 27.9715, "lon": 85.9625},
        "elevation_m": 1580,
        "capacity_specs": "Nepal-China Border Transit Link",
        "recommended_action": "Routine border transit checks."
    }
]

RISK_EVENTS_DATA = [
    {
        "zone_id": "melamchi-basin",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event_id": "evt-melamchi-live-001",
        "zone_name": "Melamchi River Basin",
        "risk_score": 82,
        "risk_level": "CRITICAL",
        "model_features": {
            "rainfall_24h": 142.0,
            "slope": 37.2,
            "lake_change": 0.21,
            "displacement": 0.14
        },
        "inference_engine": "sagemaker:terrasentinel-risk-model",
        "impacted_infrastructure_count": 3,
        "alert_id": "alt-melamchi-001"
    },
    {
        "zone_id": "bhotekoshi-basin",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event_id": "evt-bhotekoshi-live-002",
        "zone_name": "Bhotekoshi River Basin",
        "risk_score": 58,
        "risk_level": "MODERATE",
        "model_features": {
            "rainfall_24h": 68.5,
            "slope": 39.5,
            "lake_change": 0.12,
            "displacement": 0.06
        },
        "inference_engine": "sagemaker:terrasentinel-risk-model",
        "impacted_infrastructure_count": 1,
        "alert_id": "alt-bhotekoshi-002"
    }
]

ALERTS_DATA = [
    {
        "alert_id": "alt-melamchi-001",
        "event_id": "evt-melamchi-live-001",
        "zone_id": "melamchi-basin",
        "zone_name": "Melamchi River Basin",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "risk_level": "CRITICAL",
        "risk_score": 82,
        "message_en": "URGENT EVACUATION: Critical flood and debris surge (82/100) detected in Melamchi Basin! Immediate riverbank evacuation ordered. Move to Melamchi Upper Community Hilltop Ridge (1280m) immediately.",
        "message_ne": "अति जरुरी सूचना: मेलम्ची क्षेत्रमा उच्च बाढी र पहिरोको गम्भीर जोखिम (82/100) पत्ता लागेको छ। तुरुन्तै नदी किनार छाडेर सुरक्षित उच्च स्थान मेलम्ची डाँडातर्फ जानुहोस्।",
        "polly_voice_config": {
            "voice_id": "Aditi",
            "language_code": "hi-IN",
            "text": "अति जरुरी सूचना: मेलम्ची क्षेत्रमा उच्च बाढी र पहिरोको गम्भीर जोखिम पत्ता लागेको छ। तुरुन्तै सुरक्षित उच्च स्थानमा जानुहोस्।"
        },
        "delivery_status": "SENT",
        "channels": ["SMS", "POLICE_RADIO", "POLLY_VOICE", "SIRENS"]
    }
]

RESCUE_CASES_DATA = [
    {
        "case_id": "rec-melamchi-001",
        "zone_id": "melamchi-basin",
        "priority": "P1_URGENT",
        "status": "DEPLOYED",
        "target_location": "Melamchi Bazaar Confluence",
        "coordinates": {"lat": 27.8290, "lon": 85.5800},
        "evacuation_safe_zone": "Melamchi Upper Community Hilltop Ridge (1280m)",
        "designated_route": "Ascend 40 vertical meters above the Melamchi riverbed.",
        "estimated_people_impacted": 4200,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
]

def seed_to_dynamodb():
    """Populates live AWS DynamoDB tables."""
    print("🚀 Connecting to AWS DynamoDB...")
    dynamodb = boto3.resource("dynamodb")
    
    tables_map = {
        "TerraSentinel-Infrastructure": INFRASTRUCTURE_DATA,
        "TerraSentinel-RiskEvents": RISK_EVENTS_DATA,
        "TerraSentinel-Alerts": ALERTS_DATA,
        "TerraSentinel-RescueCases": RESCUE_CASES_DATA
    }

    for table_name, data in tables_map.items():
        print(f"📦 Seeding {len(data)} records into table: {table_name}...")
        try:
            table = dynamodb.Table(table_name)
            for item in data:
                table.put_item(Item=item)
            print(f"✅ Successfully seeded {table_name}")
        except Exception as e:
            print(f"❌ Error seeding {table_name}: {str(e)}")

def export_local_snapshot():
    """Exports dataset to local JSON snapshot for offline/mock runner."""
    snapshot = {
        "infrastructure": INFRASTRUCTURE_DATA,
        "risk_events": RISK_EVENTS_DATA,
        "alerts": ALERTS_DATA,
        "rescue_cases": RESCUE_CASES_DATA
    }
    with open("scripts/nepal_seed_data.json", "w", encoding="utf-8") as f:
        json.dump(snapshot, f, indent=2, ensure_ascii=False)
    print("✅ Exported scripts/nepal_seed_data.json for local offline use.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed TerraSentinel Nepal geospatial data")
    parser.add_argument("--env", choices=["aws", "local"], default="local", help="Target environment")
    args = parser.parse_args()

    export_local_snapshot()

    if args.env == "aws":
        seed_to_dynamodb()
    else:
        print("💡 Local snapshot generated. Use --env aws once SAM deployment is finished.")
