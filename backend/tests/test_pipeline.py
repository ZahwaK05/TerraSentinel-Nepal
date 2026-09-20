"""
TerraSentinel-Nepal: Comprehensive Test Suite
Tests all Lambda handlers, feature transformations, SageMaker inference mapping,
bilingual alert generation, and API Gateway routing.
"""
import os
import sys
import json
import unittest

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from functions.process_data.app import lambda_handler as process_data_handler
from functions.calculate_features.app import lambda_handler as calculate_features_handler
from functions.run_risk_model.app import lambda_handler as run_risk_model_handler
from functions.generate_alert.app import lambda_handler as generate_alert_handler
from functions.api_handler.app import lambda_handler as api_handler

class TestTerraSentinelBackend(unittest.TestCase):

    def setUp(self):
        self.sample_payload = {
            "zone_id": "melamchi-basin",
            "timestamp": "2026-09-17T10:00:00Z",
            "source": "test-harness",
            "raw_data": {
                "rainfall_24h": 142.0,
                "slope": 37.2,
                "lake_change": 0.21,
                "displacement": 0.14
            }
        }

    def test_01_process_data(self):
        """Tests data normalization and basin metadata lookup."""
        result = process_data_handler(self.sample_payload, None)
        self.assertEqual(result["zone_id"], "melamchi-basin")
        self.assertEqual(result["district"], "Sindhupalchok")
        self.assertIn("dem_slope", result["normalized_inputs"])
        self.assertEqual(result["normalized_inputs"]["dem_slope"], 37.2)

    def test_02_calculate_features(self):
        """Tests extraction of the 4 exact features expected by the ML model."""
        processed = process_data_handler(self.sample_payload, None)
        features_result = calculate_features_handler(processed, None)
        
        features = features_result["model_features"]
        self.assertIn("rainfall_24h", features)
        self.assertIn("slope", features)
        self.assertIn("lake_change", features)
        self.assertIn("displacement", features)

        self.assertEqual(features["rainfall_24h"], 142.0)
        self.assertEqual(features["slope"], 37.2)
        self.assertEqual(features["lake_change"], 0.21)
        self.assertEqual(features["displacement"], 0.14)

    def test_03_run_risk_model_exact_specification(self):
        """
        Validates the exact prompt specification:
        Input: { rainfall_24h: 142, slope: 37.2, lake_change: 0.21, displacement: 0.14 }
        Output: { risk_score: 82, risk_level: 'CRITICAL' }
        """
        features_payload = {
            "zone_id": "melamchi-basin",
            "model_features": {
                "rainfall_24h": 142,
                "slope": 37.2,
                "lake_change": 0.21,
                "displacement": 0.14
            }
        }
        model_result = run_risk_model_handler(features_payload, None)
        self.assertEqual(model_result["risk_score"], 82)
        self.assertEqual(model_result["risk_level"], "CRITICAL")

    def test_04_run_risk_model_low_risk(self):
        """Tests baseline low risk conditions."""
        features_payload = {
            "zone_id": "tamur-basin",
            "model_features": {
                "rainfall_24h": 20.0,
                "slope": 25.0,
                "lake_change": 0.01,
                "displacement": 0.01
            }
        }
        model_result = run_risk_model_handler(features_payload, None)
        self.assertTrue(model_result["risk_score"] < 40)
        self.assertEqual(model_result["risk_level"], "LOW")

    def test_05_generate_alert_bilingual_and_infrastructure(self):
        """Tests bilingual alerts generation and emergency infrastructure lockdown."""
        model_payload = {
            "zone_id": "melamchi-basin",
            "zone_name": "Melamchi River Basin",
            "timestamp": "2026-09-17T10:00:00Z",
            "risk_score": 82,
            "risk_level": "CRITICAL"
        }
        alert_result = generate_alert_handler(model_payload, None)
        self.assertEqual(alert_result["status"], "SUCCESS")
        
        # Verify alert content
        alert = alert_result["alert"]
        self.assertIn("URGENT EVACUATION", alert["message_en"])
        self.assertIn("अति जरुरी सूचना", alert["message_ne"])
        self.assertEqual(alert["polly_voice_config"]["voice_id"], "Aditi")

        # Verify infrastructure lockdown
        infras = alert_result["flagged_infrastructure"]
        self.assertTrue(len(infras) > 0)
        headworks = next((i for i in infras if "headworks" in i["infra_id"]), None)
        self.assertIsNotNone(headworks)
        self.assertEqual(headworks["status"], "EMERGENCY_LOCKDOWN")

        # Verify rescue case spawned
        rescue = alert_result["rescue_case"]
        self.assertIsNotNone(rescue)
        self.assertEqual(rescue["priority"], "P1_URGENT")

    def test_06_api_gateway_routes(self):
        """Tests all REST API endpoints served by api_handler."""
        # 1. GET /risk
        event = {"rawPath": "/risk", "httpMethod": "GET"}
        res = api_handler(event, None)
        self.assertEqual(res["statusCode"], 200)
        body = json.loads(res["body"])
        self.assertIn("basins", body)
        self.assertEqual(res["headers"]["Access-Control-Allow-Origin"], "*")

        # 2. GET /risk/melamchi-basin
        event = {"rawPath": "/risk/melamchi-basin", "httpMethod": "GET"}
        res = api_handler(event, None)
        self.assertEqual(res["statusCode"], 200)
        body = json.loads(res["body"])
        self.assertIn("time_series_trend", body)

        # 3. GET /infrastructure
        event = {"rawPath": "/infrastructure", "httpMethod": "GET"}
        res = api_handler(event, None)
        self.assertEqual(res["statusCode"], 200)
        body = json.loads(res["body"])
        self.assertIn("infrastructure", body)

        # 4. GET /population
        event = {"rawPath": "/population", "httpMethod": "GET"}
        res = api_handler(event, None)
        self.assertEqual(res["statusCode"], 200)
        body = json.loads(res["body"])
        self.assertIn("settlements", body)

        # 5. GET /alerts
        event = {"rawPath": "/alerts", "httpMethod": "GET"}
        res = api_handler(event, None)
        self.assertEqual(res["statusCode"], 200)

        # 6. GET /rescue
        event = {"rawPath": "/rescue", "httpMethod": "GET"}
        res = api_handler(event, None)
        self.assertEqual(res["statusCode"], 200)

        # 7. POST /simulate-event (Melamchi 2021 timeline slider)
        event = {
            "rawPath": "/simulate-event",
            "httpMethod": "POST",
            "body": json.dumps({"scenario": "melamchi_2021"})
        }
        res = api_handler(event, None)
        self.assertEqual(res["statusCode"], 200)
        body = json.loads(res["body"])
        self.assertEqual(body["scenario"], "melamchi_2021")
        self.assertEqual(body["total_steps"], 5)
        self.assertEqual(body["timeline"][3]["risk_score"], 82)

if __name__ == "__main__":
    unittest.main()
