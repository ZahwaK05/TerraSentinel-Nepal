"""
TerraSentinel-Nepal: Pipeline Simulation Trigger
Executes the full cascading hazard pipeline:
  process_data -> calculate_features -> run_risk_model -> generate_alert

Can run locally in Python or trigger AWS Step Functions.

Usage:
  python scripts/trigger_simulation.py [--mode local|aws] [--state-machine-arn ARN]
"""
import os
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

# Ensure project root is in sys.path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from functions.process_data.app import lambda_handler as process_data_handler
from functions.calculate_features.app import lambda_handler as calculate_features_handler
from functions.run_risk_model.app import lambda_handler as run_risk_model_handler
from functions.generate_alert.app import lambda_handler as generate_alert_handler

SAMPLE_MELAMCHI_INPUT = {
    "zone_id": "melamchi-basin",
    "timestamp": datetime.now(timezone.utc).isoformat(),
    "source": "Sentinel-1/2 + GPM IMERG Realtime Feed",
    "raw_data": {
        "rainfall_24h": 142.0,
        "slope": 37.2,
        "lake_change": 0.21,
        "displacement": 0.14
    }
}

def run_local_pipeline():
    """Runs all 4 Lambda handlers sequentially in memory."""
    print("\n" + "=" * 70)
    print("🌊 STARTING TERRASENTINEL LOCAL PIPELINE SIMULATION")
    print("=" * 70)
    print(f"📥 Input Telemetry: {json.dumps(SAMPLE_MELAMCHI_INPUT, indent=2)}")

    # Step 1: Preprocess
    print("\n[1/4] Running: process-data...")
    res_1 = process_data_handler(SAMPLE_MELAMCHI_INPUT, None)
    print(f"  ✓ Normalized Zone: {res_1['zone_name']} ({res_1['zone_id']})")
    print(f"  ✓ Processed S3 URI: {res_1.get('processed_s3_uri')}")

    # Step 2: Feature Extraction
    print("\n[2/4] Running: calculate-features...")
    res_2 = calculate_features_handler(res_1, None)
    print(f"  ✓ Extracted Model Features: {json.dumps(res_2['model_features'])}")
    print(f"  ✓ Estimated Debris Velocity: {res_2['auxiliary_features']['debris_flow_velocity_est_mps']} m/s")

    # Step 3: ML Inference
    print("\n[3/4] Running: run-risk-model...")
    res_3 = run_risk_model_handler(res_2, None)
    print(f"  ✓ Risk Score: {res_3['risk_score']} / 100")
    print(f"  ✓ Risk Classification: {res_3['risk_level']}")
    print(f"  ✓ Inference Engine: {res_3['inference_engine']}")

    # Step 4: Alert & Impact Analysis
    print("\n[4/4] Running: generate-alert...")
    res_4 = generate_alert_handler(res_3, None)
    alert = res_4.get("alert", {})
    print(f"  ✓ Generated Alert ID: {alert.get('alert_id')}")
    print(f"  ✓ English Broadcast: \"{alert.get('message_en')}\"")
    print(f"  ✓ Nepali Broadcast: \"{alert.get('message_ne')}\"")
    print(f"  ✓ Flagged Infrastructure Count: {len(res_4.get('flagged_infrastructure', []))}")
    for infra in res_4.get("flagged_infrastructure", []):
        print(f"     - [{infra['status']}] {infra['name']} -> {infra.get('recommended_action')}")
    
    rescue = res_4.get("rescue_case")
    if rescue:
        print(f"  ✓ Spawned Rescue Case: {rescue['case_id']} ({rescue['priority']}) -> Evacuate to {rescue['evacuation_safe_zone']}")

    print("\n" + "=" * 70)
    print("✅ SIMULATION COMPLETE: ALL PIPELINE STAGES PASSED SUCCESSFULLY!")
    print("=" * 70)

def run_aws_step_function(state_machine_arn):
    """Triggers live AWS Step Functions execution."""
    import boto3
    sfn_client = boto3.client("stepfunctions")
    name = f"sim-{int(datetime.now(timezone.utc).timestamp())}"
    print(f"🚀 Triggering Step Functions State Machine: {state_machine_arn} (Execution: {name})")
    response = sfn_client.start_execution(
        stateMachineArn=state_machine_arn,
        name=name,
        input=json.dumps(SAMPLE_MELAMCHI_INPUT)
    )
    print(f"Execution started! ARN: {response['executionArn']}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Trigger TerraSentinel simulation")
    parser.add_argument("--mode", choices=["local", "aws"], default="local")
    parser.add_argument("--state-machine-arn", default=os.environ.get("STEP_FUNCTIONS_ARN"))
    args = parser.parse_args()

    if args.mode == "aws":
        if not args.state_machine_arn:
            print("❌ Error: --state-machine-arn or STEP_FUNCTIONS_ARN environment variable required for aws mode.")
            sys.exit(1)
        run_aws_step_function(args.state_machine_arn)
    else:
        run_local_pipeline()
