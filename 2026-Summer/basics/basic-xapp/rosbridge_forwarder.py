#!/usr/bin/env python3
"""
HTTP-to-rosbridge forwarder for the ROSOrin command path.

This helper receives HTTP POST requests containing ROS Twist-style JSON, then
publishes that message to a ROS topic through rosbridge WebSocket.

Typical path:

    xApp
        -> HTTP POST to this forwarder
        -> rosbridge WebSocket
        -> ROS topic such as /cmd_vel
        -> robot movement controller

The xApp can already create a payload shaped like:

    {
        "linear": {
            "x": 0.3,
            "y": 0.0,
            "z": 0.0
        },
        "angular": {
            "x": 0.0,
            "y": 0.0,
            "z": -0.2
        }
    }

This file is the bridge between HTTP JSON and rosbridge publish messages.

Keep the jobs separate:

    steering_service.py      -> creates robot payload JSON
    rosbridge_forwarder.py   -> forwards Twist JSON to rosbridge
    rosbridge                -> sends the message into ROS

Concept map:

    HTTP
        A request/response protocol. The xApp sends one request. This helper
        sends one response.

    WebSocket
        A longer-lived connection. rosbridge uses WebSocket so other programs
        can publish or subscribe to ROS topics without being a ROS node.

    ROS topic
        A named channel such as /cmd_vel. Programs publish messages to a topic,
        and other ROS programs subscribe to that topic.

    Twist
        A common ROS movement message. `linear` describes straight-line motion.
        `angular` describes rotation.
"""

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict

import websocket


class RosbridgeForwarder(BaseHTTPRequestHandler):
    """
    HTTP request handler for forwarding Twist commands to rosbridge.

    `BaseHTTPRequestHandler` calls methods based on the HTTP request method:

        GET  -> do_GET()
        POST -> do_POST()

    Class variables below are shared settings for every request handler object.
    `main()` should set these values from command-line arguments before the
    server starts.

    Concept:

        The HTTP server creates a new handler object for each request. Class
        variables give all those handler objects the same shared settings:

            rosbridge_url
            default_topic
            timeout

        This avoids passing those values into every request by hand.
    """

    rosbridge_url = ""
    # TODO: add default_topic with default "/cmd_vel".
    # TODO: add timeout with default 0.5.

    def do_GET(self) -> None:
        """
        Handle simple health checks.

        Expected route:

            GET /health

        Concept:

            A health endpoint is a small test endpoint. It does not move the
            robot. It only confirms that this helper process is running and
            knows which rosbridge URL/topic it is configured to use.

        Expected JSON response:

            {
                "alive": true,
                "rosbridge_url": "...",
                "default_topic": "/cmd_vel"
            }

        ## TODO
        Implement this flow:

            1. If `self.path == "/health"`, return status 200.
            2. Include alive, rosbridge_url, and default_topic in the payload.
            3. For any other path, return status 404 with `{"error": "not found"}`.

        Method-call syntax:

            self._send_json(200, {"alive": True})

        Status code meaning:

            200 -> request worked
            404 -> this path does not exist on this helper
        """
        # TODO: implement GET /health and 404 behavior.

    def do_POST(self) -> None:
        """
        Handle one HTTP POST containing Twist JSON.

        Request body shape:

            {
                "linear": {"x": 0.3, "y": 0.0, "z": 0.0},
                "angular": {"x": 0.0, "y": 0.0, "z": -0.2}
            }

        Concept:

            POST is used because the request is asking this helper to do an
            action: publish a movement command. GET should not be used for
            movement commands because GET is normally for reading information.

        Topic rule:

            - POST /cmd_vel publishes to /cmd_vel
            - POST /controller/cmd_vel publishes to /controller/cmd_vel
            - POST / publishes to `self.default_topic`

        ## TODO
        Implement this flow:

            1. Read `Content-Length` from headers.
            2. Read that many bytes from `self.rfile`.
            3. Use `{}` when the body is empty.
            4. Choose the topic from `self.path`.
            5. Decode JSON with `json.loads`.
            6. Convert the body to clean Twist fields with `_coerce_twist`.
            7. Publish it with `_publish_twist`.
            8. Return status 202 when accepted.
            9. Return status 400 for invalid JSON.
            10. Return status 400 for invalid Twist fields.
            11. Return status 502 when rosbridge publishing fails.

        Header syntax:

            self.headers.get("Content-Length", "0")

        Body-read syntax:

            body = self.rfile.read(length)

        Content-Length concept:

            HTTP sends the body as bytes. `Content-Length` tells the server how
            many bytes to read. If the server reads too little, the JSON is cut
            off. If it reads too much, it may wait for bytes that never arrive.

        JSON decoding concept:

            The xApp sends JSON text. Python logic works with dictionaries.
            `json.loads(...)` converts JSON text into Python data.

        Twist validation concept:

            Network input is not trusted. The helper must check that the body
            really has `linear` and `angular` fields, and that the values can be
            converted into numbers.

        Exception syntax:

            try:
                ...
            except json.JSONDecodeError as exc:
                ...
            except ValueError as exc:
                ...
            except Exception as exc:
                ...

        Status code meaning:

            202 -> command accepted for forwarding
            400 -> request body is bad
            502 -> helper understood the request, but rosbridge publish failed
        """
        # TODO: implement POST body parsing, Twist validation, publishing, and errors.

    def log_message(self, fmt: str, *args: Any) -> None:
        """
        Print HTTP server log messages.

        This method overrides the default `BaseHTTPRequestHandler` logging.
        It is kept complete as a small reference example.

        Concept:

            Every HTTP request can produce a log line. Logs help connect a curl
            command to what the server saw.

        String formatting syntax:

            fmt % args

        Flush syntax:

            print("message", flush=True)
        """
        print("%s - %s" % (self.address_string(), fmt % args), flush=True)

    def _coerce_twist(self, payload: Dict[str, Any]) -> Dict[str, Dict[str, float]]:
        """
        Validate and normalize a Twist-like dictionary.

        Required top-level keys:

            linear
            angular

        Each section can contain:

            x
            y
            z

        Missing x/y/z values should default to 0.0.

        Concept:

            "Coerce" means convert input into the exact shape and type needed by
            the next step. Here, the next step is rosbridge publishing, so the
            result must be a clean Twist dictionary containing floats.

        Missing x/y/z defaults:

            A Twist message has six movement numbers:

                linear.x, linear.y, linear.z
                angular.x, angular.y, angular.z

            For this robot path, most commands only need `linear.x` and
            `angular.z`. The unused directions can safely default to 0.0.

        ## TODO
        Implement this flow:

            1. Read `payload["linear"]`.
            2. Read `payload["angular"]`.
            3. Return a dictionary with numeric float values.
            4. Use `.get("x", 0.0)` for x/y/z defaults.
            5. Catch `KeyError`, `TypeError`, and `ValueError`.
            6. Raise `ValueError("body must contain numeric geometry_msgs/Twist linear/angular fields")`.

        Dictionary access syntax:

            linear = payload["linear"]

        Difference between `payload["linear"]` and `.get(...)`:

            payload["linear"]
                Required field. Raise an error if missing.

            linear.get("x", 0.0)
                Optional field. Use 0.0 if missing.

        Safe default syntax:

            linear.get("x", 0.0)

        Float conversion syntax:

            float(linear.get("x", 0.0))

        Return shape:

            {
                "linear": {"x": 0.0, "y": 0.0, "z": 0.0},
                "angular": {"x": 0.0, "y": 0.0, "z": 0.0},
            }
        """
        # TODO: validate and return clean Twist values.

    def _publish_twist(self, topic: str, twist: Dict[str, Dict[str, float]]) -> None:
        """
        Publish one Twist message to rosbridge.

        rosbridge advertise message shape:

            {
                "op": "advertise",
                "topic": "/cmd_vel",
                "type": "geometry_msgs/Twist"
            }

        rosbridge publish message shape:

            {
                "op": "publish",
                "topic": "/cmd_vel",
                "msg": {
                    "linear": {"x": 0.0, "y": 0.0, "z": 0.0},
                    "angular": {"x": 0.0, "y": 0.0, "z": 0.0}
                }
            }

        Concept:

            rosbridge does not receive a raw Twist by itself. It receives
            wrapper messages that say what operation to perform.

            The updated command path sends two rosbridge messages:

                1. advertise the topic and message type
                2. publish the Twist message

            The important wrapper fields are:

                op      -> "advertise" or "publish"
                topic   -> the ROS topic name
                type    -> ROS message type, for advertise
                msg     -> actual ROS message payload, for publish

        ## TODO
        Implement this flow:

            1. Make sure the topic starts with `/`.
            2. Save the clean topic name in `ros_topic`.
            3. Build an advertise dictionary with type `geometry_msgs/Twist`.
            4. Build the publish message dictionary.
            5. Connect with `websocket.create_connection`.
            6. Send the advertise JSON first.
            7. Send the publish JSON second.
            8. Always close the connection.

        Topic syntax:

            ros_topic = topic if topic.startswith("/") else f"/{topic}"

        ROS topic name concept:

            ROS topic names are commonly written as absolute names beginning
            with `/`, such as `/cmd_vel`. This helper accepts `cmd_vel` and
            converts it to `/cmd_vel` for convenience.

        WebSocket syntax:

            connection = websocket.create_connection(self.rosbridge_url, timeout=self.timeout)
            connection.send(json.dumps(advertise))
            connection.send(json.dumps(message))
            connection.close()

        Dictionary-building syntax:

            advertise = {
                "op": "advertise",
                "topic": ros_topic,
                "type": "geometry_msgs/Twist",
            }

            message = {
                "op": "publish",
                "topic": ros_topic,
                "msg": twist,
            }

        Cleanup syntax:

            try:
                ...
            finally:
                connection.close()

        Cleanup concept:

            A network send can fail. `finally` still runs after success or
            failure, so the WebSocket connection is closed either way.
        """
        # TODO: create rosbridge publish message and send it over WebSocket.

    def _send_json(self, status: int, payload: Dict[str, Any]) -> None:
        """
        Send an HTTP JSON response.

        This method is kept mostly complete as a reference pattern because many
        HTTP responses in this file use the same steps.

        Concept:

            HTTP responses are bytes. A Python dictionary must be converted to
            JSON text, then encoded to bytes, before it can be written back to
            the client.

        Steps:

            1. Convert payload dictionary to JSON text.
            2. Encode JSON text as UTF-8 bytes.
            3. Send status code.
            4. Send Content-Type header.
            5. Send Content-Length header.
            6. End headers.
            7. Write response body bytes.

        HTTP response method syntax:

            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body)

        Header meaning:

            Content-Type
                Tells the client the body is JSON.

            Content-Length
                Tells the client how many bytes are in the response body.
        """
        body = json.dumps(payload, sort_keys=True).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def parse_args() -> argparse.Namespace:
    """
    Read command-line arguments.

    Example run:

        python3 rosbridge_forwarder.py \
          --listen-host 0.0.0.0 \
          --listen-port 8090 \
          --rosbridge-url ws://ROBOT_IP:9090 \
          --default-topic /cmd_vel

    Concept:

        Command-line arguments let the same file run in different environments
        without changing the code. For example, the robot IP or topic may be
        different on another network.

    ## TODO
    Add arguments:

        --listen-host
        --listen-port
        --rosbridge-url
        --default-topic
        --timeout

    argparse syntax:

        parser.add_argument("--name", type=some_type, default=value, help="text")

    Required argument syntax:

        parser.add_argument("--rosbridge-url", required=True, help="...")

    Required rosbridge URL concept:

        Without the rosbridge WebSocket URL, this helper has nowhere to publish
        the Twist message.

    Return syntax:

        return parser.parse_args()
    """
    parser = argparse.ArgumentParser(description="Forward HTTP Twist commands to ROS rosbridge")
    # TODO: add parser.add_argument(...) calls.
    return parser.parse_args()


def main() -> None:
    """
    Program entrypoint.

    Concept:

        `main()` connects the setup pieces:

            command-line args
            class-level handler settings
            HTTP server object
            forever-running request loop

        After `serve_forever()` starts, the program waits for HTTP requests.

    ## TODO
    Implement this flow:

        1. Parse command-line arguments.
        2. Copy argument values onto `RosbridgeForwarder` class variables.
        3. Create `ThreadingHTTPServer`.
        4. Print the forwarding address.
        5. Run `server.serve_forever()`.

    Class variable assignment syntax:

        RosbridgeForwarder.rosbridge_url = args.rosbridge_url

    Server syntax:

        server = ThreadingHTTPServer(
            (args.listen_host, args.listen_port),
            RosbridgeForwarder,
        )

    Serve syntax:

        server.serve_forever()

    `serve_forever()` concept:

        Keep the process running and keep accepting requests until the process
        is stopped.
    """
    # TODO: parse args, configure handler class, create server, serve forever.


if __name__ == "__main__":
    main()
