#!/usr/bin/env python3
"""
Steering command service.

This module owns the command logic for the steering-wheel xApp.

The xApp file should handle REST and framework setup.  This service should
handle the robot-control rules:

    - read command limits from config
    - validate incoming command dictionaries
    - reject stale or repeated commands
    - clamp command values when configured
    - map normalized steering data into robot payloads
    - forward payloads to the robot HTTP endpoint
    - remember useful state for `/ric/v1/steering/state`
    - send stop commands when the operator stops or the deadman timer expires

Keep the responsibilities separate:

    steering_xapp.py      -> receives HTTP requests and sends HTTP responses
    steering_service.py   -> decides what commands mean and what should happen
"""

import json
import threading
import time
from dataclasses import dataclass
from math import isfinite
from typing import Any, Dict, Optional, Tuple

import requests


DEFAULT_ROBOT_BASE_URL = "http://10.233.56.235:8090"
DEFAULT_ROBOT_PAYLOAD_FORMAT = "ros_twist"
DEFAULT_ROBOT_MAX_LINEAR_MPS = 0.2
DEFAULT_ROBOT_MAX_ANGULAR_RADPS = 0.5
DEFAULT_ROBOT_TIMEOUT_SECONDS = 0.5

# Servo-arm reference values.
#
# Concept:
#
#     The arm controller expects a servo id and a pulse position.  The complete
#     reference file uses these dictionaries to remember the default position
#     and the allowed min/max range for each servo.
#
# Dictionary syntax:
#
#     key: value
#
# One completed example is left below. Add the remaining servo ids by following
# the same pattern from `steering_service_og.py`.
DEFAULT_ARM_POSITIONS = {1: 500}
DEFAULT_ARM_LIMITS = {1: (0, 1000)}


def now_ms() -> int:
    """
    Return the current time in milliseconds.

    `time.time()` returns seconds as a decimal number.  Robot commands usually
    compare timestamps in milliseconds, so this helper converts seconds to ms.
    """
    return int(time.time() * 1000)


def format_timestamp_date(timestamp_ms: int) -> str:
    """
    Format a millisecond timestamp as a small date string.

    Function-call syntax:

        time.localtime(timestamp_ms / 1000.0)

    Concept:

        The command keeps the original `timestamp_ms` value for precise timing.
        The `timestamp_date` field is an extra readable value that can make
        logs and JSON responses easier to scan.
    """
    dt = time.localtime(timestamp_ms / 1000.0)
    return f"{dt.tm_mon}/{dt.tm_mday:02d}/{dt.tm_year}"


# ---------------------------------------------------------------------------
# Data containers
# ---------------------------------------------------------------------------

@dataclass
class CommandLimits:
    """
    Safety and timing limits for incoming commands.

    A dataclass stores related values without writing a full `__init__` method.

    Concept:

        Each line uses the pattern:

            field_name: type = default_value

        Example:

            steering_min: float = -1.0

        The type hint says which kind of value is expected.  The default value
        is used when `config.json` does not provide that setting.
    """
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
    """
    Robot HTTP endpoint and payload mapping settings.

    Concept:

        `base_url` points at the robot-side helper.  `command_path` and
        `stop_path` are joined onto that base URL for POST requests.

        Video uses two extra paths.  Those fields are included here so the
        config shape is visible.  Servo-arm movement uses `arm_pose_path`.
    """
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
    """
    Runtime state reported by `/ric/v1/steering/state`.

    State is different from config:

        - config says how the service should behave
        - state says what has happened recently
    """
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


# ---------------------------------------------------------------------------
# Service class
# ---------------------------------------------------------------------------

class SteeringCommandService:
    """
    Command-processing service used by the xApp REST handlers.

    Public methods used by `steering_xapp.py`:

        apply_config(config)
        start_deadman()
        stop_deadman()
        submit(body)
        stop(reason)
        snapshot()

    Private helper methods begin with `_`.  They are still normal Python
    methods, but the underscore signals "used inside this class."
    """

    def __init__(self, config: Dict[str, Any], logger: Any = None) -> None:
        """
        Create the service.

        The lock protects shared state because REST handlers and the deadman
        timer can touch the service at the same time.

        Code pattern:

            1. Save `logger`.
            2. Create `self.lock = threading.Lock()`.
            3. Create `self.state = SteeringState()`.
            4. Set `self.deadman_thread` to `None`.
            5. Set `self.keep_running` to `False`.
            6. Call `self.apply_config(config)`.
        """
        self.logger = logger
        self.lock = threading.Lock()
        self.state = SteeringState()
        self.arm_positions = DEFAULT_ARM_POSITIONS.copy()
        self.arm_last_robot_status: Optional[Dict[str, Any]] = None
        self.arm_command_count = 0
        self.arm_last_error: Optional[str] = None
        self.arm_last_command_ms: Optional[int] = None
        self.deadman_thread: Optional[threading.Thread] = None
        self.keep_running = False
        self.apply_config(config)

    def apply_config(self, config: Dict[str, Any]) -> None:
        """
        Read limits and robot settings from the config dictionary.

        Config values live under:

            controls
            controls.bounds
            controls.robot

        Use `.get()` so missing optional values fall back to safe defaults.

        Example pattern:

            controls = config.get("controls", {})
            bounds = controls.get("bounds", {})
            robot = controls.get("robot", {})

            self.limits = CommandLimits(
                steering_min=float(bounds.get("steeringMin", -1.0)),
                ...
            )

        Concept:

        Remember:

            - config uses names like `steeringMin`
            - Python fields use names like `steering_min`
            - cast numeric values with `float(...)` or `int(...)`
            - use `.rstrip("/")` on `baseUrl` so URL building is easier later
        """
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
        """
        Start the background deadman timer.

        The deadman loop watches for command silence.  If a command was accepted
        but no new command arrives within `deadman_timeout_ms`, the service
        should send a stop command.

        Code pattern:

            self.keep_running = True
            self.deadman_thread = threading.Thread(
                target=self._deadman_loop,
                daemon=True,
            )
            self.deadman_thread.start()
        """
        self.keep_running = True
        self.deadman_thread = threading.Thread(target=self._deadman_loop, daemon=True)
        self.deadman_thread.start()

    def stop_deadman(self) -> None:
        """
        Stop the background deadman timer.

        Concept:

            `join(timeout=...)` waits briefly for the thread to exit.  The
            timeout prevents shutdown from waiting forever.
        """
        self.keep_running = False
        if self.deadman_thread is not None:
            self.deadman_thread.join(timeout=1.0)

    def submit(self, body: Dict[str, Any]) -> Tuple[int, Dict[str, Any]]:
        """
        Accept one command dictionary from the REST layer.

        Return shape:

            status_code, payload_dictionary

        Normal success should return:

            202, {"accepted": True, ...}

        Common error statuses:

            400 -> invalid request body or command values
            409 -> stale/repeated sequence number
            429 -> command rate is too fast

        Code pattern:

        Implemented command flow:

            1. Save `received_ms = now_ms()`.
            2. Call `_validate_and_normalize(body, received_ms)`.
            3. If invalid, increment rejected count and return 400.
            4. Lock state with `with self.lock:`.
            5. Check rate limit.
            6. Check repeated/stale sequence number.
            7. Map the command with `_map_robot_payload(command, stop=False)`.
            8. Save state fields such as last command, last payload, last seq.
            9. Unlock before doing network I/O.
            10. POST to the robot with `_post_to_robot(...)`.
            11. Lock again and save robot status.
            12. Return 202 with command, mapped payload, and robot status.

        Concept:

            HTTP requests can be slow.  Holding the lock during network I/O can
            block other code from reading state or stopping the service.
        """
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
        """
        Send a stop command to the robot.

        Stop command idea:

            steering = 0.0
            throttle = 0.0
            brake = 1.0
            enable = False

        Code pattern:

            self._map_robot_payload(stop_command, stop=True)

        Then POST it to:

            self.robot.stop_path

        Update state:

            - last_command
            - last_mapped_payload
            - last_robot_status
            - last_forward_ms
            - stop_count
            - stopped
            - last_error
        """
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
        """
        Return a dictionary showing current config-derived settings and state.

        This is used by:

            GET /ric/v1/steering/state

        Code pattern:

            {
                "limits": self.limits.__dict__,
                "robot": self.robot.__dict__,
                "state": self.state.__dict__.copy(),
            }
        """
        with self.lock:
            return {
                "limits": self.limits.__dict__,
                "robot": self.robot.__dict__,
                "state": self.state.__dict__.copy(),
            }

    def submit_arm_pose(self, body: Dict[str, Any]) -> Tuple[int, Dict[str, Any]]:
        """
        Accept one servo-arm pose request.

        Expected incoming body:

            {
                "duration": 0.2,
                "positions": [
                    {"id": 1, "position": 500}
                ]
            }

        Concept:

            The wheel client sends `positions` because it may update one servo
            or several servos.  The rosbridge helper sends the final ROS message
            using the field name `position`, because that is the message shape
            expected by the servo controller.

        Function-call syntax:

            valid, payload_or_error = self._validate_arm_pose(body)
            robot_status = self._post_to_robot(payload_or_error["mapped"], self.robot.arm_pose_path)

        Dictionary update syntax:

            self.arm_positions.update(payload_or_error["positions"])

        ## TODO
        Complete the servo-arm submit flow:

            1. Call `_validate_arm_pose(body)`.
            2. Return status 400 when validation fails.
            3. POST the mapped payload to `self.robot.arm_pose_path`.
            4. Save the accepted servo positions in `self.arm_positions`.
            5. Save the robot status and command counters.
            6. Return status 202 with accepted state.
        """
        return 501, {"error": "servo arm movement TODO"}

    def arm_snapshot(self) -> Dict[str, Any]:
        """
        Return the current servo-arm state.

        Concept:

            This is the arm version of `snapshot()`.  It gives the REST layer a
            dictionary that can be returned from:

                GET /ric/v1/arm/state

        Dictionary-comprehension syntax:

            {str(k): {"min": v[0], "max": v[1]} for k, v in DEFAULT_ARM_LIMITS.items()}

        ## TODO
        Include:

            - current servo positions
            - allowed servo limits
            - default servo positions
            - last robot status
            - last command timestamp
            - command count
            - last error
        """
        with self.lock:
            return {
                "positions": self.arm_positions.copy(),
                "limits": {str(k): {"min": v[0], "max": v[1]} for k, v in DEFAULT_ARM_LIMITS.items()},
                "defaults": DEFAULT_ARM_POSITIONS.copy(),
                "state": {
                    "last_robot_status": self.arm_last_robot_status,
                    "last_command_ms": self.arm_last_command_ms,
                    "command_count": self.arm_command_count,
                    "last_error": self.arm_last_error,
                },
            }

    def _validate_arm_pose(self, body: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
        """
        Validate and map a servo-arm pose body.

        Concept:

            Validation checks outside input before it is sent to the robot.
            Mapping changes the xApp-facing shape into the robot-facing shape.

        Input field syntax:

            positions = body.get("positions", body.get("position"))
            duration = float(body.get("duration", 0.3))

        Loop syntax:

            for item in positions:
                servo_id = int(item["id"])
                value = int(round(float(item["position"])))

        Clamp syntax:

            lower, upper = DEFAULT_ARM_LIMITS[servo_id]
            bounded = min(max(value, lower), upper)

        Mapped payload shape:

            {
                "duration": duration,
                "position_unit": "pulse",
                "position": [
                    {"id": servo_id, "position": value}
                ]
            }

        ## TODO
        Complete servo-arm validation and mapping.
        """
        return False, {"error": "servo arm validation TODO"}

    def video_snapshot(self) -> Tuple[int, bytes, str]:
        """
        Read one camera image from the robot-side video endpoint.

        Concept:

            A snapshot endpoint returns one complete image as bytes.  This is
            different from command JSON because image data is binary data, not a
            dictionary.

        Function syntax from the complete reference:

            response = requests.get(url, timeout=max(self.robot.timeout_seconds, 2.0))
            content_type = response.headers.get("Content-Type", "application/octet-stream")
            return response.status_code, response.content, content_type

        URL-building example:

            path = self.robot.video_snapshot_path
            url = f"{self.robot.base_url}{path if path.startswith('/') else '/' + path}"

        JSON-error example:

            body = json.dumps({"error": "message"}, sort_keys=True).encode("utf-8")
            return 502, body, "application/json"

        Completed video snapshot flow:

            1. Return JSON error bytes when `self.robot.base_url` is blank.
            2. Build the URL from `self.robot.base_url` and `self.robot.video_snapshot_path`.
            3. Send an HTTP GET request.
            4. Return status code, raw image bytes, and Content-Type.
            5. Catch `requests.RequestException` and return a 502 JSON error.
        """
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

    def video_stream_url(self) -> str:
        """
        Build the robot-side video stream URL.

        Concept:

            The xApp stream route does not decode every frame.  It can proxy the
            robot stream by connecting to this URL and forwarding chunks to the
            wheel client.

        URL-building syntax:

            path = self.robot.video_stream_path
            return f"{self.robot.base_url}{path if path.startswith('/') else '/' + path}"

        Snapshot URL example:

            path = self.robot.video_snapshot_path
            return f"{self.robot.base_url}{path if path.startswith('/') else '/' + path}"

        Completed URL builder.
        """
        path = self.robot.video_stream_path
        return f"{self.robot.base_url}{path if path.startswith('/') else '/' + path}"

    def _validate_and_normalize(self, body: Dict[str, Any], received_ms: int) -> Tuple[bool, Dict[str, Any]]:
        """
        Validate an incoming command and convert fields into expected types.

        Expected command body:

            {
                "seq": 1,
                "timestamp_ms": 1717800000000,
                "steering": 0.1,
                "throttle": 0.2,
                "brake": 0.0,
                "enable": true
            }

        Return shape:

            True, normalized_command
            False, error_payload

        Concept checks:

            1. Make sure required fields exist.
            2. Make sure `enable` is a real Boolean.
            3. Convert sequence and timestamp to `int`.
            4. Convert steering, throttle, and brake to `float`.
            5. Reject values that are not finite numbers using `isfinite`.
            6. Check command timestamp age.
            7. Check future timestamp skew.
            8. Check steering/throttle/brake bounds.
            9. Clamp out-of-range values when `self.limits.clamp_inputs` is True.
            10. Reject out-of-range values when clamping is False.

        Useful snippets:

            required = ("seq", "timestamp_ms", "steering", "throttle", "brake", "enable")
            missing = [key for key in required if key not in body]

            if missing:
                return False, {"error": "missing required field(s)", "fields": missing}

            age_ms = received_ms - command["timestamp_ms"]
        """
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
        """
        Check whether commands are arriving too quickly.

        This method name ends in `_locked` because callers should already hold
        `self.lock` before calling it.

        Logic:

            - if command_rate_hz <= 0, rate limiting is disabled
            - if no command has been accepted yet, allow the command
            - minimum interval is `1000 / command_rate_hz`
            - if elapsed time is too small, return an error dictionary
            - otherwise return None

        Code pattern:

            {"error": "command rate limit exceeded", "retry_after_ms": ...}

        when the command arrives too soon.
        """
        if self.limits.command_rate_hz <= 0 or self.state.last_accept_ms is None:
            return None
        min_interval_ms = int(1000 / self.limits.command_rate_hz)
        elapsed_ms = received_ms - self.state.last_accept_ms
        if elapsed_ms < min_interval_ms:
            return {"error": "command rate limit exceeded", "retry_after_ms": min_interval_ms - elapsed_ms}
        return None

    def _check_stale_locked(self, command: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Check whether sequence numbers are increasing.

        Sequence numbers help reject old or repeated commands.

        Concept:

            This version keeps the function as a reference point, but the
            command path does not reject repeated sequence numbers.  The wheel
            client may restart at sequence 0 during lab testing.
        """
        return None

    def _map_robot_payload(self, command: Dict[str, Any], stop: bool) -> Dict[str, Any]:
        """
        Convert normalized command values into the robot payload format.

        Supported formats:

            normalized
                Send steering, throttle, brake, and enable directly.

            ros_twist / rosorin_twist
                Send a JSON version of a ROS Twist-like command:

                    linear.x  = (throttle - brake) * max_linear_mps
                    angular.z = -steering * max_angular_radps

        Concept:

            In the current wheel convention, positive steering means right.
            In many ROS coordinate conventions, positive angular.z means left.
        """
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
        """
        Send payload using either HTTP POST or rosbridge WebSocket.

        Concept:

            The service can support two robot-side connection styles:

                HTTP base URL       -> requests.post(...)
                ws:// or wss:// URL -> rosbridge publish

            `payload_format == "rosbridge_twist"` also selects rosbridge.
        """
        if not self.robot.base_url:
            return {"ok": True, "skipped": True, "reason": "robot baseUrl is not configured"}
        if self.robot.payload_format == "rosbridge_twist" or self.robot.base_url.startswith(("ws://", "wss://")):
            return self._publish_to_rosbridge(payload, path)
        return self._post_to_robot(payload, path)

    def _post_to_robot(self, payload: Dict[str, Any], path: str) -> Dict[str, Any]:
        """
        POST one payload to the robot.

        If no robot base URL is configured, do not fail.  Return a skipped
        result so local testing can still exercise validation and state logic.

        URL-building pattern:

            url = f"{self.robot.base_url}{path if path.startswith('/') else '/' + path}"

        Request pattern:

            response = requests.post(
                url,
                json=payload,
                timeout=self.robot.timeout_seconds,
            )

        Code pattern:

            1. Return skipped status when `self.robot.base_url` is blank.
            2. Build the URL from base URL and path.
            3. POST JSON to the robot with a timeout.
            4. Return ok/status_code/url/body for HTTP responses.
            5. Catch `requests.RequestException`.
            6. Log the exception if `self.logger` exists.
            7. Return ok False with the URL and error string.
        """
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
        """
        Publish one Twist payload directly to rosbridge.

        Concept:

            rosbridge accepts JSON messages over WebSocket.  The advertise
            message tells rosbridge which ROS topic and message type are being
            used.  The publish message carries the actual Twist data.
        """
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
        """
        Convert an HTTP-style robot URL into a WebSocket URL when needed.

        String slicing syntax:

            self.robot.base_url[len("http://"):]

        removes the `http://` prefix and keeps the rest of the address.
        """
        if self.robot.base_url.startswith(("ws://", "wss://")):
            return self.robot.base_url
        if self.robot.base_url.startswith("https://"):
            return "wss://" + self.robot.base_url[len("https://"):]
        if self.robot.base_url.startswith("http://"):
            return "ws://" + self.robot.base_url[len("http://"):]
        return self.robot.base_url

    def _deadman_loop(self) -> None:
        """
        Background safety loop.

        The loop should keep running while `self.keep_running` is True.

        Deadman logic:

            - sleep for a small part of the timeout
            - skip work if the service is already stopped
            - skip work if no command has ever been accepted
            - compare now against `self.state.last_accept_ms`
            - if elapsed time is too large, mark `deadman_triggered`
            - call `self.stop(reason="deadman_timeout")` outside the lock

        Concept:

            Do not call `self.stop(...)` while still inside `with self.lock:`
            because `stop()` also updates state.

        Useful sleep expression:

            time.sleep(max(self.limits.deadman_timeout_ms / 3000.0, 0.05))
        """
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
