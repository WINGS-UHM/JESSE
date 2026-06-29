#!/usr/bin/env python3
"""
Steering-wheel command xApp.

The command path is REST/IP:

    wheel client -> this xApp -> robot UE HTTP endpoint

RMR is still initialized by `RMRXapp` for normal xApp framework behavior,
configuration handling, health checks, and platform startup.  This file does
not advertise or consume custom E2 control or indication messages.

Main idea:

    - `steering_xapp.py` handles xApp setup and REST endpoints.
    - `steering_service.py` handles command validation, mapping, forwarding,
      state, and deadman stop behavior.

Keep those jobs separate.  The REST layer should parse requests and return
responses.  The service layer should decide whether commands are valid.
"""

import json
import os
import http.server
from typing import Any, Dict, Optional

import requests
from google.protobuf.json_format import MessageToDict
from ricxappframe.rmr import rmr
from ricxappframe.util.constants import Constants
from ricxappframe.xapp_frame import RMRXapp
from ricxappframe import xapp_rest as ricrest

from steering_service import SteeringCommandService


APP_NAME = "steering-wheel-command-xapp"


class SteeringRestHandler(ricrest.RestHandler):
    """
    REST handler class used when the video stream route is added.

    Concept:

        Normal JSON routes are registered with `add_handler(...)`.  A streaming
        route needs direct control over the HTTP response because it sends many
        chunks over one request.

    Completed video stream proxying:

        1. In `do_GET`, detect `/ric/v1/video/stream`.
        2. Call `_proxy_video_stream(self.xapp)`.
        3. Use `requests.get(url, stream=True, timeout=(connect_timeout, None))`.
        4. Forward status, Content-Type, Cache-Control, and stream chunks.
        5. Handle client disconnects without crashing the xApp.

    Method override syntax:

        def do_GET(self):
            ...

    Superclass-call syntax:

        super().do_GET()

    Route-detection syntax:

        if self.path.find("/ric/v1/video/stream") >= 0 and self.xapp is not None:
            self._proxy_video_stream(self.xapp)
            return

    Response-header syntax:

        self.send_response(upstream.status_code)
        self.send_header("Content-type", upstream.headers.get("Content-Type", "multipart/x-mixed-replace; boundary=frame"))
        self.send_header("Cache-Control", upstream.headers.get("Cache-Control", "no-cache"))
        self.end_headers()
    """

    xapp: Optional["SteeringXapp"] = None

    def do_GET(self):
        if self.path.find("/ric/v1/video/stream") >= 0 and self.xapp is not None:
            self._proxy_video_stream(self.xapp)
            return
        super().do_GET()

    def _proxy_video_stream(self, app: "SteeringXapp") -> None:
        """
        Proxy the robot camera stream through the xApp.

        Concept:

            The wheel client should only need the xApp URL.  This method hides
            the robot-side video URL behind the xApp REST API.

        Completed flow:

            1. Ask the service for the robot-side video stream URL.
            2. Open a streaming GET request to that URL.
            3. Copy response headers that matter to video clients.
            4. Forward each incoming chunk to this HTTP response.

        Stream-copy example:

            for chunk in upstream.iter_content(chunk_size=8192):
                if not chunk:
                    continue
                self.wfile.write(chunk)
                self.wfile.flush()

        Disconnect exception example:

            except (BrokenPipeError, ConnectionResetError):
                app.logger.info("video stream client disconnected")
        """
        url = app.command_service.video_stream_url()
        connect_timeout = max(app.command_service.robot.timeout_seconds, 2.0)
        try:
            with requests.get(url, stream=True, timeout=(connect_timeout, None)) as upstream:
                self.send_response(upstream.status_code)
                self.send_header("Content-type", upstream.headers.get("Content-Type", "multipart/x-mixed-replace; boundary=frame"))
                self.send_header("Cache-Control", upstream.headers.get("Cache-Control", "no-cache"))
                self.end_headers()
                for chunk in upstream.iter_content(chunk_size=8192):
                    if not chunk:
                        continue
                    self.wfile.write(chunk)
                    self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            app.logger.info("video stream client disconnected")
        except requests.RequestException as exc:
            app.logger.error(f"video stream proxy failed: {exc}")
            payload = json.dumps({"error": "video stream proxy failed", "detail": str(exc)}).encode("utf-8")
            try:
                self.send_response(502)
                self.send_header("Content-type", "application/json")
                self.send_header("Content-length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
            except (BrokenPipeError, ConnectionResetError):
                app.logger.info("video stream client disconnected")


class SteeringHTTPServer(ricrest.ThreadedHTTPServer):
    """
    REST server class that can use `SteeringRestHandler`.

    Concept:

        `ThreadingHTTPServer` lets a long video stream run without blocking
        short JSON routes such as `/ric/v1/health/alive`.
    """

    handler = SteeringRestHandler
    server_class = http.server.ThreadingHTTPServer


# ---------------------------------------------------------------------------
# Config and response helpers
# ---------------------------------------------------------------------------

def load_config(path: Optional[str]) -> Dict[str, Any]:
    """
    Load the xApp JSON config file.

    `Optional[str]` means `path` can be a string or `None`.
    `Dict[str, Any]` means this function returns a dictionary with string keys.

    The framework normally stores the config path in:

        os.environ[Constants.CONFIG_FILE_ENV]

    If no path is provided, return an empty dictionary so local experiments can
    still create the xApp with default values.
    """
    if not path:
        return {}
    with open(path, "r", encoding="utf-8") as config_file:
        return json.load(config_file)


def load_config_text(path: Optional[str], config: Dict[str, Any]) -> str:
    """
    Return config text for the `/ric/v1/config` endpoint.

    The xApp keeps both forms:

        - parsed dictionary for Python code
        - raw JSON text for the config REST endpoint

    If the original file exists, return its exact text.  Otherwise, turn the
    dictionary back into JSON text.
    """
    if path and os.path.isfile(path):
        with open(path, "r", encoding="utf-8") as config_file:
            return config_file.read()
    return json.dumps(config, sort_keys=True)


def json_response(status: int = 200, payload: Optional[Any] = None) -> Dict[str, Any]:
    """
    Build a JSON response in the shape expected by `ricxappframe.xapp_rest`.

    REST handlers in this file should return this kind of dictionary instead of
    returning plain Python data.
    """
    response = ricrest.initResponse(status=status, response="OK" if status < 400 else "ERROR")
    response["ctype"] = "application/json"
    response["payload"] = json.dumps(payload if payload is not None else {}, sort_keys=True)
    return response


def binary_response(status: int, payload: bytes, content_type: str) -> Dict[str, Any]:
    """
    Build a binary REST response for image snapshot data.

    Concept:

        JSON responses use text payloads.  A camera snapshot uses raw bytes, so
        the response needs a binary mode and the correct Content-Type.

    Completed helper for:

        GET /ric/v1/video/snapshot

    Reference syntax:

        response = ricrest.initResponse(status=status, response="OK" if status < 400 else "ERROR")
        response["ctype"] = content_type
        response["payload"] = payload
        response["mode"] = "binary"
        return response

    This uses the same response dictionary style as `json_response`, but the
    payload stays as bytes instead of using `json.dumps(...)`.
    """
    response = ricrest.initResponse(status=status, response="OK" if status < 400 else "ERROR")
    response["ctype"] = content_type
    response["payload"] = payload
    response["mode"] = "binary"
    return response


def protobuf_to_dict(message: Any) -> Dict[str, Any]:
    """
    Convert framework/RNIB protobuf objects into dictionaries for JSON output.

    Some framework helper methods return protobuf-style objects.  JSON cannot
    directly encode those objects, so this helper converts them first.
    """
    try:
        return MessageToDict(message, preserving_proto_field_name=True)
    except Exception:
        return {"text": str(message)}


def default_rmr_handler(app: "SteeringXapp", summary: Dict[str, Any], sbuf: Any) -> None:
    """
    Handle unexpected RMR messages.

    This xApp uses REST for steering commands, so it does not need custom RMR
    message handlers yet.  If an RMR message arrives anyway, log its type and
    free the buffer.
    """
    msg_type = summary.get(rmr.RMR_MS_MSG_TYPE)
    app.logger.warning(f"no handler registered for RMR message type {msg_type}")
    app.rmr_free(sbuf)


def config_change_handler(app: "SteeringXapp", config: Dict[str, Any]) -> None:
    """
    Apply a config update from the xApp framework.

    Concept:

    Trace the four actions in this function:

        1. Save the parsed config on the xApp object.
        2. Refresh the raw config text.
        3. Send the config into `SteeringCommandService`.
        4. Log the loaded config name and version.
    """
    app.current_config = config
    app.current_config_text = load_config_text(os.environ.get(Constants.CONFIG_FILE_ENV), config)
    app.command_service.apply_config(config)
    app.logger.info(f"loaded config for {config.get('name')} version {config.get('version')}")


# ---------------------------------------------------------------------------
# Main xApp class
# ---------------------------------------------------------------------------

class SteeringXapp(RMRXapp):
    """
    xApp shell around the command service.

    This class should focus on platform setup:

        - read initial config
        - initialize `RMRXapp`
        - create `SteeringCommandService`
        - start REST routes
        - start/stop the deadman timer
        - expose `/ric/v1/config`

    Avoid putting steering validation or robot payload mapping here.  That work
    belongs in `steering_service.py`.
    """

    def __init__(self) -> None:
        """
        Build the xApp.

        Code pattern:

            1. Read the config path from `Constants.CONFIG_FILE_ENV`.
            2. Load parsed config with `load_config`.
            3. Save `self.current_config`.
            4. Save `self.current_config_text`.
            5. Create `self.rest_server` and set it to `None`.
            6. Create `self.command_service = SteeringCommandService(config)`.
            7. Read RMR settings from `controls`.
            8. Call `super().__init__(...)`.
            9. Connect `self.logger` to the command service.
            10. Call `start_rest_server(self)`.
            11. Start the deadman thread.

        Useful sample:

            config_path = os.environ.get(Constants.CONFIG_FILE_ENV)
            config = load_config(config_path)
            controls = config.get("controls", {})
            rmr_port = int(controls.get("rmrPort", 4562))

            super().__init__(
                default_handler=default_rmr_handler,
                config_handler=config_change_handler,
                rmr_port=rmr_port,
                rmr_wait_for_ready=bool(controls.get("waitForRmrReady", False)),
                use_fake_sdl=bool(controls.get("useFakeSdl", False)),
            )
        """
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
        """
        Return the payload for:

            GET /ric/v1/config

        Target shape:

            [
                {
                    "config": "...raw JSON text...",
                    "metadata": {
                        "xappName": "steering-wheel-command-xapp",
                        "configType": "json",
                    },
                }
            ]
        """
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
        """
        Shut down cleanly.

        Code pattern:

        Suggested cleanup order:

            1. Send a stop command through `self.command_service.stop(...)`.
            2. Stop the command service deadman thread.
            3. Stop the REST server if it exists.
            4. Call `super().stop()`.
        """
        self.command_service.stop(reason="xapp_shutdown")
        self.command_service.stop_deadman()
        if self.rest_server is not None:
            self.rest_server.stop()
        super().stop()


# ---------------------------------------------------------------------------
# REST server registration
# ---------------------------------------------------------------------------

def start_rest_server(app: SteeringXapp) -> None:
    """
    Create the REST server object, register routes, and start listening.

    This function includes one GET route and one POST route as examples:

        - GET `/ric/v1/health/alive`
        - POST `/ric/v1/steering/command`

    Concept:

    This function includes the completed command/control and video routes.  The
    servo-arm routes are registered so their service-layer TODO sections can be
    completed in `steering_service.py`.

        POST /ric/v1/steering/stop
        GET  /ric/v1/steering/state
        GET  /ric/v1/oran/gnbs
        GET  /ric/v1/config
        GET  /ric/v1/health/ready

    Handler registration pattern:

        server.handler.add_handler(
            server.handler,
            "GET",
            "alive",
            "/ric/v1/health/alive",
            rest_health_alive(app),
        )
    """
    if app.rest_server is not None:
        app.logger.info("REST server already started")
        return

    controls = app.current_config.get("controls", {})
    host = controls.get("restHost", "0.0.0.0")
    port = int(controls.get("restPort", 8080))

    SteeringRestHandler.xapp = app
    server = SteeringHTTPServer(host, port)

    # GET example: simple health check route.
    server.handler.add_handler(
        server.handler,
        "GET",
        "alive",
        "/ric/v1/health/alive",
        rest_health_alive(app),
    )

    # POST example: route that reads JSON bytes from the request body.
    server.handler.add_handler(
        server.handler,
        "POST",
        "steering-command",
        "/ric/v1/steering/command",
        rest_post_command(app),
    )

    server.handler.add_handler(server.handler, "POST", "steering-stop", "/ric/v1/steering/stop", rest_post_stop(app))
    server.handler.add_handler(server.handler, "GET", "steering-state", "/ric/v1/steering/state", rest_get_steering_state(app))
    server.handler.add_handler(server.handler, "GET", "video-snapshot", "/ric/v1/video/snapshot", rest_get_video_snapshot(app))
    server.handler.add_handler(server.handler, "POST", "arm-pose", "/ric/v1/arm/pose", rest_post_arm_pose(app))
    server.handler.add_handler(server.handler, "GET", "arm-state", "/ric/v1/arm/state", rest_get_arm_state(app))
    server.handler.add_handler(server.handler, "GET", "oran-gnbs", "/ric/v1/oran/gnbs", rest_get_oran_gnbs(app))
    server.handler.add_handler(server.handler, "GET", "config", "/ric/v1/config", rest_get_config(app))
    server.handler.add_handler(server.handler, "GET", "ready", "/ric/v1/health/ready", rest_health_ready(app))

    server.start()
    app.rest_server = server
    app.logger.info(f"REST server listening on {host}:{port}")


# ---------------------------------------------------------------------------
# REST handlers
# ---------------------------------------------------------------------------

def rest_get_config(app: SteeringXapp):
    """
    Return xApp config.

    Code pattern:

    Follow the same nested handler pattern used by `rest_health_alive`.
    The returned payload should come from:

        app.config_payload()
    """

    def handler(_name: str, _path: str, _data: Optional[bytes], _ctype: str) -> Dict[str, Any]:
        return json_response(payload=app.config_payload())

    return handler


def rest_health_alive(app: SteeringXapp):
    """
    GET example: liveness endpoint.

    A GET handler usually ignores the request body and returns current state.
    This endpoint only proves the HTTP process is alive.  It does not prove that
    RMR/SDL are ready.
    """

    def handler(_name: str, _path: str, _data: Optional[bytes], _ctype: str) -> Dict[str, Any]:
        return json_response(payload={"alive": True, "name": APP_NAME})

    return handler


def rest_health_ready(app: SteeringXapp):
    """
    Readiness endpoint.

    Concept:

    Use `app.healthcheck()` so Kubernetes/RIC readiness reflects framework
    dependencies.  Return status 200 when ready and 503 when not ready.

    Example payload:

        {"ready": ready, "rmr_and_sdl": ready}
    """

    def handler(_name: str, _path: str, _data: Optional[bytes], _ctype: str) -> Dict[str, Any]:
        ready = app.healthcheck()
        return json_response(status=200 if ready else 503, payload={"ready": ready, "rmr_and_sdl": ready})

    return handler


def rest_get_steering_state(app: SteeringXapp):
    """
    Return a snapshot from the command service.

    Code pattern:

    Do not manually assemble state here.  Let the service expose its own view:

        app.command_service.snapshot()
    """

    def handler(_name: str, _path: str, _data: Optional[bytes], _ctype: str) -> Dict[str, Any]:
        return json_response(payload=app.command_service.snapshot())

    return handler


def rest_get_oran_gnbs(app: SteeringXapp):
    """
    Optional ORAN inventory endpoint.

    Code pattern:

    Implement this flow:

        1. Call `app.get_list_gnb_ids()`.
        2. Convert each returned object with `protobuf_to_dict`.
        3. Return count, list, and source name.
        4. Return HTTP 503 if the RNIB/SDL lookup fails.

    Success payload idea:

        {
            "count": len(gnbs),
            "gnbs": gnbs,
            "source": "RMRXapp.get_list_gnb_ids",
        }
    """

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
    """
    POST example: accept one steering-wheel command.

    A POST handler usually reads request body data.  In this route, the body is
    JSON bytes from the wheel client.

    Expected request body:

        {
            "seq": 1,
            "timestamp_ms": 1717800000000,
            "steering": 0.1,
            "throttle": 0.2,
            "brake": 0.0,
            "enable": true
        }

    This handler only parses the request and passes the dictionary to the
    service.  Detailed command validation stays in `SteeringCommandService`.
    """

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
    """
    Operator stop endpoint.

    Code pattern:

    Call:

        app.command_service.stop(reason="operator")

    Then return the status/payload as JSON.
    """

    def handler(_name: str, _path: str, _data: Optional[bytes], _ctype: str) -> Dict[str, Any]:
        status, payload = app.command_service.stop(reason="operator")
        return json_response(status=status, payload=payload)

    return handler


def rest_post_arm_pose(app: SteeringXapp):
    """
    POST one servo-arm pose command.

    Expected request body:

        {
            "duration": 0.2,
            "positions": [
                {"id": 1, "position": 500}
            ]
        }

    Concept:

        This REST handler should look like `rest_post_command`: decode the JSON
        body, pass the dictionary to the service, and return the service result
        as JSON.

    JSON decode syntax:

        body = decode_json_body(data)

    Service-call syntax:

        status, payload = app.command_service.submit_arm_pose(body)

    Route wiring is complete here.  The servo-arm validation and forwarding
    work is in `steering_service.py` and `rosbridge_forwarder.py`.
    """

    def handler(_name: str, _path: str, data: Optional[bytes], _ctype: str) -> Dict[str, Any]:
        try:
            body = decode_json_body(data)
        except ValueError as exc:
            return json_response(status=400, payload={"error": str(exc)})
        status, payload = app.command_service.submit_arm_pose(body)
        return json_response(status=status, payload=payload)

    return handler


def rest_get_arm_state(app: SteeringXapp):
    """
    GET the current servo-arm state.

    Concept:

        This follows the same route shape as `rest_get_steering_state`, but it
        calls the arm-specific service method.

    Service-call syntax:

        app.command_service.arm_snapshot()

    Route wiring is complete here.  Add extra arm state fields in
    `SteeringCommandService.arm_snapshot()` when the controller needs them.
    """

    def handler(_name: str, _path: str, _data: Optional[bytes], _ctype: str) -> Dict[str, Any]:
        return json_response(payload=app.command_service.arm_snapshot())

    return handler


def rest_get_video_snapshot(app: SteeringXapp):
    """
    Return one camera image through the xApp.

    Concept:

        This route should call the service layer because the service owns the
        robot URL and robot-side paths.  The xApp route only converts the
        service result into a REST response.

    Function-call syntax from the complete reference:

        status, payload, content_type = app.command_service.video_snapshot()
        return binary_response(status=status, payload=payload, content_type=content_type)

    Nested handler pattern:

        def handler(_name, _path, _data, _ctype):
            ...

        return handler

    The snapshot handler follows the same shape as `rest_get_steering_state`,
    but it returns `binary_response(...)` instead of `json_response(...)`.

    Completed video snapshot route.
    """

    def handler(_name: str, _path: str, _data: Optional[bytes], _ctype: str) -> Dict[str, Any]:
        status, payload, content_type = app.command_service.video_snapshot()
        return binary_response(status=status, payload=payload, content_type=content_type)

    return handler


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

def main() -> None:
    """
    Program entrypoint.

    Code pattern:

    Finished solution shape:

        app = SteeringXapp()
        app.run(thread=False, rmr_timeout=5, inotify_timeout=0)

    `thread=False` keeps the xApp in the foreground for container execution.
    """
    app = SteeringXapp()
    app.run(thread=False, rmr_timeout=5, inotify_timeout=0)


if __name__ == "__main__":
    main()
