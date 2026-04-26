"""Minimal webhook receiver — prints every incoming request body to stdout.
No HMAC validation, no routing. Run with:
    conda activate weaving_webhook
    python test_receiver.py
"""

import json
from http.server import BaseHTTPRequestHandler, HTTPServer


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        event = self.headers.get("X-Gitea-Event", "unknown")
        print(f"\n--- {event} ---")
        try:
            print(json.dumps(json.loads(body), indent=2)[:2000])
        except Exception:
            print(body[:2000])
        self.send_response(200)
        self.end_headers()

    def log_message(self, fmt, *args):
        pass  # suppress default access log noise


if __name__ == "__main__":
    port = 3001
    print(f"Listening on port {port} — waiting for Gitea webhooks...")
    HTTPServer(("0.0.0.0", port), Handler).serve_forever()
