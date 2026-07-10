#!/usr/bin/env python3
"""
Steering-wheel command xApp.

The v1 command path is REST/IP plus robot ROS bridge messaging:
wheel-client -> this xApp -> robot UE rosbridge/ROS command path. RMR is still
initialized by RMRXapp for normal xApp framework behavior and health handling,
but this file does not advertise or consume fake E2 control/indication messages.
"""

import json
import os
import http.server
import time
from typing import Any, Dict, Optional
from urllib.parse import urlparse

import requests
from google.protobuf.json_format import MessageToDict
from ricxappframe.rmr import rmr
from ricxappframe.util.constants import Constants
from ricxappframe.xapp_frame import RMRXapp
from ricxappframe import xapp_rest as ricrest

from steering_service import SteeringCommandService


APP_NAME = "steering-xapp"


class SteeringRestHandler(ricrest.RestHandler):
    xapp: Optional["SteeringXapp"] = None

    def do_GET(self):
        if self.path.find("/ric/v1/video/depth/stream") >= 0 and self.xapp is not None:
            self._proxy_depth_stream(self.xapp)
            return
        if self.path.find("/ric/v1/video/depth/snapshot") >= 0 and self.xapp is not None:
            self._proxy_depth_snapshot(self.xapp)
            return
        if self.path.find("/ric/v1/video/stream") >= 0 and self.xapp is not None:
            self._proxy_video_stream(self.xapp)
            return
        if self.path.find("/ric/v1/video/snapshot") >= 0 and self.xapp is not None:
            self._proxy_video_snapshot(self.xapp)
            return
        super().do_GET()

    def _proxy_depth_snapshot(self, app: "SteeringXapp") -> None:
        query = urlparse(self.path).query
        status, payload, content_type = app.command_service.depth_snapshot(query=query)
        self.send_response(status)
        self.send_header("Server-name", "XAPP REST SERVER 0.9")
        self.send_header("Content-type", content_type)
        self.send_header("Content-length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _proxy_depth_stream(self, app: "SteeringXapp") -> None:
        query = urlparse(self.path).query
        interval_seconds = 1.0 / 8.0
        try:
            self.send_response(200)
            self.send_header("Server-name", "XAPP REST SERVER 0.9")
            self.send_header("Content-type", "multipart/x-mixed-replace; boundary=frame")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            app.logger.info(f"xApp processed depth stream started query={query}")
            while True:
                started = time.monotonic()
                status, payload, content_type = app.command_service.depth_snapshot(query=query)
                if status >= 400:
                    app.logger.error(f"xApp processed depth frame failed status={status} payload={payload[:200]!r}")
                    time.sleep(1.0)
                    continue
                self.wfile.write(b"--frame\r\n")
                self.wfile.write(f"Content-Type: {content_type}\r\n".encode("ascii"))
                self.wfile.write(f"Content-Length: {len(payload)}\r\n\r\n".encode("ascii"))
                self.wfile.write(payload)
                self.wfile.write(b"\r\n")
                self.wfile.flush()
                time.sleep(max(interval_seconds - (time.monotonic() - started), 0.001))
        except (BrokenPipeError, ConnectionResetError):
            app.logger.info("xApp processed depth stream client disconnected")
        except Exception as exc:
            app.logger.error(f"xApp processed depth stream failed: {exc}")

    def _proxy_video_snapshot(self, app: "SteeringXapp") -> None:
        query = urlparse(self.path).query
        status, payload, content_type = app.command_service.video_snapshot(query=query)
        self.send_response(status)
        self.send_header("Server-name", "XAPP REST SERVER 0.9")
        self.send_header("Content-type", content_type)
        self.send_header("Content-length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _proxy_video_stream(self, app: "SteeringXapp") -> None:
        query = urlparse(self.path).query
        url = app.command_service.video_stream_url(query=query)
        try:
            with requests.get(url, stream=True, timeout=(app.command_service.robot.timeout_seconds, None)) as upstream:
                self.send_response(upstream.status_code)
                self.send_header("Server-name", "XAPP REST SERVER 0.9")
                self.send_header("Content-type", upstream.headers.get("Content-Type", "multipart/x-mixed-replace; boundary=frame"))
                self.send_header("Cache-Control", upstream.headers.get("Cache-Control", "no-cache"))
                self.end_headers()
                if upstream.status_code >= 400:
                    self.wfile.write(upstream.content)
                    return
                app.logger.info(f"video stream proxy started url={url}")
                for chunk in upstream.iter_content(chunk_size=65536):
                    if not chunk:
                        continue
                    self.wfile.write(chunk)
                    self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            app.logger.info("video stream client disconnected")
        except Exception as exc:
            app.logger.error(f"video stream proxy failed: {exc}")
            try:
                payload = json.dumps({"error": "video stream proxy failed", "detail": str(exc), "url": url}).encode("utf-8")
                self.send_response(502)
                self.send_header("Content-type", "application/json")
                self.send_header("Content-length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
            except Exception:
                pass


class SteeringHTTPServer(ricrest.ThreadedHTTPServer):
    handler = SteeringRestHandler
    server_class = http.server.ThreadingHTTPServer


def load_config(path: Optional[str]) -> Dict[str, Any]:
    if not path:
        return {}
    with open(path, "r", encoding="utf-8") as config_file:
        return json.load(config_file)


def load_config_text(path: Optional[str], config: Dict[str, Any]) -> str:
    if path and os.path.isfile(path):
        with open(path, "r", encoding="utf-8") as config_file:
            return config_file.read()
    return json.dumps(config, sort_keys=True)


def json_response(status: int = 200, payload: Optional[Any] = None) -> Dict[str, Any]:
    response = ricrest.initResponse(status=status, response="OK" if status < 400 else "ERROR")
    response["ctype"] = "application/json"
    response["payload"] = json.dumps(payload if payload is not None else {}, sort_keys=True)
    return response


def binary_response(status: int, payload: bytes, content_type: str) -> Dict[str, Any]:
    response = ricrest.initResponse(status=status, response="OK" if status < 400 else "ERROR")
    response["ctype"] = content_type
    response["payload"] = payload
    response["mode"] = "binary"
    return response


def protobuf_to_dict(message: Any) -> Dict[str, Any]:
    try:
        return MessageToDict(message, preserving_proto_field_name=True)
    except Exception:
        return {"text": str(message)}


def default_rmr_handler(app: "SteeringXapp", summary: Dict[str, Any], sbuf: Any) -> None:
    msg_type = summary.get(rmr.RMR_MS_MSG_TYPE)
    app.logger.warning(f"no handler registered for RMR message type {msg_type}")
    app.rmr_free(sbuf)


def config_change_handler(app: "SteeringXapp", config: Dict[str, Any]) -> None:
    app.current_config = config
    app.current_config_text = load_config_text(os.environ.get(Constants.CONFIG_FILE_ENV), config)
    app.command_service.apply_config(config)
    app.logger.info(f"loaded config for {config.get('name')} version {config.get('version')}")


class SteeringXapp(RMRXapp):
    def __init__(self) -> None:
        config_path = os.environ.get(Constants.CONFIG_FILE_ENV)
        config = load_config(config_path)
        self.current_config: Dict[str, Any] = config
        self.current_config_text = load_config_text(config_path, config)
        self.rest_server: Optional[ricrest.ThreadedHTTPServer] = None
        self.command_service = SteeringCommandService(config)

        controls = config.get("controls", {})
        rmr_port = int(controls.get("rmrPort", 4562))

        super().__init__(
            default_handler=default_rmr_handler,
            config_handler=config_change_handler,
            rmr_port=rmr_port,
            rmr_wait_for_ready=bool(controls.get("waitForRmrReady", False)),
            use_fake_sdl=bool(controls.get("useFakeSdl", False)),
        )

        self.command_service.logger = self.logger
        start_rest_server(self)
        self.command_service.start_deadman()

    def config_payload(self) -> Dict[str, Any]:
        return [
            {
                "config": self.current_config_text,
                "metadata": {
                    "xappName": self.current_config.get("name", APP_NAME),
                    "configType": "json",
                }
            }
        ]

    def stop(self) -> None:
        self.command_service.stop(reason="xapp_shutdown")
        self.command_service.stop_deadman()
        if self.rest_server is not None:
            self.rest_server.stop()
        super().stop()


def start_rest_server(app: SteeringXapp) -> None:
    if app.rest_server is not None:
        app.logger.info("REST server already started")
        return

    controls = app.current_config.get("controls", {})
    host = controls.get("restHost", "0.0.0.0")
    port = int(controls.get("restPort", 8080))

    SteeringRestHandler.xapp = app
    server = SteeringHTTPServer(host, port)
    server.handler.add_handler(server.handler, "POST", "steering-command", "/ric/v1/steering/command", rest_post_command(app))
    server.handler.add_handler(server.handler, "GET", "steering-state", "/ric/v1/steering/state", rest_get_steering_state(app))
    server.handler.add_handler(server.handler, "POST", "steering-stop", "/ric/v1/steering/stop", rest_post_stop(app))
    server.handler.add_handler(server.handler, "POST", "arm-pose", "/ric/v1/arm/pose", rest_post_arm_pose(app))
    server.handler.add_handler(server.handler, "GET", "arm-state", "/ric/v1/arm/state", rest_get_arm_state(app))
    server.handler.add_handler(server.handler, "GET", "video-snapshot", "/ric/v1/video/snapshot", rest_get_video_snapshot(app))
    server.handler.add_handler(server.handler, "GET", "oran-gnbs", "/ric/v1/oran/gnbs", rest_get_oran_gnbs(app))
    server.handler.add_handler(server.handler, "GET", "config", "/ric/v1/config", rest_get_config(app))
    server.handler.add_handler(server.handler, "GET", "alive", "/ric/v1/health/alive", rest_health_alive(app))
    server.handler.add_handler(server.handler, "GET", "ready", "/ric/v1/health/ready", rest_health_ready(app))
    server.start()

    app.rest_server = server
    app.logger.info(f"REST server listening on {host}:{port}")


def rest_get_config(app: SteeringXapp):
    def handler(_name: str, _path: str, _data: Optional[bytes], _ctype: str) -> Dict[str, Any]:
        return json_response(payload=app.config_payload())

    return handler


def rest_health_alive(app: SteeringXapp):
    def handler(_name: str, _path: str, _data: Optional[bytes], _ctype: str) -> Dict[str, Any]:
        return json_response(payload={"alive": True, "name": APP_NAME})

    return handler


def rest_health_ready(app: SteeringXapp):
    def handler(_name: str, _path: str, _data: Optional[bytes], _ctype: str) -> Dict[str, Any]:
        ready = app.healthcheck()
        return json_response(status=200 if ready else 503, payload={"ready": ready, "rmr_and_sdl": ready})

    return handler


def rest_get_steering_state(app: SteeringXapp):
    def handler(_name: str, _path: str, _data: Optional[bytes], _ctype: str) -> Dict[str, Any]:
        return json_response(payload=app.command_service.snapshot())

    return handler


def rest_get_oran_gnbs(app: SteeringXapp):
    def handler(_name: str, _path: str, _data: Optional[bytes], _ctype: str) -> Dict[str, Any]:
        try:
            gnb_ids = app.get_list_gnb_ids()
        except Exception as exc:
            app.logger.error(f"failed to read gNB IDs from RNIB/SDL: {exc}")
            return json_response(status=503, payload={"error": "failed to read gNB IDs", "detail": str(exc)})

        gnbs = [protobuf_to_dict(gnb_id) for gnb_id in gnb_ids]
        return json_response(payload={"count": len(gnbs), "gnbs": gnbs, "source": "RMRXapp.get_list_gnb_ids"})

    return handler


def rest_post_command(app: SteeringXapp):
    def handler(_name: str, _path: str, data: Optional[bytes], _ctype: str) -> Dict[str, Any]:
        try:
            body = json.loads((data or b"{}").decode("utf-8"))
        except ValueError:
            return json_response(status=400, payload={"error": "request body must be JSON"})
        if not isinstance(body, dict):
            return json_response(status=400, payload={"error": "request body must be a JSON object"})
        status, payload = app.command_service.submit(body)
        return json_response(status=status, payload=payload)

    return handler


def rest_post_stop(app: SteeringXapp):
    def handler(_name: str, _path: str, _data: Optional[bytes], _ctype: str) -> Dict[str, Any]:
        status, payload = app.command_service.stop(reason="operator")
        return json_response(status=status, payload=payload)

    return handler


def rest_post_arm_pose(app: SteeringXapp):
    def handler(_name: str, _path: str, data: Optional[bytes], _ctype: str) -> Dict[str, Any]:
        try:
            body = json.loads((data or b"{}").decode("utf-8"))
        except ValueError:
            return json_response(status=400, payload={"error": "request body must be JSON"})
        if not isinstance(body, dict):
            return json_response(status=400, payload={"error": "request body must be a JSON object"})
        status, payload = app.command_service.submit_arm_pose(body)
        return json_response(status=status, payload=payload)

    return handler


def rest_get_arm_state(app: SteeringXapp):
    def handler(_name: str, _path: str, _data: Optional[bytes], _ctype: str) -> Dict[str, Any]:
        return json_response(payload=app.command_service.arm_snapshot())

    return handler


def rest_get_video_snapshot(app: SteeringXapp):
    def handler(_name: str, _path: str, _data: Optional[bytes], _ctype: str) -> Dict[str, Any]:
        status, payload, content_type = app.command_service.video_snapshot(query=urlparse(_path).query)
        return binary_response(status=status, payload=payload, content_type=content_type)

    return handler


def main() -> None:
    app = SteeringXapp()
    app.run(thread=False, rmr_timeout=5, inotify_timeout=0)


if __name__ == "__main__":
    main()
