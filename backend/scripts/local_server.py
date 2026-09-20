"""
TerraSentinel-Nepal: Local Mock API Server
Runs the exact api_handler Lambda locally on http://127.0.0.1:8000 without requiring AWS deployment.
Uses Python standard library (no extra pip dependencies required).

Usage:
  python scripts/local_server.py [--port 8000]
"""
import sys
import os
import json
import argparse
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

# Ensure UTF-8 output on Windows consoles
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Add root folder to sys.path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from functions.api_handler.app import lambda_handler

class LocalApiHandler(BaseHTTPRequestHandler):
    def _send_response_from_lambda(self, lambda_resp):
        status_code = lambda_resp.get("statusCode", 200)
        headers = lambda_resp.get("headers", {})
        body = lambda_resp.get("body", "")

        self.send_response(status_code)
        for k, v in headers.items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body.encode("utf-8"))

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-Requested-With")
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        qs = parse_qs(parsed.query)
        # flatten query string dict
        flattened_qs = {k: v[0] if len(v) == 1 else v for k, v in qs.items()}

        event = {
            "rawPath": parsed.path,
            "path": parsed.path,
            "httpMethod": "GET",
            "requestContext": {
                "http": {
                    "method": "GET",
                    "path": parsed.path
                }
            },
            "queryStringParameters": flattened_qs,
            "body": None
        }

        response = lambda_handler(event, None)
        self._send_response_from_lambda(response)

    def do_POST(self):
        parsed = urlparse(self.path)
        content_length = int(self.headers.get("Content-Length", 0))
        post_body = self.rfile.read(content_length).decode("utf-8") if content_length > 0 else ""

        event = {
            "rawPath": parsed.path,
            "path": parsed.path,
            "httpMethod": "POST",
            "requestContext": {
                "http": {
                    "method": "POST",
                    "path": parsed.path
                }
            },
            "queryStringParameters": {},
            "body": post_body
        }

        response = lambda_handler(event, None)
        self._send_response_from_lambda(response)

def run(port=8000):
    server_address = ("127.0.0.1", port)
    httpd = HTTPServer(server_address, LocalApiHandler)
    print("=" * 70)
    print(f"🌍 TerraSentinel-Nepal Local API Server running at http://127.0.0.1:{port}")
    print("=" * 70)
    print("Available REST API Endpoints:")
    print(f"  • GET  http://127.0.0.1:{port}/risk")
    print(f"  • GET  http://127.0.0.1:{port}/risk/melamchi-basin")
    print(f"  • GET  http://127.0.0.1:{port}/infrastructure")
    print(f"  • GET  http://127.0.0.1:{port}/population")
    print(f"  • GET  http://127.0.0.1:{port}/alerts")
    print(f"  • GET  http://127.0.0.1:{port}/rescue")
    print(f"  • POST http://127.0.0.1:{port}/simulate-event  (Try body: {{\"scenario\":\"melamchi_2021\"}})")
    print("=" * 70)
    print("Ready to serve requests from Frontend (CORS enabled for localhost:3000)...")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n🛑 Shutting down server.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run local TerraSentinel API mock server")
    parser.add_argument("--port", type=int, default=8000, help="Port to listen on (default: 8000)")
    args = parser.parse_args()
    run(args.port)
