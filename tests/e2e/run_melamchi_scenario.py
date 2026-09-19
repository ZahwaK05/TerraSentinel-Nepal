"""
End-to-End Test — Melamchi Scenario
=====================================
Validates the complete demo pipeline without manual intervention.
Run this in CI and before any demonstration to confirm the system works.

Exit code 0 = all assertions passed.
Exit code 1 = one or more assertions failed.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SAMPLE_DATA = ROOT / "data" / "sample" / "melamchi"


def check(condition: bool, message: str) -> bool:
    if condition:
        print(f"  PASS: {message}")
    else:
        print(f"  FAIL: {message}")
    return condition


def main() -> int:
    failures = 0
    print("=" * 60)
    print("TerraSentinel-Nepal — Melamchi E2E Test")
    print("=" * 60)

    # ── 1. Sample data exists ─────────────────────────────────────
    print("\n[1] Sample data validation")
    failures += not check(SAMPLE_DATA.exists(), f"Sample data directory exists: {SAMPLE_DATA}")
    if SAMPLE_DATA.exists():
        files = list(SAMPLE_DATA.rglob("*.*"))
        failures += not check(len(files) >= 1, f"At least 1 sample file present (found {len(files)})")

    # ── 2. Pipeline runs within time threshold ────────────────────
    print("\n[2] Pipeline execution")
    start = time.monotonic()
    result = subprocess.run(
        [sys.executable, "services/risk-scorer/run_local.py", "--scenario", "melamchi", "--mode", "test"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    elapsed = time.monotonic() - start

    failures += not check(result.returncode == 0, f"Pipeline exits with code 0 (got {result.returncode})")
    failures += not check(elapsed < 300, f"Pipeline completes in < 300 s (took {elapsed:.1f} s)")

    if result.returncode != 0:
        print("  STDOUT:", result.stdout[-2000:])
        print("  STDERR:", result.stderr[-2000:])

    # ── 3. Output file exists and is valid JSON ───────────────────
    print("\n[3] Output validation")
    output_path = Path("/tmp/terrasentinel_demo_output.json")
    failures += not check(output_path.exists(), f"Output file created at {output_path}")

    if output_path.exists():
        try:
            output = json.loads(output_path.read_text(encoding="utf-8"))
            failures += not check(
                output.get("scenario") == "melamchi",
                "Output scenario matches 'melamchi'"
            )
            zones = output.get("risk_results", {}).get("zones", [])
            failures += not check(len(zones) >= 3, f"At least 3 risk zones scored (found {len(zones)})")

            # Check all zones have data_mode label
            all_labelled = all(z.get("data_mode") in ("HISTORICAL", "SIMULATED", "LIVE") for z in zones)
            failures += not check(all_labelled, "All zones have a valid data_mode label")

            # Check at least one HIGH zone exists for Melamchi scenario
            high_zones = [z for z in zones if z.get("risk_level") == "HIGH"]
            failures += not check(len(high_zones) >= 1, f"At least 1 HIGH-risk zone identified (found {len(high_zones)})")

            # Check mock alerts were generated
            alerts = output.get("mock_alerts", [])
            failures += not check(len(alerts) >= 1, f"At least 1 mock alert generated (found {len(alerts)})")
            for alert in alerts:
                failures += not check(
                    alert.get("alert_mode") != "live",
                    f"Alert mode is not 'live' for zone {alert.get('zone_id', '?')}"
                )

        except json.JSONDecodeError as e:
            print(f"  FAIL: Output is not valid JSON: {e}")
            failures += 1

    # ── Summary ───────────────────────────────────────────────────
    print("\n" + "=" * 60)
    if failures == 0:
        print(f"ALL CHECKS PASSED — {elapsed:.1f} s")
        return 0
    else:
        print(f"{failures} CHECK(S) FAILED")
        return 1


if __name__ == "__main__":
    sys.exit(main())
