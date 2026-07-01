#!/usr/bin/env python3
"""
Small HTTP forwarder for deployments where the xApp host cannot reach the robot
UE IP directly, but a gNB/core host can.

Run on the reachable host and configure the xApp robot.baseUrl to this helper.
The helper forwards JSON POST bodies without parsing E2/RMR or modifying gNB code.
"""

import argparse
import json
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class Forwarder(BaseHTTPRequestHandler):
    target_base_url = ""
    timeout = 0.5

    def do_GET(self) -> None:
        if self.path == "/health":
            self._send_json(200, {"alive": True, "target": self.target_base_url})
            return
        self._send_json(404, {"error": "not found"})

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length) if length else b"{}"
        target_url = self.target_base_url.rstrip("/") + self.path
        request = urllib.request.Request(
            target_url,
            data=body,
            headers={"Content-Type": self.headers.get("Content-Type", "application/json")},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                response_body = response.read()
                self.send_response(response.status)
                self.send_header("Content-Type", response.headers.get("Content-Type", "application/json"))
                self.send_header("Content-Length", str(len(response_body)))
                self.end_headers()
                self.wfile.write(response_body)
        except urllib.error.HTTPError as exc:
            self._send_bytes(exc.code, exc.read(), exc.headers.get("Content-Type", "application/json"))
        except urllib.error.URLError as exc:
            self._send_json(502, {"error": str(exc), "target": target_url})

    def log_message(self, fmt: str, *args) -> None:
        print("%s - %s" % (self.address_string(), fmt % args))

    def _send_json(self, status: int, payload) -> None:
        self._send_bytes(status, json.dumps(payload).encode("utf-8"), "application/json")

    def _send_bytes(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Forward steering xApp REST commands to a robot UE HTTP endpoint")
    parser.add_argument("--listen-host", default="0.0.0.0")
    parser.add_argument("--listen-port", type=int, default=8090)
    parser.add_argument("--target-base-url", default="http://10.45.1.3:8000", help="Robot UE base URL, for example http://10.45.1.3:8000")
    parser.add_argument("--timeout", type=float, default=0.5)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    Forwarder.target_base_url = args.target_base_url
    Forwarder.timeout = args.timeout
    server = ThreadingHTTPServer((args.listen_host, args.listen_port), Forwarder)
    print(f"forwarding http://{args.listen_host}:{args.listen_port} -> {args.target_base_url}")
    server.serve_forever()


if __name__ == "__main__":
    main()
