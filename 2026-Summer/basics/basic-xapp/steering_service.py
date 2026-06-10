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

import threading
import time
from dataclasses import dataclass
from math import isfinite
from typing import Any, Dict, Optional, Tuple

import requests


def now_ms() -> int:
    """
    Return the current time in milliseconds.

    `time.time()` returns seconds as a decimal number.  Robot commands usually
    compare timestamps in milliseconds, so this helper converts seconds to ms.
    """
    return int(time.time() * 1000)


# ---------------------------------------------------------------------------
# Data containers
# ---------------------------------------------------------------------------

@dataclass
class CommandLimits:
    """
    Safety and timing limits for incoming commands.

    A dataclass stores related values without writing a full `__init__` method.
    The first line below is left as the pattern.

    ## TODO
    Add the remaining fields from `config.json`.

    Fields to add:

        steering_max: largest allowed steering value, default 1.0
        throttle_min: smallest allowed throttle value, default 0.0
        throttle_max: largest allowed throttle value, default 1.0
        brake_min: smallest allowed brake value, default 0.0
        brake_max: largest allowed brake value, default 1.0
        clamp_inputs: whether out-of-range values are clamped, default True
        command_rate_hz: max accepted command rate, default 20.0
        deadman_timeout_ms: stop if commands pause too long, default 500
        max_command_age_ms: reject old timestamps, default 1000
        max_future_skew_ms: reject timestamps too far ahead, default 250
    """
    steering_min: float = -1.0
    # TODO: add the remaining CommandLimits fields.


@dataclass
class RobotTarget:
    """
    Robot HTTP endpoint and payload mapping settings.

    The first field is left as the pattern.  Each extra field should follow the
    same style:

        name: type = default_value

    ## TODO
    Add these fields:

        command_path: path for normal command POSTs, default "/api/steering"
        stop_path: path for stop command POSTs, default "/api/steering"
        timeout_seconds: HTTP request timeout, default 0.2
        payload_format: "normalized", "ros_twist", or "rosorin_twist"
        max_linear_mps: maximum linear speed scale, default 1.0
        max_angular_radps: maximum angular speed scale, default 1.0
    """
    base_url: str = ""
    # TODO: add the remaining RobotTarget fields.


@dataclass
class SteeringState:
    """
    Runtime state reported by `/ric/v1/steering/state`.

    State is different from config:

        - config says how the service should behave
        - state says what has happened recently

    The first field is left as the pattern.

    ## TODO
    Add fields for:

        last_mapped_payload: last payload sent to the robot
        last_robot_status: last HTTP result from the robot POST
        last_accept_ms: time when the last command was accepted
        last_forward_ms: time when the last robot POST finished
        last_seq: last accepted sequence number
        command_count: number of accepted commands
        rejected_count: number of rejected commands
        stop_count: number of stop commands sent
        deadman_triggered: whether the deadman timer caused a stop
        stopped: whether the service is currently stopped
        last_error: most recent error string, if any
    """
    last_command: Optional[Dict[str, Any]] = None
    # TODO: add the remaining SteeringState fields.


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

        ## TODO
        Complete the setup:

            1. Save `logger`.
            2. Create `self.lock = threading.Lock()`.
            3. Create `self.state = SteeringState()`.
            4. Set `self.deadman_thread` to `None`.
            5. Set `self.keep_running` to `False`.
            6. Call `self.apply_config(config)`.
        """
        # TODO: initialize logger, lock, state, deadman fields, and config.

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

        ## TODO
        Build `self.limits` from `CommandLimits`.
        Build `self.robot` from `RobotTarget`.

        Remember:

            - config uses names like `steeringMin`
            - Python fields use names like `steering_min`
            - cast numeric values with `float(...)` or `int(...)`
            - use `.rstrip("/")` on `baseUrl` so URL building is easier later
        """
        # TODO: read controls, bounds, and robot dictionaries.
        # TODO: create self.limits.
        # TODO: create self.robot.

    def start_deadman(self) -> None:
        """
        Start the background deadman timer.

        The deadman loop watches for command silence.  If a command was accepted
        but no new command arrives within `deadman_timeout_ms`, the service
        should send a stop command.

        ## TODO
        Implement this pattern:

            self.keep_running = True
            self.deadman_thread = threading.Thread(
                target=self._deadman_loop,
                daemon=True,
            )
            self.deadman_thread.start()
        """
        # TODO: create and start the deadman thread.

    def stop_deadman(self) -> None:
        """
        Stop the background deadman timer.

        ## TODO
        Set `self.keep_running` to False.  If a thread exists, join it with a
        short timeout so shutdown can finish cleanly.
        """
        # TODO: stop and join the deadman thread.

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

        ## TODO
        Implement the command flow:

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

        Why unlock before network I/O?

            HTTP requests can be slow.  Holding the lock during network I/O can
            block other code from reading state or stopping the service.
        """
        # TODO: validate, rate-limit, map, forward, update state, and return.

    def stop(self, reason: str = "operator") -> Tuple[int, Dict[str, Any]]:
        """
        Send a stop command to the robot.

        Stop command idea:

            steering = 0.0
            throttle = 0.0
            brake = 1.0
            enable = False

        ## TODO
        Build a stop command dictionary, map it with:

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
        # TODO: create stop command, map it, post it, update state, return 202.

    def snapshot(self) -> Dict[str, Any]:
        """
        Return a dictionary showing current config-derived settings and state.

        This is used by:

            GET /ric/v1/steering/state

        ## TODO
        Lock before reading state and return:

            {
                "limits": self.limits.__dict__,
                "robot": self.robot.__dict__,
                "state": self.state.__dict__.copy(),
            }
        """
        # TODO: return limits, robot, and state dictionaries.

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

        ## TODO
        Implement these checks:

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
        # TODO: validate fields, normalize types, clamp values, and return.

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

        ## TODO
        Return:

            {"error": "command rate limit exceeded", "retry_after_ms": ...}

        when the command arrives too soon.
        """
        # TODO: implement command-rate check.

    def _check_stale_locked(self, command: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Check whether sequence numbers are increasing.

        Sequence numbers help reject old or repeated commands.

        ## TODO
        If `self.state.last_seq` exists and `command["seq"]` is less than or
        equal to it, return:

            {"error": "sequence number must increase", "last_seq": self.state.last_seq}

        Otherwise return None.
        """
        # TODO: implement sequence-number check.

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

        Why negative steering for angular.z?

            In the current wheel convention, positive steering means right.
            In many ROS coordinate conventions, positive angular.z means left.

        ## TODO
        Implement two branches:

            1. If payload format is `ros_twist` or `rosorin_twist`, return a
               nested payload with `linear`, `angular`, and `enable`.
            2. Otherwise return the normalized payload.

        Stop behavior:

            - steering should become 0.0
            - throttle should become 0.0
            - brake should become 1.0
            - enable should become False
        """
        # TODO: map command into robot payload format.

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

        ## TODO
        Implement:

            1. Return skipped status when `self.robot.base_url` is blank.
            2. Build the URL from base URL and path.
            3. POST JSON to the robot with a timeout.
            4. Return ok/status_code/url/body for HTTP responses.
            5. Catch `requests.RequestException`.
            6. Log the exception if `self.logger` exists.
            7. Return ok False with the URL and error string.
        """
        # TODO: implement robot HTTP POST.

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

        ## TODO
        Implement the loop carefully.  Do not call `self.stop(...)` while still
        inside `with self.lock:` because `stop()` also updates state.

        Useful sleep expression:

            time.sleep(max(self.limits.deadman_timeout_ms / 3000.0, 0.05))
        """
        # TODO: implement the deadman loop.
