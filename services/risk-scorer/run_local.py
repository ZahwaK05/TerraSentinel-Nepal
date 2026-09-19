"""
Local Demo Runner — Melamchi Scenario
======================================
Runs the end-to-end pipeline locally using sample data.
No AWS services are required in demo mode.

Usage:
    python services/risk-scorer/run_local.py --scenario melamchi --mode demo
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("run_local")

ROOT = Path(__file__).resolve().parents[2]
SAMPLE_DATA = ROOT / "data" / "sample"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="TerraSentinel-Nepal local demo runner")
    parser.add_argument("--scenario", default="melamchi", help="Scenario name")
    parser.add_argument(
        "--mode",
        default="demo",
        choices=["demo", "test"],
        help="Run mode: demo (full display) or test (validate outputs only)",
    )
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    return parser.parse_args()


def step(name: str) -> None:
    logger.info("=" * 60)
    logger.info("STEP: %s", name)
    logger.info("=" * 60)


def validate_sample_data(scenario: str) -> None:
    scenario_dir = SAMPLE_DATA / scenario
    if not scenario_dir.exists():
        logger.error("Sample data directory not found: %s", scenario_dir)
        sys.exit(1)
    logger.info("Sample data directory: %s", scenario_dir)
    files = list(scenario_dir.rglob("*"))
    logger.info("Found %d sample files", len(files))


def mock_pipeline(scenario: str) -> dict:
    """Run a mock pipeline and return simulated results for demo."""
    import random
    random.seed(42)

    ZONES = [
        {"id": "melamchi-upper", "label": "Upper Melamchi Valley"},
        {"id": "melamchi-gorge", "label": "Melamchi Gorge"},
        {"id": "indrawati-confluence", "label": "Indrawati Confluence"},
        {"id": "melamchi-bazar", "label": "Melamchi Bazar"},
        {"id": "sundarijal", "label": "Sundarijal"},
    ]

    results = []
    for zone in ZONES:
        score = round(random.uniform(0.3, 0.97), 3)
        level = "HIGH" if score >= 0.7 else ("MEDIUM" if score >= 0.4 else "LOW")
        results.append({
            "cell_id": zone["id"],
            "label": zone["label"],
            "risk_score": score,
            "risk_level": level,
            "data_mode": "HISTORICAL",
            "model_version": "v1",
            "timestamp_utc": "2021-06-15T03:00:00Z",
            "feature_contributions": {
                "ndwi_change": round(score * 0.38, 3),
                "rainfall_72h_mm": round(score * 0.28, 3),
                "dem_slope_deg": round(score * 0.15, 3),
                "flow_accumulation_km2": round(score * 0.12, 3),
                "distance_to_river_m": round(score * 0.05, 3),
                "infrastructure_density_per_km2": round(score * 0.02, 3),
            },
        })
    return {"scenario": scenario, "zones": results}


def mock_alerts(results: dict) -> list[dict]:
    from services.alert_dispatcher.dispatcher import AlertDispatcher  # type: ignore[import]
    dispatcher = AlertDispatcher(mode="mock")
    alerts = []
    for zone in results["zones"]:
        if zone["risk_level"] in ("HIGH", "MEDIUM"):
            payload = dispatcher.generate_alert(
                zone["cell_id"],
                zone["risk_level"],
                data_mode=zone["data_mode"],
                timestamp_utc=zone["timestamp_utc"],
            )
            alerts.append(dispatcher.dispatch(payload))
    return alerts


def main() -> None:
    args = parse_args()
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    start = time.monotonic()
    logger.info("TerraSentinel-Nepal — Local Demo Runner")
    logger.info("Scenario: %s | Mode: %s", args.scenario, args.mode)

    step("1. Validate sample data")
    validate_sample_data(args.scenario)

    step("2. Geospatial processing (mock)")
    logger.info("Simulating SAR water-change and DEM flow-corridor computation...")
    time.sleep(0.5)
    logger.info("Flood extent polygon: 38.4 km² [HISTORICAL]")

    step("3. Risk scoring (mock)")
    results = mock_pipeline(args.scenario)
    for z in results["zones"]:
        logger.info(
            "  %-30s score=%.3f level=%-6s mode=%s",
            z["label"],
            z["risk_score"],
            z["risk_level"],
            z["data_mode"],
        )

    step("4. Impact identification (mock)")
    logger.info("Exposed assets within flood extent [HISTORICAL]:")
    logger.info("  - Melamchi-Sindhupalachowk road (3.2 km)")
    logger.info("  - Melamchi Bazar bridge")
    logger.info("  - 2 health posts within HIGH-risk zone")

    step("5. Alert generation (mock — no real notifications)")
    try:
        alerts = mock_alerts(results)
        for a in alerts:
            logger.info("  [MOCK] %s", json.dumps(a))
    except ImportError:
        logger.warning("Alert dispatcher import failed — skipping in minimal mode")
        alerts = [{"status": "mock_skipped", "note": "dispatcher not importable locally"}]

    step("6. Pipeline complete")
    elapsed = time.monotonic() - start
    logger.info("Total elapsed time: %.1f s", elapsed)

    SUCCESS_THRESHOLD_S = 300
    if elapsed > SUCCESS_THRESHOLD_S:
        logger.error(
            "Pipeline exceeded %d s threshold (%.1f s). Review performance.",
            SUCCESS_THRESHOLD_S,
            elapsed,
        )
        sys.exit(1)

    logger.info("SUCCESS: Pipeline completed within time threshold.")

    output = {
        "scenario": args.scenario,
        "elapsed_s": round(elapsed, 2),
        "risk_results": results,
        "mock_alerts": alerts,
    }
    out_path = Path("/tmp/terrasentinel_demo_output.json")
    out_path.write_text(json.dumps(output, indent=2, ensure_ascii=False))
    logger.info("Output written to %s", out_path)


if __name__ == "__main__":
    main()
