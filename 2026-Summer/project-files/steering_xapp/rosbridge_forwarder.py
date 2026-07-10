#!/usr/bin/env python3
"""
HTTP-to-rosbridge forwarder for the ROSOrin command path.

Run this where the robot UE IP is reachable, such as inside or beside the core
network deployment. Expose the listen port with a Kubernetes Service so the xApp
can POST Twist JSON to this helper.
"""

import argparse
import atexit
import base64
import io
import json
import signal
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlencode, urlparse
from urllib.request import Request, urlopen
from typing import Any, Dict, Optional, Tuple

import websocket

try:
    from PIL import Image
except ImportError:
    Image = None


class RosbridgeForwarder(BaseHTTPRequestHandler):
    rosbridge_url = "ws://10.45.1.3:9090"
    web_video_server_url = "http://10.45.1.3:8080"
    video_source = "web_video_server"
    default_topic = "/cmd_vel"
    default_video_topic = "/depth_cam/rgb0/image_raw"
    default_depth_topic = "/depth_cam/depth0/image_raw"
    default_arm_topic = "/servo_controller"
    default_video_width = 320
    default_video_height = 200
    default_jpeg_quality = 60
    rosbridge_fallback_throttle_ms = 83
    timeout = 0.5
    rosbridge_timeout = 3.0
    command_connection = None
    command_lock = threading.Lock()
    advertised_topics = set()
    video_lock = threading.Lock()
    video_subscriptions = []

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/health":
            self._send_json(
                200,
                {
                    "alive": True,
                    "rosbridge_url": self.rosbridge_url,
                    "web_video_server_url": self.web_video_server_url,
                    "video_source": self.video_source,
                    "default_topic": self.default_topic,
                    "default_video_topic": self.default_video_topic,
                    "default_depth_topic": self.default_depth_topic,
                    "default_arm_topic": self.default_arm_topic,
                },
            )
            return
        if parsed.path == "/depth/raw":
            query = parse_qs(parsed.query)
            topic = query.get("topic", [self.default_depth_topic])[0]
            try:
                self._send_json(200, self._read_raw_image(topic))
            except Exception as exc:
                self._send_json(502, {"error": "raw depth read failed", "detail": str(exc), "topic": topic})
            return
        if parsed.path == "/video/snapshot":
            query = parse_qs(parsed.query)
            topic = query.get("topic", [self.default_video_topic])[0]
            if self.video_source == "web_video_server":
                self._proxy_web_video_snapshot(topic, query)
                return
            video_options = self._video_options(query)
            try:
                image, content_type = self._read_image(topic, video_options)
                self._send_bytes(200, image, content_type)
            except Exception as exc:
                self._send_json(502, {"error": "rosbridge image read failed", "detail": str(exc), "topic": topic})
            return
        if parsed.path == "/video/stream":
            query = parse_qs(parsed.query)
            topic = query.get("topic", [self.default_video_topic])[0]
            if self.video_source == "web_video_server":
                self._proxy_web_video_stream(topic, query)
                return
            video_options = self._video_options(query)
            try:
                self._stream_images(topic, video_options)
            except (BrokenPipeError, ConnectionResetError):
                return
            except Exception as exc:
                self._send_json(502, {"error": "rosbridge image stream failed", "detail": str(exc), "topic": topic})
            return
        self._send_json(404, {"error": "not found"})

    def _video_options(self, query: Dict[str, Any]) -> Dict[str, Any]:
        width = self._query_int(query, "width", self.default_video_width)
        height = self._query_int(query, "height", self.default_video_height)
        quality = self._query_int(query, "quality", self.default_jpeg_quality)
        return {
            "width": min(max(width, 1), 1280),
            "height": min(max(height, 1), 720),
            "quality": min(max(quality, 30), 90),
        }

    def _web_video_url(self, path: str, topic: str, query: Dict[str, Any]) -> str:
        base_url = self.web_video_server_url.rstrip("/")
        params = {"topic": topic}
        for key in ("quality", "width", "height"):
            if key in query and query[key]:
                params[key] = query[key][0]
        return f"{base_url}{path}?{urlencode(params, safe='/')}"

    def _proxy_web_video_snapshot(self, topic: str, query: Dict[str, Any]) -> None:
        url = self._web_video_url("/snapshot", topic, query)
        try:
            request = Request(url, headers={"Accept": "image/jpeg,*/*"})
            with urlopen(request, timeout=max(self.rosbridge_timeout, 5.0)) as upstream:
                content_type = upstream.headers.get("Content-Type", "image/jpeg")
                body = upstream.read()
                self._send_bytes(200, body, content_type)
        except Exception as exc:
            self._send_json(
                502,
                {
                    "error": "web video snapshot proxy failed",
                    "detail": str(exc),
                    "topic": topic,
                    "url": url,
                },
            )

    def _proxy_web_video_stream(self, topic: str, query: Dict[str, Any]) -> None:
        url = self._web_video_url("/stream", topic, query)
        headers_sent = False
        try:
            request = Request(url, headers={"Accept": "multipart/x-mixed-replace,*/*"})
            with urlopen(request, timeout=max(self.rosbridge_timeout, 10.0)) as upstream:
                content_type = upstream.headers.get("Content-Type", "multipart/x-mixed-replace;boundary=boundarydonotcross")
                self.send_response(200)
                self.send_header("Content-Type", content_type)
                self.send_header("Cache-Control", "no-cache")
                self.end_headers()
                headers_sent = True
                while True:
                    chunk = upstream.read(65536)
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            return
        except Exception as exc:
            if headers_sent:
                print(f"web video stream ended: {exc}", flush=True)
                return
            self._send_json(
                502,
                {
                    "error": "web video stream proxy failed",
                    "detail": str(exc),
                    "topic": topic,
                    "url": url,
                },
            )

    @staticmethod
    def _query_int(query: Dict[str, Any], key: str, default: int) -> int:
        try:
            return int(float(query.get(key, [str(default)])[0]))
        except (TypeError, ValueError):
            return default

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

    @classmethod
    def _close_command_connection(cls) -> None:
        if cls.command_connection is not None:
            try:
                cls.command_connection.close()
            except Exception:
                pass
        cls.command_connection = None
        cls.advertised_topics.clear()

    @classmethod
    def register_video_subscription(cls, connection: Any, topic: str) -> None:
        with cls.video_lock:
            cls.video_subscriptions.append((connection, topic))

    @classmethod
    def unregister_video_subscription(cls, connection: Any, topic: str) -> None:
        with cls.video_lock:
            cls.video_subscriptions = [
                item for item in cls.video_subscriptions
                if not (item[0] is connection and item[1] == topic)
            ]

    @classmethod
    def unsubscribe_video_connection(cls, connection: Any, topic: str) -> None:
        try:
            connection.send(json.dumps({"op": "unsubscribe", "topic": topic}))
        except Exception:
            pass
        try:
            connection.close()
        except Exception:
            pass

    @classmethod
    def cleanup_all(cls) -> None:
        cls._close_command_connection()
        with cls.video_lock:
            subscriptions = list(cls.video_subscriptions)
            cls.video_subscriptions.clear()
        for connection, topic in subscriptions:
            cls.unsubscribe_video_connection(connection, topic)

    def _read_image(self, topic: str, video_options: Dict[str, Any]) -> Tuple[bytes, str]:
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
            type(self).register_video_subscription(connection, ros_topic)
            while True:
                message = json.loads(connection.recv())
                if message.get("op") != "publish" or message.get("topic") != ros_topic:
                    continue
                image = message.get("msg", {})
                frame = self._image_message_to_bytes(image, video_options)
                if frame is None:
                    raise ValueError("unsupported image message encoding")
                return frame
        finally:
            type(self).unregister_video_subscription(connection, ros_topic)
            type(self).unsubscribe_video_connection(connection, ros_topic)

    def _stream_images(self, topic: str, video_options: Dict[str, Any]) -> None:
        ros_topic = topic if topic.startswith("/") else f"/{topic}"
        subscribe = {
            "op": "subscribe",
            "topic": ros_topic,
            "queue_length": 1,
            "throttle_rate": self.rosbridge_fallback_throttle_ms,
        }
        unsubscribe = {"op": "unsubscribe", "topic": ros_topic}
        connection = websocket.create_connection(self.rosbridge_url, timeout=max(self.rosbridge_timeout, 10.0))
        self.send_response(200)
        self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()

        try:
            connection.send(json.dumps(subscribe))
            type(self).register_video_subscription(connection, ros_topic)
            while True:
                message = json.loads(connection.recv())
                if message.get("op") != "publish" or message.get("topic") != ros_topic:
                    continue
                frame = self._image_message_to_bytes(message.get("msg", {}), video_options)
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
            type(self).unregister_video_subscription(connection, ros_topic)
            type(self).unsubscribe_video_connection(connection, ros_topic)

    def _read_raw_image(self, topic: str) -> Dict[str, Any]:
        ros_topic = topic if topic.startswith("/") else f"/{topic}"
        subscribe = {
            "op": "subscribe",
            "topic": ros_topic,
            "queue_length": 1,
            "throttle_rate": 0,
        }
        connection = websocket.create_connection(self.rosbridge_url, timeout=max(self.rosbridge_timeout, 10.0))
        try:
            connection.send(json.dumps(subscribe))
            type(self).register_video_subscription(connection, ros_topic)
            while True:
                message = json.loads(connection.recv())
                if message.get("op") != "publish" or message.get("topic") != ros_topic:
                    continue
                image = message.get("msg", {})
                data = self._decode_ros_binary(image.get("data", ""))
                return {
                    "topic": ros_topic,
                    "height": int(image.get("height", 0)),
                    "width": int(image.get("width", 0)),
                    "encoding": str(image.get("encoding", "")),
                    "is_bigendian": int(image.get("is_bigendian", 0)),
                    "step": int(image.get("step", 0)),
                    "data": base64.b64encode(data).decode("ascii"),
                }
        finally:
            type(self).unregister_video_subscription(connection, ros_topic)
            type(self).unsubscribe_video_connection(connection, ros_topic)

    def _image_message_to_bytes(self, image: Dict[str, Any], video_options: Optional[Dict[str, Any]] = None) -> Optional[Tuple[bytes, str]]:
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
            rows = [data[row * step: row * step + width] for row in range(height)]
            pixels = b"".join(rows)
            jpeg = self._jpeg_bytes("L", width, height, pixels, video_options)
            if jpeg is not None:
                return jpeg, "image/jpeg"
            header = f"P5\n{width} {height}\n255\n".encode("ascii")
            return header + pixels, "image/x-portable-graymap"

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
        jpeg = self._jpeg_bytes("RGB", width, height, bytes(pixels), video_options)
        if jpeg is not None:
            return jpeg, "image/jpeg"
        header = f"P6\n{width} {height}\n255\n".encode("ascii")
        return header + bytes(pixels), "image/x-portable-pixmap"

    def _jpeg_bytes(self, mode: str, width: int, height: int, pixels: bytes, video_options: Optional[Dict[str, Any]]) -> Optional[bytes]:
        if Image is None:
            return None
        options = video_options or {
            "width": self.default_video_width,
            "height": self.default_video_height,
            "quality": self.default_jpeg_quality,
        }
        image = Image.frombytes(mode, (width, height), pixels)
        if mode != "RGB":
            image = image.convert("RGB")
        target = (int(options["width"]), int(options["height"]))
        if target[0] > 0 and target[1] > 0 and image.size != target:
            resample = getattr(getattr(Image, "Resampling", Image), "BILINEAR")
            image.thumbnail(target, resample)
        buffer = io.BytesIO()
        image.save(buffer, format="JPEG", quality=int(options["quality"]), optimize=False)
        return buffer.getvalue()

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


class ForwarderHTTPServer(ThreadingHTTPServer):
    daemon_threads = True


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Forward HTTP Twist commands to ROS rosbridge")
    parser.add_argument("--listen-host", default="0.0.0.0")
    parser.add_argument("--listen-port", type=int, default=8090)
    parser.add_argument("--rosbridge-url", default="ws://10.45.1.3:9090", help="Robot rosbridge URL")
    parser.add_argument("--web-video-server-url", default="http://10.45.1.3:8080", help="Robot web_video_server base URL")
    parser.add_argument(
        "--video-source",
        choices=("web_video_server", "rosbridge"),
        default="web_video_server",
        help="Use robot web_video_server for video by default; rosbridge is a raw-image fallback",
    )
    parser.add_argument("--default-topic", default="/cmd_vel")
    parser.add_argument("--default-video-topic", default="/depth_cam/rgb0/image_raw")
    parser.add_argument("--default-depth-topic", default="/depth_cam/depth0/image_raw")
    parser.add_argument("--default-arm-topic", default="/servo_controller")
    parser.add_argument("--default-video-width", type=int, default=320)
    parser.add_argument("--default-video-height", type=int, default=200)
    parser.add_argument("--default-jpeg-quality", type=int, default=60)
    parser.add_argument("--timeout", type=float, default=0.5)
    parser.add_argument("--rosbridge-timeout", type=float, default=3.0)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    RosbridgeForwarder.rosbridge_url = args.rosbridge_url
    RosbridgeForwarder.web_video_server_url = args.web_video_server_url
    RosbridgeForwarder.video_source = args.video_source
    RosbridgeForwarder.default_topic = args.default_topic
    RosbridgeForwarder.default_video_topic = args.default_video_topic
    RosbridgeForwarder.default_depth_topic = args.default_depth_topic
    RosbridgeForwarder.default_arm_topic = args.default_arm_topic
    RosbridgeForwarder.default_video_width = args.default_video_width
    RosbridgeForwarder.default_video_height = args.default_video_height
    RosbridgeForwarder.default_jpeg_quality = args.default_jpeg_quality
    RosbridgeForwarder.timeout = args.timeout
    RosbridgeForwarder.rosbridge_timeout = args.rosbridge_timeout
    atexit.register(RosbridgeForwarder.cleanup_all)
    server = ForwarderHTTPServer((args.listen_host, args.listen_port), RosbridgeForwarder)

    def shutdown(_signum: int, _frame: Any) -> None:
        RosbridgeForwarder.cleanup_all()
        raise KeyboardInterrupt

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)
    print(
        f"forwarding http://{args.listen_host}:{args.listen_port} -> {args.rosbridge_url} topic {args.default_topic}; "
        f"video_source={args.video_source} web_video_server={args.web_video_server_url}",
        flush=True,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("stopping rosbridge forwarder", flush=True)
    finally:
        RosbridgeForwarder.cleanup_all()
        server.server_close()


if __name__ == "__main__":
    main()
