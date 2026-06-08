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
from typing import Any, Dict, Optional

from google.protobuf.json_format import MessageToDict
from ricxappframe.rmr import rmr
from ricxappframe.util.constants import Constants
from ricxappframe.xapp_frame import RMRXapp
from ricxappframe import xapp_rest as ricrest

from steering_service import SteeringCommandService


APP_NAME = "steering-wheel-command-xapp"


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

    ## TODO
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

        ## TODO
        Complete the startup sequence:

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
        # TODO: initialize the xApp.

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
        # TODO: return the config payload.

    def stop(self) -> None:
        """
        Shut down cleanly.

        ## TODO
        Suggested cleanup order:

            1. Send a stop command through `self.command_service.stop(...)`.
            2. Stop the command service deadman thread.
            3. Stop the REST server if it exists.
            4. Call `super().stop()`.
        """
        # TODO: implement graceful shutdown.


# ---------------------------------------------------------------------------
# REST server registration
# ---------------------------------------------------------------------------

def start_rest_server(app: SteeringXapp) -> None:
    """
    Create the REST server object, register routes, and start listening.

    This function includes one GET route and one POST route as examples:

        - GET `/ric/v1/health/alive`
        - POST `/ric/v1/steering/command`

    ## TODO
    Add the remaining routes:

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

    server = ricrest.ThreadedHTTPServer(host, port)

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

    # TODO: register the remaining routes listed above.

    server.start()
    app.rest_server = server
    app.logger.info(f"REST server listening on {host}:{port}")


# ---------------------------------------------------------------------------
# REST handlers
# ---------------------------------------------------------------------------

def rest_get_config(app: SteeringXapp):
    """
    Return xApp config.

    ## TODO
    Follow the same nested handler pattern used by `rest_health_alive`.
    The returned payload should come from:

        app.config_payload()
    """

    def handler(_name: str, _path: str, _data: Optional[bytes], _ctype: str) -> Dict[str, Any]:
        # TODO: return `json_response(payload=app.config_payload())`.
        pass

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

    ## TODO
    Use `app.healthcheck()` so Kubernetes/RIC readiness reflects framework
    dependencies.  Return status 200 when ready and 503 when not ready.

    Example payload:

        {"ready": ready, "rmr_and_sdl": ready}
    """

    def handler(_name: str, _path: str, _data: Optional[bytes], _ctype: str) -> Dict[str, Any]:
        # TODO: call `app.healthcheck()` and return 200 or 503.
        pass

    return handler


def rest_get_steering_state(app: SteeringXapp):
    """
    Return a snapshot from the command service.

    ## TODO
    Do not manually assemble state here.  Let the service expose its own view:

        app.command_service.snapshot()
    """

    def handler(_name: str, _path: str, _data: Optional[bytes], _ctype: str) -> Dict[str, Any]:
        # TODO: return the command service snapshot.
        pass

    return handler


def rest_get_oran_gnbs(app: SteeringXapp):
    """
    Optional ORAN inventory endpoint.

    ## TODO
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
        # TODO: implement optional gNB inventory lookup.
        pass

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

    ## TODO
    Call:

        app.command_service.stop(reason="operator")

    Then return the status/payload as JSON.
    """

    def handler(_name: str, _path: str, _data: Optional[bytes], _ctype: str) -> Dict[str, Any]:
        # TODO: call service stop and return JSON response.
        pass

    return handler


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

def main() -> None:
    """
    Program entrypoint.

    ## TODO
    Finished solution shape:

        app = SteeringXapp()
        app.run(thread=False, rmr_timeout=5, inotify_timeout=0)

    `thread=False` keeps the xApp in the foreground for container execution.
    """
    # TODO: create SteeringXapp and run it.


if __name__ == "__main__":
    main()
