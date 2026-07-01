#!/usr/bin/env python3

import json
import threading
import time
from dataclasses import dataclass
from math import isfinite
from typing import Any, Dict, List, Optional, Tuple

import requests


DEFAULT_ROBOT_BASE_URL = "http://10.233.56.235:8090"
DEFAULT_ROBOT_PAYLOAD_FORMAT = "ros_twist"
DEFAULT_ROBOT_MAX_LINEAR_MPS = 0.2
DEFAULT_ROBOT_MAX_ANGULAR_RADPS = 0.5
DEFAULT_ROBOT_TIMEOUT_SECONDS = 4.0
DEFAULT_ARM_POSITIONS = {1: 500, 2: 725, 3: 50, 4: 150, 5: 500, 10: 500}
DEFAULT_ARM_LIMITS = {
    1: (100, 1000),
    2: (100, 765),
    3: (0, 468),
    4: (88, 654),
    5: (125, 700),
    10: (200, 700),
}


def now_ms() -> int:
    return int(time.time() * 1000)


def format_timestamp_date(timestamp_ms: int) -> str:
    dt = time.localtime(timestamp_ms / 1000.0)
    return f"{dt.tm_mon}/{dt.tm_mday:02d}/{dt.tm_year}"


@dataclass
class CommandLimits:
    steering_min: float = -1.0
    steering_max: float = 1.0
    throttle_min: float = 0.0
    throttle_max: float = 1.0
    brake_min: float = 0.0
    brake_max: float = 1.0
    clamp_inputs: bool = True
    command_rate_hz: float = 20.0
    deadman_timeout_ms: int = 500


@dataclass
class RobotTarget:
    base_url: str = DEFAULT_ROBOT_BASE_URL
    command_path: str = "/cmd_vel"
    stop_path: str = "/cmd_vel"
    video_snapshot_path: str = "/video/snapshot"
    video_stream_path: str = "/video/stream"
    arm_pose_path: str = "/arm/pose"
    timeout_seconds: float = DEFAULT_ROBOT_TIMEOUT_SECONDS
    payload_format: str = DEFAULT_ROBOT_PAYLOAD_FORMAT
    max_linear_mps: float = DEFAULT_ROBOT_MAX_LINEAR_MPS
    max_angular_radps: float = DEFAULT_ROBOT_MAX_ANGULAR_RADPS


@dataclass
class SteeringState:
    last_command: Optional[Dict[str, Any]] = None
    last_mapped_payload: Optional[Dict[str, Any]] = None
    last_robot_status: Optional[Dict[str, Any]] = None
    last_accept_ms: Optional[int] = None
    last_forward_ms: Optional[int] = None
    last_seq: Optional[int] = None
    command_count: int = 0
    rejected_count: int = 0
    stop_count: int = 0
    deadman_triggered: bool = False
    stopped: bool = True
    last_error: Optional[str] = None


@dataclass
class ArmState:
    positions: Dict[int, int]
    last_robot_status: Optional[Dict[str, Any]] = None
    last_command_ms: Optional[int] = None
    command_count: int = 0
    last_error: Optional[str] = None


class SteeringCommandService:
    def __init__(self, config: Dict[str, Any], logger: Any = None) -> None:
        self.logger = logger
        self.lock = threading.Lock()
        self.state = SteeringState()
        self.arm_state = ArmState(positions=DEFAULT_ARM_POSITIONS.copy())
        self.deadman_thread: Optional[threading.Thread] = None
        self.keep_running = False
        self.apply_config(config)

    def apply_config(self, config: Dict[str, Any]) -> None:
        controls = config.get("controls", {})
        bounds = controls.get("bounds", {})
        robot = controls.get("robot", {})

        self.limits = CommandLimits(
            steering_min=float(bounds.get("steeringMin", -1.0)),
            steering_max=float(bounds.get("steeringMax", 1.0)),
            throttle_min=float(bounds.get("throttleMin", 0.0)),
            throttle_max=float(bounds.get("throttleMax", 1.0)),
            brake_min=float(bounds.get("brakeMin", 0.0)),
            brake_max=float(bounds.get("brakeMax", 1.0)),
            clamp_inputs=bool(bounds.get("clampInputs", True)),
            command_rate_hz=float(controls.get("commandRateHz", 20.0)),
            deadman_timeout_ms=int(controls.get("deadmanTimeoutMs", 500)),
        )
        self.robot = RobotTarget(
            base_url=str(robot.get("baseUrl", DEFAULT_ROBOT_BASE_URL)).rstrip("/"),
            command_path=str(robot.get("commandPath", "/cmd_vel")),
            stop_path=str(robot.get("stopPath", robot.get("commandPath", "/cmd_vel"))),
            video_snapshot_path=str(robot.get("videoSnapshotPath", "/video/snapshot")),
            video_stream_path=str(robot.get("videoStreamPath", "/video/stream")),
            arm_pose_path=str(robot.get("armPosePath", "/arm/pose")),
            timeout_seconds=float(robot.get("timeoutSeconds", DEFAULT_ROBOT_TIMEOUT_SECONDS)),
            payload_format=str(robot.get("payloadFormat", DEFAULT_ROBOT_PAYLOAD_FORMAT)),
            max_linear_mps=float(robot.get("maxLinearMps", DEFAULT_ROBOT_MAX_LINEAR_MPS)),
            max_angular_radps=float(robot.get("maxAngularRadps", DEFAULT_ROBOT_MAX_ANGULAR_RADPS)),
        )

    def start_deadman(self) -> None:
        self.keep_running = True
        self.deadman_thread = threading.Thread(target=self._deadman_loop, daemon=True)
        self.deadman_thread.start()

    def stop_deadman(self) -> None:
        self.keep_running = False
        if self.deadman_thread is not None:
            self.deadman_thread.join(timeout=1.0)

    def submit(self, body: Dict[str, Any]) -> Tuple[int, Dict[str, Any]]:
        received_ms = now_ms()
        valid, payload_or_error = self._validate_and_normalize(body, received_ms)
        if not valid:
            with self.lock:
                self.state.rejected_count += 1
                self.state.last_error = payload_or_error["error"]
            return 400, payload_or_error

        command = payload_or_error
        with self.lock:
            rate_status = self._check_rate_limit_locked(received_ms)
            if rate_status is not None:
                self.state.rejected_count += 1
                self.state.last_error = rate_status["error"]
                return 429, rate_status

            mapped_payload = self._map_robot_payload(command, stop=False)
            self.state.last_command = command
            self.state.last_mapped_payload = mapped_payload
            self.state.last_accept_ms = received_ms
            self.state.last_seq = command.get("seq")
            self.state.command_count += 1
            self.state.deadman_triggered = False
            self.state.stopped = not command.get("enable", True)

        if self.logger is not None:
            self.logger.info(
                f"accepted steering command seq={command.get('seq')} "
                f"timestamp_date={command.get('timestamp_date')}"
            )

        robot_status = self._send_to_robot(mapped_payload, self.robot.command_path)
        with self.lock:
            self.state.last_forward_ms = now_ms()
            self.state.last_robot_status = robot_status
            if robot_status.get("ok"):
                self.state.last_error = None
            else:
                self.state.last_error = robot_status.get("error")

        return 202, {"accepted": True, "command": command, "mapped": mapped_payload, "robot": robot_status}

    def stop(self, reason: str = "operator") -> Tuple[int, Dict[str, Any]]:
        stop_command = {
            "seq": None,
            "timestamp_ms": now_ms(),
            "steering": 0.0,
            "throttle": 0.0,
            "brake": 1.0,
            "enable": False,
            "reason": reason,
        }
        stop_command["timestamp_date"] = format_timestamp_date(stop_command["timestamp_ms"])
        mapped_payload = self._map_robot_payload(stop_command, stop=True)
        robot_status = self._send_to_robot(mapped_payload, self.robot.stop_path)
        with self.lock:
            self.state.last_command = stop_command
            self.state.last_mapped_payload = mapped_payload
            self.state.last_robot_status = robot_status
            self.state.last_forward_ms = now_ms()
            self.state.stop_count += 1
            self.state.stopped = True
            self.state.last_error = None if robot_status.get("ok") else robot_status.get("error")
        if self.logger is not None:
            self.logger.info(f"stop command reason={reason} timestamp_date={stop_command.get('timestamp_date')}")
        return 202, {"stopped": True, "reason": reason, "command": stop_command, "mapped": mapped_payload, "robot": robot_status}

    def snapshot(self) -> Dict[str, Any]:
        with self.lock:
            return {
                "limits": self.limits.__dict__,
                "robot": self.robot.__dict__,
                "state": self.state.__dict__.copy(),
            }

    def submit_arm_pose(self, body: Dict[str, Any]) -> Tuple[int, Dict[str, Any]]:
        valid, payload_or_error = self._validate_arm_pose(body)
        if not valid:
            return 400, payload_or_error

        robot_status = self._post_to_robot(payload_or_error["mapped"], self.robot.arm_pose_path)
        with self.lock:
            self.arm_state.positions.update(payload_or_error["positions"])
            self.arm_state.last_robot_status = robot_status
            self.arm_state.last_command_ms = now_ms()
            self.arm_state.command_count += 1
            self.arm_state.last_error = None if robot_status.get("ok") else robot_status.get("error")
        if self.logger is not None:
            self.logger.info(f"arm command positions={payload_or_error['positions']}")
        return 202, {"accepted": True, "arm": self.arm_snapshot(), "mapped": payload_or_error["mapped"], "robot": robot_status}

    def arm_snapshot(self) -> Dict[str, Any]:
        with self.lock:
            return {
                "positions": self.arm_state.positions.copy(),
                "limits": {str(k): {"min": v[0], "max": v[1]} for k, v in DEFAULT_ARM_LIMITS.items()},
                "defaults": DEFAULT_ARM_POSITIONS.copy(),
                "state": {
                    "last_robot_status": self.arm_state.last_robot_status,
                    "last_command_ms": self.arm_state.last_command_ms,
                    "command_count": self.arm_state.command_count,
                    "last_error": self.arm_state.last_error,
                },
            }

    def _validate_arm_pose(self, body: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
        positions = body.get("positions", body.get("position"))
        if not isinstance(positions, list):
            return False, {"error": "body must contain positions list"}
        try:
            duration = float(body.get("duration", 0.3))
        except (TypeError, ValueError):
            return False, {"error": "duration must be numeric"}
        duration = min(max(duration, 0.02), 30.0)

        normalized: Dict[int, int] = {}
        clamped: List[int] = []
        for item in positions:
            try:
                servo_id = int(item["id"])
                value = int(round(float(item["position"])))
            except (KeyError, TypeError, ValueError):
                return False, {"error": "each position must contain numeric id and position"}
            if servo_id not in DEFAULT_ARM_LIMITS:
                return False, {"error": "unsupported arm servo id", "id": servo_id}
            lower, upper = DEFAULT_ARM_LIMITS[servo_id]
            bounded = min(max(value, lower), upper)
            if bounded != value:
                clamped.append(servo_id)
            normalized[servo_id] = bounded

        mapped = {
            "duration": duration,
            "position_unit": "pulse",
            "position": [{"id": servo_id, "position": value} for servo_id, value in sorted(normalized.items())],
        }
        result = {"positions": normalized, "mapped": mapped}
        if clamped:
            result["clamped"] = clamped
        return True, result

    def video_snapshot(self) -> Tuple[int, bytes, str]:
        if not self.robot.base_url:
            body = json.dumps({"error": "robot baseUrl is not configured"}, sort_keys=True).encode("utf-8")
            return 503, body, "application/json"

        path = self.robot.video_snapshot_path
        url = f"{self.robot.base_url}{path if path.startswith('/') else '/' + path}"
        try:
            response = requests.get(url, timeout=max(self.robot.timeout_seconds, 2.0))
            content_type = response.headers.get("Content-Type", "application/octet-stream")
            return response.status_code, response.content, content_type
        except requests.RequestException as exc:
            if self.logger is not None:
                self.logger.error(f"robot video snapshot GET failed: {exc}")
            body = json.dumps({"error": "robot video snapshot failed", "detail": str(exc), "url": url}, sort_keys=True).encode("utf-8")
            return 502, body, "application/json"

    def video_stream_url(self, query: str = "") -> str:
        path = self.robot.video_stream_path
        url = f"{self.robot.base_url}{path if path.startswith('/') else '/' + path}"
        return f"{url}?{query}" if query else url

    def _validate_and_normalize(self, body: Dict[str, Any], received_ms: int) -> Tuple[bool, Dict[str, Any]]:
        required = ("seq", "timestamp_ms", "steering", "throttle", "brake", "enable")
        missing = [key for key in required if key not in body]
        if missing:
            return False, {"error": "missing required field(s)", "fields": missing}

        if not isinstance(body["enable"], bool):
            return False, {"error": "enable must be a JSON boolean"}

        try:
            command = {
                "seq": int(body["seq"]),
                "timestamp_ms": int(body["timestamp_ms"]),
                "steering": float(body["steering"]),
                "throttle": float(body["throttle"]),
                "brake": float(body["brake"]),
                "enable": body["enable"],
            }
        except (TypeError, ValueError):
            return False, {"error": "seq/timestamp must be integers and command values must be numeric"}

        if not all(isfinite(command[key]) for key in ("steering", "throttle", "brake")):
            return False, {"error": "command values must be finite numbers"}

        command["timestamp_date"] = format_timestamp_date(command["timestamp_ms"])

        for key, lower, upper in (
            ("steering", self.limits.steering_min, self.limits.steering_max),
            ("throttle", self.limits.throttle_min, self.limits.throttle_max),
            ("brake", self.limits.brake_min, self.limits.brake_max),
        ):
            value = command[key]
            if lower <= value <= upper:
                continue
            if not self.limits.clamp_inputs:
                return False, {"error": "command value outside configured bounds", "field": key, "value": value}
            command[key] = min(max(value, lower), upper)
            command.setdefault("clamped", []).append(key)

        return True, command

    def _check_rate_limit_locked(self, received_ms: int) -> Optional[Dict[str, Any]]:
        if self.limits.command_rate_hz <= 0 or self.state.last_accept_ms is None:
            return None
        min_interval_ms = int(1000 / self.limits.command_rate_hz)
        elapsed_ms = received_ms - self.state.last_accept_ms
        if elapsed_ms < min_interval_ms:
            return {"error": "command rate limit exceeded", "retry_after_ms": min_interval_ms - elapsed_ms}
        return None

    def _map_robot_payload(self, command: Dict[str, Any], stop: bool) -> Dict[str, Any]:
        if self.robot.payload_format in ("ros_twist", "rosorin_twist", "rosbridge_twist"):
            linear_x = 0.0 if stop or not command["enable"] else (command["throttle"] - command["brake"])
            angular_z = 0.0 if stop or not command["enable"] else -command["steering"]
            twist = {
                "linear": {"x": linear_x * self.robot.max_linear_mps, "y": 0.0, "z": 0.0},
                "angular": {"x": 0.0, "y": 0.0, "z": angular_z * self.robot.max_angular_radps},
            }
            if self.robot.payload_format != "rosbridge_twist":
                twist["enable"] = command["enable"] and not stop
            return twist
        return {
            "seq": command.get("seq"),
            "timestamp_ms": command["timestamp_ms"],
            "timestamp_date": command.get("timestamp_date"),
            "steering": 0.0 if stop else command["steering"],
            "throttle": 0.0 if stop else command["throttle"],
            "brake": 1.0 if stop else command["brake"],
            "enable": command["enable"] and not stop,
        }

    def _send_to_robot(self, payload: Dict[str, Any], path: str) -> Dict[str, Any]:
        if not self.robot.base_url:
            return {"ok": True, "skipped": True, "reason": "robot baseUrl is not configured"}
        if self.robot.payload_format == "rosbridge_twist" or self.robot.base_url.startswith(("ws://", "wss://")):
            return self._publish_to_rosbridge(payload, path)
        return self._post_to_robot(payload, path)

    def _post_to_robot(self, payload: Dict[str, Any], path: str) -> Dict[str, Any]:
        url = f"{self.robot.base_url}{path if path.startswith('/') else '/' + path}"
        try:
            response = requests.post(url, json=payload, timeout=self.robot.timeout_seconds)
            return {
                "ok": 200 <= response.status_code < 300,
                "status_code": response.status_code,
                "url": url,
                "body": response.text[:256],
            }
        except requests.RequestException as exc:
            if self.logger is not None:
                self.logger.error(f"robot command POST failed: {exc}")
            return {"ok": False, "url": url, "error": str(exc)}

    def _publish_to_rosbridge(self, payload: Dict[str, Any], topic: str) -> Dict[str, Any]:
        try:
            import websocket

            ws_url = self._rosbridge_url()
            ros_topic = topic if topic.startswith("/") else f"/{topic}"
            advertise = {
                "op": "advertise",
                "topic": ros_topic,
                "type": "geometry_msgs/Twist",
            }
            message = {
                "op": "publish",
                "topic": ros_topic,
                "msg": payload,
            }
            connection = websocket.create_connection(ws_url, timeout=self.robot.timeout_seconds)
            try:
                connection.send(json.dumps(advertise))
                connection.send(json.dumps(message))
            finally:
                connection.close()
            return {"ok": True, "url": ws_url, "topic": message["topic"], "protocol": "rosbridge_websocket"}
        except Exception as exc:
            if self.logger is not None:
                self.logger.error(f"rosbridge publish failed: {exc}")
            return {"ok": False, "url": self._rosbridge_url(), "topic": topic, "error": str(exc)}

    def _rosbridge_url(self) -> str:
        if self.robot.base_url.startswith(("ws://", "wss://")):
            return self.robot.base_url
        if self.robot.base_url.startswith("https://"):
            return "wss://" + self.robot.base_url[len("https://"):]
        if self.robot.base_url.startswith("http://"):
            return "ws://" + self.robot.base_url[len("http://"):]
        return self.robot.base_url

    def _deadman_loop(self) -> None:
        while self.keep_running:
            time.sleep(max(self.limits.deadman_timeout_ms / 3000.0, 0.05))
            should_stop = False
            with self.lock:
                if self.state.stopped or self.state.last_accept_ms is None:
                    continue
                elapsed_ms = now_ms() - self.state.last_accept_ms
                if elapsed_ms >= self.limits.deadman_timeout_ms:
                    self.state.deadman_triggered = True
                    should_stop = True
            if should_stop:
                self.stop(reason="deadman_timeout")
