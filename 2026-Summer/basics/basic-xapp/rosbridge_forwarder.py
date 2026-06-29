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
import base64
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse
from typing import Any, Dict, Optional, Tuple

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

    rosbridge_url = "ws://10.45.1.3:9090"
    default_topic = "/cmd_vel"
    default_video_topic = "/depth_cam/rgb0/image_raw"
    default_arm_topic = "/servo_controller"
    timeout = 0.5

    def do_GET(self) -> None:
        """
        Handle simple health checks.

        Expected routes:

            GET /health
            GET /video/snapshot
            GET /video/stream

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

        Concept:

            The video routes read ROS image messages through rosbridge and
            return either one image or a multipart stream.

        Method-call syntax:

            self._send_json(200, {"alive": True})

        Status code meaning:

            200 -> request worked
            404 -> this path does not exist on this helper
        """
        parsed = urlparse(self.path)
        if parsed.path == "/health":
            self._send_json(
                200,
                {
                    "alive": True,
                    "rosbridge_url": self.rosbridge_url,
                    "default_topic": self.default_topic,
                    "default_video_topic": self.default_video_topic,
                    "default_arm_topic": self.default_arm_topic,
                },
            )
            return
        if parsed.path == "/video/snapshot":
            query = parse_qs(parsed.query)
            topic = query.get("topic", [self.default_video_topic])[0]
            try:
                image, content_type = self._read_image(topic)
                self._send_bytes(200, image, content_type)
            except Exception as exc:
                self._send_json(502, {"error": "video snapshot failed", "detail": str(exc), "topic": topic})
            return
        if parsed.path == "/video/stream":
            query = parse_qs(parsed.query)
            topic = query.get("topic", [self.default_video_topic])[0]
            try:
                fps = float(query.get("fps", ["10"])[0])
                self._stream_images(topic, max(fps, 0.1))
            except (BrokenPipeError, ConnectionResetError):
                pass
            except Exception as exc:
                self._send_json(502, {"error": "video stream failed", "detail": str(exc), "topic": topic})
            return
        self._send_json(404, {"error": "not found"})

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
            - POST /arm/pose publishes a servo-controller message
            - POST / publishes to `self.default_topic`

        Code pattern:

        Implemented flow:

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
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length) if length else b"{}"
        topic = self.path if self.path != "/" else self.default_topic

        try:
            payload = json.loads(body.decode("utf-8"))
            if topic == "/arm/pose":
                arm_payload = self._coerce_arm_pose(payload)
                self._publish_arm_pose(arm_payload)
                self._send_json(202, {"accepted": True, "topic": self.default_arm_topic, "rosbridge_url": self.rosbridge_url})
                return
            twist = self._coerce_twist(payload)
            self._publish_twist(topic, twist)
            self._send_json(202, {"accepted": True, "topic": topic, "rosbridge_url": self.rosbridge_url})
        except json.JSONDecodeError as exc:
            self._send_json(400, {"error": "invalid JSON body", "detail": str(exc)})
        except ValueError as exc:
            self._send_json(400, {"error": str(exc)})
        except Exception as exc:
            self._send_json(502, {"error": "rosbridge publish failed", "detail": str(exc), "topic": topic})

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

        Code pattern:

        Implemented flow:

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
        try:
            linear = payload["linear"]
            angular = payload["angular"]
            return {
                "linear": {
                    "x": float(linear.get("x", 0.0)),
                    "y": float(linear.get("y", 0.0)),
                    "z": float(linear.get("z", 0.0)),
                },
                "angular": {
                    "x": float(angular.get("x", 0.0)),
                    "y": float(angular.get("y", 0.0)),
                    "z": float(angular.get("z", 0.0)),
                },
            }
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("body must contain numeric geometry_msgs/Twist linear/angular fields") from exc

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

        Code pattern:

        Implemented flow:

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
        ros_topic = topic if topic.startswith("/") else f"/{topic}"
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
        connection = websocket.create_connection(self.rosbridge_url, timeout=self.timeout)
        try:
            connection.send(json.dumps(advertise))
            connection.send(json.dumps(message))
        finally:
            connection.close()

    def _coerce_arm_pose(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Convert an arm-pose request into the servo-controller message shape.

        Expected incoming body from the xApp service:

            {
                "duration": 0.2,
                "position_unit": "pulse",
                "position": [
                    {"id": 1, "position": 500}
                ]
            }

        Concept:

            The servo controller uses `position` as a list of servo targets.
            Each item needs a servo id and a numeric target position.

        Field-read syntax:

            positions = payload.get("position")
            duration = float(payload.get("duration", 0.3))
            position_unit = str(payload.get("position_unit", "pulse"))

        List-building syntax:

            coerced.append({"id": int(item["id"]), "position": float(item["position"])})

        ## TODO
        Complete servo-arm payload coercion.
        """
        raise NotImplementedError("servo arm payload TODO")

    def _publish_arm_pose(self, payload: Dict[str, Any]) -> None:
        """
        Publish one servo-arm message to rosbridge.

        ROS message type:

            servo_controller_msgs/ServosPosition

        rosbridge advertise syntax:

            advertise = {
                "op": "advertise",
                "topic": self.default_arm_topic,
                "type": "servo_controller_msgs/ServosPosition",
            }

        rosbridge publish syntax:

            message = {
                "op": "publish",
                "topic": self.default_arm_topic,
                "msg": payload,
            }

        ## TODO
        Connect to rosbridge, send the advertise message, send the publish
        message, and close the WebSocket connection.
        """
        raise NotImplementedError("servo arm publish TODO")

    def _read_image(self, topic: str) -> Tuple[bytes, str]:
        """
        Read one image message from a ROS image topic through rosbridge.

        Concept:

            A ROS image topic is read by subscribing first, then waiting for a
            publish message.  After one image arrives, the helper should
            unsubscribe and close the WebSocket connection.

        Subscribe message syntax:

            subscribe = {
                "op": "subscribe",
                "topic": ros_topic,
                "queue_length": 1,
                "throttle_rate": 0,
            }

        Completed flow:

            1. Subscribe to `topic`.
            2. Wait for one publish message.
            3. Convert it with `_image_message_to_bytes`.
            4. Unsubscribe and close the connection.
            5. Return `(image, content_type)`.

        Topic cleanup syntax:

            ros_topic = topic if topic.startswith("/") else f"/{topic}"

        Receive-loop syntax:

            message = json.loads(connection.recv())
            if message.get("op") != "publish" or message.get("topic") != ros_topic:
                continue

        Image conversion syntax:

            image = message.get("msg", {})
            frame = self._image_message_to_bytes(image)
            if frame is None:
                raise ValueError("unsupported image message encoding")
            return frame

        Cleanup syntax:

            try:
                connection.send(json.dumps(unsubscribe))
            except Exception:
                pass
            connection.close()
        """
        ros_topic = topic if topic.startswith("/") else f"/{topic}"
        subscribe = {
            "op": "subscribe",
            "topic": ros_topic,
            "queue_length": 1,
            "throttle_rate": 0,
        }
        unsubscribe = {"op": "unsubscribe", "topic": ros_topic}
        connection = websocket.create_connection(self.rosbridge_url, timeout=max(self.timeout, 2.0))
        try:
            connection.send(json.dumps(subscribe))
            while True:
                message = json.loads(connection.recv())
                if message.get("op") != "publish" or message.get("topic") != ros_topic:
                    continue
                image = message.get("msg", {})
                frame = self._image_message_to_bytes(image)
                if frame is None:
                    raise ValueError("unsupported image message encoding")
                return frame
        finally:
            try:
                connection.send(json.dumps(unsubscribe))
            except Exception:
                pass
            connection.close()

    def _stream_images(self, topic: str, fps: float) -> None:
        """
        Stream image messages as multipart HTTP frames.

        Concept:

            A multipart stream keeps the HTTP response open.  Each camera frame
            is written as one part with its own Content-Type and Content-Length.

        Part-writing syntax:

            self.wfile.write(b"--frame\\r\\n")
            self.wfile.write(f"Content-Type: {content_type}\\r\\n".encode("ascii"))
            self.wfile.write(f"Content-Length: {len(image)}\\r\\n\\r\\n".encode("ascii"))
            self.wfile.write(image)
            self.wfile.write(b"\\r\\n")
            self.wfile.flush()

        Completed stream flow:

            1. Send multipart response headers.
            2. Subscribe to the image topic.
            3. Convert each image publish message.
            4. Write one multipart frame for each image.
            5. Unsubscribe and close the WebSocket when the stream ends.

        Stream response headers:

            self.send_response(200)
            self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()

        Subscribe throttle syntax:

            "throttle_rate": int(1000.0 / fps)

        Publish-message check:

            if message.get("op") != "publish" or message.get("topic") != ros_topic:
                continue
        """
        ros_topic = topic if topic.startswith("/") else f"/{topic}"
        subscribe = {
            "op": "subscribe",
            "topic": ros_topic,
            "queue_length": 1,
            "throttle_rate": int(1000.0 / fps),
        }
        unsubscribe = {"op": "unsubscribe", "topic": ros_topic}
        connection = websocket.create_connection(self.rosbridge_url, timeout=max(self.timeout, 2.0))
        self.send_response(200)
        self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        try:
            connection.send(json.dumps(subscribe))
            while True:
                message = json.loads(connection.recv())
                if message.get("op") != "publish" or message.get("topic") != ros_topic:
                    continue
                image = message.get("msg", {})
                frame = self._image_message_to_bytes(image)
                if frame is None:
                    continue
                image_bytes, content_type = frame
                self.wfile.write(b"--frame\r\n")
                self.wfile.write(f"Content-Type: {content_type}\r\n".encode("ascii"))
                self.wfile.write(f"Content-Length: {len(image_bytes)}\r\n\r\n".encode("ascii"))
                self.wfile.write(image_bytes)
                self.wfile.write(b"\r\n")
                self.wfile.flush()
        finally:
            try:
                connection.send(json.dumps(unsubscribe))
            except Exception:
                pass
            connection.close()

    def _image_message_to_bytes(self, image: Dict[str, Any]) -> Optional[Tuple[bytes, str]]:
        """
        Convert ROS image message dictionaries into bytes for HTTP.

        Concept:

            ROS image data may arrive as compressed image bytes or raw pixel
            bytes.  HTTP clients need a recognizable image byte format and a
            matching Content-Type header.

        Common conversions:

            compressed image -> image/jpeg or application/octet-stream
            mono8 raw image  -> image/x-portable-graymap
            rgb8/bgr8 image  -> image/x-portable-pixmap

        Completed conversions:

            compressed image
            mono8 raw image
            rgb8/bgr8 raw image
            rgba8/bgra8 raw image

        Compressed image syntax:

            if "format" in image and "data" in image:
                data = self._decode_ros_binary(image["data"])
                image_format = str(image.get("format", "")).lower()
                content_type = "image/jpeg" if "jpg" in image_format or "jpeg" in image_format else "application/octet-stream"
                return data, content_type

        Raw image fields:

            width = int(image.get("width", 0))
            height = int(image.get("height", 0))
            encoding = str(image.get("encoding", "")).lower()
            data = self._decode_ros_binary(image.get("data", ""))

        PPM/PGM header examples:

            header = f"P5\\n{width} {height}\\n255\\n".encode("ascii")
            header = f"P6\\n{width} {height}\\n255\\n".encode("ascii")
        """
        if "format" in image and "data" in image:
            data = self._decode_ros_binary(image["data"])
            image_format = str(image.get("format", "")).lower()
            content_type = "image/jpeg" if "jpg" in image_format or "jpeg" in image_format else "application/octet-stream"
            return data, content_type

        width = int(image.get("width", 0))
        height = int(image.get("height", 0))
        encoding = str(image.get("encoding", "")).lower()
        data = self._decode_ros_binary(image.get("data", ""))
        if width <= 0 or height <= 0 or not data:
            return None

        if encoding in {"mono8", "8uc1"}:
            expected = width * height
            if len(data) < expected:
                return None
            header = f"P5\n{width} {height}\n255\n".encode("ascii")
            return header + data[:expected], "image/x-portable-graymap"

        if encoding in {"rgb8", "bgr8"}:
            expected = width * height * 3
            if len(data) < expected:
                return None
            pixels = data[:expected]
            if encoding == "bgr8":
                pixels = b"".join(bytes((pixels[i + 2], pixels[i + 1], pixels[i])) for i in range(0, expected, 3))
            header = f"P6\n{width} {height}\n255\n".encode("ascii")
            return header + pixels, "image/x-portable-pixmap"

        if encoding in {"rgba8", "bgra8"}:
            expected = width * height * 4
            if len(data) < expected:
                return None
            pixels = bytearray()
            for index in range(0, expected, 4):
                if encoding == "rgba8":
                    pixels.extend(data[index:index + 3])
                else:
                    pixels.extend((data[index + 2], data[index + 1], data[index]))
            header = f"P6\n{width} {height}\n255\n".encode("ascii")
            return header + bytes(pixels), "image/x-portable-pixmap"

        return None

    @staticmethod
    def _decode_ros_binary(value: Any) -> bytes:
        """
        Decode ROS binary fields.

        Concept:

            rosbridge may represent binary data as a base64 string or as a list
            of numbers.  Both forms need to become Python `bytes`.

        Complete helper:

            Decode base64 strings, numeric lists, and existing bytes.

        Syntax examples:

            base64.b64decode(value)
            bytes(int(item) & 0xFF for item in value)
        """
        if isinstance(value, bytes):
            return value
        if isinstance(value, str):
            return base64.b64decode(value)
        if isinstance(value, list):
            return bytes(int(item) & 0xFF for item in value)
        return b""

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

    def _send_bytes(self, status: int, body: bytes, content_type: str) -> None:
        """
        Send a binary HTTP response.

        Concept:

            Camera snapshots are already bytes.  They should not be wrapped in
            JSON before sending them to the client.

        Header syntax:

            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
        """
        self.send_response(status)
        self.send_header("Content-Type", content_type)
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

    Code pattern:

    Completed arguments:

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
    parser.add_argument("--listen-host", default="0.0.0.0")
    parser.add_argument("--listen-port", type=int, default=8090)
    parser.add_argument("--rosbridge-url", default="ws://10.45.1.3:9090", help="Robot rosbridge URL")
    parser.add_argument("--default-topic", default="/cmd_vel")
    parser.add_argument("--default-video-topic", default="/depth_cam/rgb0/image_raw")
    parser.add_argument("--default-arm-topic", default="/servo_controller")
    parser.add_argument("--timeout", type=float, default=0.5)
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

    Code pattern:

    Implemented flow:

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
    args = parse_args()
    RosbridgeForwarder.rosbridge_url = args.rosbridge_url
    RosbridgeForwarder.default_topic = args.default_topic
    RosbridgeForwarder.default_video_topic = args.default_video_topic
    RosbridgeForwarder.default_arm_topic = args.default_arm_topic
    RosbridgeForwarder.timeout = args.timeout
    server = ThreadingHTTPServer((args.listen_host, args.listen_port), RosbridgeForwarder)
    print(
        f"forwarding http://{args.listen_host}:{args.listen_port} -> {args.rosbridge_url} topic {args.default_topic}",
        flush=True,
    )
    server.serve_forever()


if __name__ == "__main__":
    main()
