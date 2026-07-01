#!/usr/bin/env python3
"""
HTTP-to-rosbridge forwarder for the ROSOrin command path.

Run this where the robot UE IP is reachable, such as inside or beside the core
network deployment. Expose the listen port with a Kubernetes Service so the xApp
can POST Twist JSON to this helper.
"""

import argparse
import base64
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse
from typing import Any, Dict, Optional, Tuple

import websocket


class RosbridgeForwarder(BaseHTTPRequestHandler):
    rosbridge_url = "ws://10.45.1.3:9090"
    default_topic = "/cmd_vel"
    default_video_topic = "/depth_cam/rgb0/image_raw"
    default_arm_topic = "/servo_controller"
    timeout = 0.5
    rosbridge_timeout = 3.0
    command_connection = None
    command_lock = threading.Lock()
    advertised_topics = set()

    def do_GET(self) -> None:
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
                self._send_json(502, {"error": "rosbridge image read failed", "detail": str(exc), "topic": topic})
            return
        if parsed.path == "/video/stream":
            query = parse_qs(parsed.query)
            topic = query.get("topic", [self.default_video_topic])[0]
            try:
                fps = float(query.get("fps", ["4"])[0])
            except ValueError:
                fps = 4.0
            try:
                self._stream_images(topic, fps=min(max(fps, 1.0), 8.0))
            except (BrokenPipeError, ConnectionResetError):
                return
            except Exception as exc:
                self._send_json(502, {"error": "rosbridge image stream failed", "detail": str(exc), "topic": topic})
            return
        self._send_json(404, {"error": "not found"})

    def do_POST(self) -> None:
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
        print("%s - %s" % (self.address_string(), fmt % args), flush=True)

    def _coerce_twist(self, payload: Dict[str, Any]) -> Dict[str, Dict[str, float]]:
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
        self._publish_command_messages(ros_topic, advertise, message)

    def _coerce_arm_pose(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        positions = payload.get("position")
        if not isinstance(positions, list):
            raise ValueError("body must contain a position list")
        coerced = []
        for item in positions:
            try:
                coerced.append({"id": int(item["id"]), "position": float(item["position"])})
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError("each arm position must contain numeric id and position") from exc
        return {
            "duration": float(payload.get("duration", 0.3)),
            "position_unit": str(payload.get("position_unit", "pulse")),
            "position": coerced,
        }

    def _publish_arm_pose(self, payload: Dict[str, Any]) -> None:
        advertise = {
            "op": "advertise",
            "topic": self.default_arm_topic,
            "type": "servo_controller_msgs/ServosPosition",
        }
        message = {
            "op": "publish",
            "topic": self.default_arm_topic,
            "msg": payload,
        }
        self._publish_command_messages(self.default_arm_topic, advertise, message)

    def _publish_command_messages(self, topic: str, advertise: Dict[str, Any], message: Dict[str, Any]) -> None:
        with self.command_lock:
            try:
                self._send_command_messages(topic, advertise, message)
            except Exception:
                self._close_command_connection()
                self._send_command_messages(topic, advertise, message)

    def _send_command_messages(self, topic: str, advertise: Dict[str, Any], message: Dict[str, Any]) -> None:
        connection = self._command_connection()
        cls = type(self)
        if topic not in cls.advertised_topics:
            connection.send(json.dumps(advertise))
            cls.advertised_topics.add(topic)
        connection.send(json.dumps(message))

    def _command_connection(self) -> Any:
        cls = type(self)
        if cls.command_connection is None:
            cls.command_connection = websocket.create_connection(self.rosbridge_url, timeout=self.rosbridge_timeout)
            cls.command_connection.settimeout(self.rosbridge_timeout)
        return cls.command_connection

    def _close_command_connection(self) -> None:
        cls = type(self)
        if cls.command_connection is not None:
            try:
                cls.command_connection.close()
            except Exception:
                pass
        cls.command_connection = None
        cls.advertised_topics.clear()

    def _read_image(self, topic: str) -> Tuple[bytes, str]:
        ros_topic = topic if topic.startswith("/") else f"/{topic}"
        subscribe = {
            "op": "subscribe",
            "topic": ros_topic,
            "queue_length": 1,
            "throttle_rate": 0,
        }
        unsubscribe = {"op": "unsubscribe", "topic": ros_topic}
        connection = websocket.create_connection(self.rosbridge_url, timeout=max(self.rosbridge_timeout, 10.0))
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
        ros_topic = topic if topic.startswith("/") else f"/{topic}"
        subscribe = {
            "op": "subscribe",
            "topic": ros_topic,
            "queue_length": 1,
            "throttle_rate": int(1000.0 / fps),
        }
        unsubscribe = {"op": "unsubscribe", "topic": ros_topic}
        connection = websocket.create_connection(self.rosbridge_url, timeout=max(self.rosbridge_timeout, 10.0))
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
                frame = self._image_message_to_bytes(message.get("msg", {}))
                if frame is None:
                    continue
                image, content_type = frame
                self.wfile.write(b"--frame\r\n")
                self.wfile.write(f"Content-Type: {content_type}\r\n".encode("ascii"))
                self.wfile.write(f"Content-Length: {len(image)}\r\n\r\n".encode("ascii"))
                self.wfile.write(image)
                self.wfile.write(b"\r\n")
                self.wfile.flush()
        finally:
            try:
                connection.send(json.dumps(unsubscribe))
            except Exception:
                pass
            connection.close()

    def _image_message_to_bytes(self, image: Dict[str, Any]) -> Optional[Tuple[bytes, str]]:
        if "format" in image and "data" in image:
            data = self._decode_ros_binary(image["data"])
            image_format = str(image.get("format", "")).lower()
            content_type = "image/jpeg" if "jpg" in image_format or "jpeg" in image_format else "application/octet-stream"
            return data, content_type

        width = int(image.get("width", 0))
        height = int(image.get("height", 0))
        encoding = str(image.get("encoding", "")).lower()
        data = self._decode_ros_binary(image.get("data", ""))
        if width <= 0 or height <= 0:
            return None
        if encoding not in ("rgb8", "bgr8", "rgba8", "bgra8", "mono8"):
            return None

        if encoding == "mono8":
            step = int(image.get("step", width))
            header = f"P5\n{width} {height}\n255\n".encode("ascii")
            rows = [data[row * step: row * step + width] for row in range(height)]
            return header + b"".join(rows), "image/x-portable-graymap"

        channels = 4 if encoding in ("rgba8", "bgra8") else 3
        row_bytes = width * channels
        step = int(image.get("step", row_bytes))
        pixels = bytearray()
        for row in range(height):
            raw_row = data[row * step: row * step + row_bytes]
            for col in range(0, len(raw_row), channels):
                pixel = raw_row[col: col + channels]
                if len(pixel) < channels:
                    continue
                if encoding.startswith("bgr"):
                    pixels.extend((pixel[2], pixel[1], pixel[0]))
                else:
                    pixels.extend((pixel[0], pixel[1], pixel[2]))
        header = f"P6\n{width} {height}\n255\n".encode("ascii")
        return header + bytes(pixels), "image/x-portable-pixmap"

    @staticmethod
    def _decode_ros_binary(value: Any) -> bytes:
        if isinstance(value, str):
            return base64.b64decode(value)
        if isinstance(value, list):
            return bytes(int(item) & 0xFF for item in value)
        if isinstance(value, bytes):
            return value
        return b""

    def _send_json(self, status: int, payload: Dict[str, Any]) -> None:
        body = json.dumps(payload, sort_keys=True).encode("utf-8")
        self._send_bytes(status, body, "application/json")

    def _send_bytes(self, status: int, body: bytes, content_type: str) -> None:
        try:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            print("client disconnected before response was sent", flush=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Forward HTTP Twist commands to ROS rosbridge")
    parser.add_argument("--listen-host", default="0.0.0.0")
    parser.add_argument("--listen-port", type=int, default=8090)
    parser.add_argument("--rosbridge-url", default="ws://10.45.1.3:9090", help="Robot rosbridge URL")
    parser.add_argument("--default-topic", default="/cmd_vel")
    parser.add_argument("--default-video-topic", default="/depth_cam/rgb0/image_raw")
    parser.add_argument("--default-arm-topic", default="/servo_controller")
    parser.add_argument("--timeout", type=float, default=0.5)
    parser.add_argument("--rosbridge-timeout", type=float, default=3.0)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    RosbridgeForwarder.rosbridge_url = args.rosbridge_url
    RosbridgeForwarder.default_topic = args.default_topic
    RosbridgeForwarder.default_video_topic = args.default_video_topic
    RosbridgeForwarder.default_arm_topic = args.default_arm_topic
    RosbridgeForwarder.timeout = args.timeout
    RosbridgeForwarder.rosbridge_timeout = args.rosbridge_timeout
    server = ThreadingHTTPServer((args.listen_host, args.listen_port), RosbridgeForwarder)
    print(
        f"forwarding http://{args.listen_host}:{args.listen_port} -> {args.rosbridge_url} topic {args.default_topic}",
        flush=True,
    )
    server.serve_forever()


if __name__ == "__main__":
    main()
