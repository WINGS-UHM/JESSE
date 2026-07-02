#!/usr/bin/env python3
"""
Wheel, command, arm, HTTP, and MJPEG control logic.

This module is the closest match to `wheel_client.py`.  The GUI package adds:

    - a dashboard window
    - camera switching
    - event log messages
    - pedal idle calibration
    - command deadband and heartbeat logic
    - arm default/reset helpers

Typical input model:

    axis 0 -> steering
    axis 1 -> accelerator
    axis 2 -> brake
    axis 3 -> clutch

Typical xApp REST paths:

    /ric/v1/steering/command
    /ric/v1/steering/stop
    /ric/v1/arm/pose
    /ric/v1/video/stream
"""

import argparse
import io
import json
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, Optional, Sequence, Tuple

try:
    import pygame
except ImportError:
    pygame = None

from .constants import (
    ARM_LAUNCH_POSITIONS,
    ARM_LIMITS,
    ARM_ROS_WORKSPACE_DEFAULT_POSITIONS,
    ARM_SERVO_IDS,
    DEPTH_IMAGE_TOPIC,
)
from .helpers import axis_value, button_value, clamp, format_axes, normalize_steering, read_state


class WheelControlClient:
    """
    Base client logic shared by terminal and GUI versions.

    The GUI subclass adds dashboard state, key handling, and event logging.
    """

    def __init__(self, args: argparse.Namespace) -> None:
        """
        Save command-line settings and create state variables.

        Concrete values to set:

            self.seq = 0
            self.keep_running = True
            self.last_sent_time = 0.0
            self.throttle_idle_raw = 1.0
            self.brake_idle_raw = 1.0
            self.clutch_idle_raw = 1.0

        URL-building syntax:

            base = args.xapp_url.rstrip("/")
            self.command_url = base + "/ric/v1/steering/command"

        ## TODO
        Set these variables to these exact values:

            self.stop_url = base + "/ric/v1/steering/stop"
            self.arm_url = base + "/ric/v1/arm/pose"
            self.video_url = self.video_url_with_defaults(args.video_url or (base + "/ric/v1/video/stream"))
            self.arm_positions = ARM_ROS_WORKSPACE_DEFAULT_POSITIONS.copy()
            self.arm_buttons = dict(zip(ARM_SERVO_IDS, args.arm_buttons))
            self.arm_next_send = {servo_id: 0.0 for servo_id in ARM_SERVO_IDS}
            self.arm_default_button_was_pressed = False
            self.video_lock = threading.Lock()
            self.video_frame = None
            self.video_frame_id = 0
            self.video_drawn_id = -1
            self.video_window_started = False
            self.video_thread = None
            self.video_stream_logged = False
            self.video_first_frame_logged = False
            self.last_sent_command = None
        """
        self.args = args
        self.seq = 0
        self.keep_running = True
        base = args.xapp_url.rstrip("/")
        self.command_url = base + "/ric/v1/steering/command"
        self.stop_url = base + "/ric/v1/steering/stop"
        self.arm_url = base + "/ric/v1/arm/pose"
        self.video_url = self.video_url_with_defaults(args.video_url or (base + "/ric/v1/video/stream"))
        self.arm_positions = ARM_ROS_WORKSPACE_DEFAULT_POSITIONS.copy()
        self.arm_buttons = dict(zip(ARM_SERVO_IDS, args.arm_buttons))
        self.arm_next_send = {servo_id: 0.0 for servo_id in ARM_SERVO_IDS}
        self.arm_default_button_was_pressed = False
        self.video_lock = threading.Lock()
        self.video_frame: Optional[bytes] = None
        self.video_frame_id = 0
        self.video_drawn_id = -1
        self.video_window_started = False
        self.video_thread: Optional[threading.Thread] = None
        self.video_stream_logged = False
        self.video_first_frame_logged = False
        self.last_sent_command: Optional[Dict[str, Any]] = None
        self.last_sent_time = 0.0
        self.throttle_idle_raw = 1.0
        self.brake_idle_raw = 1.0
        self.clutch_idle_raw = 1.0

    def run(self) -> None:
        """
        Main wheel loop.

        Loop timing values:

            command rate: self.args.rate_hz, default 10.0
            poll sleep: self.args.poll_seconds, default 0.005

        ## TODO
        Set up the loop with these exact statements:

            pygame.init()
            pygame.joystick.init()
            joystick = pygame.joystick.Joystick(self.args.joystick_index)
            joystick.init()
            next_send = 0.0

        If video is enabled, call:

            self.start_video()

        Set the initial axes with:

            axes, _buttons, _hats = read_state(joystick)

        Then call:

            self.calibrate_pedal_idle(axes)

        Inside the loop, set:

            axes, buttons, hats = read_state(joystick)
            now = time.monotonic()
            command = self.build_command(axes, buttons)

        After sending a command, set:

            self.last_sent_command = command
            self.last_sent_time = now
            next_send = time.monotonic() + (1.0 / self.args.rate_hz)
        """
        if pygame is None:
            raise SystemExit("pygame is required. Install it with: python3 -m pip install pygame")
        pygame.init()
        pygame.joystick.init()
        if pygame.joystick.get_count() == 0:
            raise SystemExit("No joystick or wheel detected by pygame.")

        joystick = pygame.joystick.Joystick(self.args.joystick_index)
        joystick.init()
        print(
            f"Using {joystick.get_name()} "
            f"axes={joystick.get_numaxes()} buttons={joystick.get_numbuttons()} hats={joystick.get_numhats()}"
        )
        if self.args.video:
            self.start_video()
        self.send_launch_arm_pose()
        axes, _buttons, _hats = read_state(joystick)
        self.calibrate_pedal_idle(axes)

        next_send = 0.0
        try:
            while self.keep_running:
                self.handle_pygame_events()
                axes, buttons, hats = read_state(joystick)
                now = time.monotonic()
                self.process_arm_default_button(buttons)
                self.process_arm_buttons(axes, buttons, now)
                if now >= next_send:
                    command = self.build_command(axes, buttons)
                    if self.should_send_command(command, now):
                        response = self._post_json(self.command_url, command)
                        self.last_sent_command = command
                        self.last_sent_time = now
                        if self.args.print_commands:
                            print(f"seq={command['seq']} axes={format_axes(axes)} cmd={json.dumps(command, sort_keys=True)}")
                        if response is not None:
                            self.print_json_response("command", response)
                    next_send = time.monotonic() + (1.0 / self.args.rate_hz)
                if self.stop_requested(buttons, hats):
                    self.keep_running = False
                self.draw_video_frame()
                time.sleep(self.args.poll_seconds)
        finally:
            self.send_stop()
            self.reset_arm_on_exit()
            pygame.quit()

    def start_video(self) -> None:
        """
        Start a simple video window and background video thread.

        GUI subclass overrides this with dashboard dimensions:

            width = 1120
            height = 720
        """
        self.video_window_started = True
        pygame.display.set_caption("Robot camera")
        pygame.display.set_mode((640, 480), pygame.RESIZABLE)
        self.video_thread = threading.Thread(target=self.video_loop, daemon=True)
        self.video_thread.start()
        print(f"Video window started from {self.video_url}")

    def handle_pygame_events(self) -> None:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.keep_running = False

    def video_loop(self) -> None:
        """
        Read video frames in a background thread.

        ## TODO
        Set the stream branch to:

            if "/stream" in self.video_url:
                self.video_stream_loop()
                return

        For snapshot mode, set:

            frame_interval = 1.0 / 15.0
            started = time.monotonic()
            frame = self._get_bytes(self.video_url, timeout=self.args.video_timeout)
            elapsed = time.monotonic() - started

        When a frame exists, set:

            self.video_frame = frame
            self.video_frame_id += 1

        At the end of each snapshot loop, call:

            time.sleep(max(frame_interval - elapsed, 0.001))
        """
        if "/stream" in self.video_url:
            self.video_stream_loop()
            return

    def video_stream_loop(self) -> None:
        """
        Read a multipart stream.

        Request syntax:

            urllib.request.Request(self.video_url, headers={"Accept": "multipart/x-mixed-replace,image/jpeg"})

        ## TODO
        Set request to:

            request = urllib.request.Request(
                self.video_url,
                headers={"Accept": "multipart/x-mixed-replace,image/jpeg,image/x-portable-pixmap,image/x-portable-graymap"},
            )

        Inside the response block, set:

            content_type = response.headers.get("Content-Type", "")
            boundary = self.multipart_boundary(content_type) or b"--frame"
            buffer = b""

        Inside the read loop, set:

            chunk = response.read(8192)
            buffer += chunk

        Then update `buffer` with:

            buffer = self.extract_multipart_frames(buffer, boundary)
        """
        return

    def video_url_with_defaults(self, url: str) -> str:
        """
        Add video query parameters when the URL points at a stream.

        Values to set when missing:

            topic: self.args.video_topic
            width: self.args.video_width       default 640
            height: self.args.video_height     default 400
            quality: self.args.video_quality   default 60
        """
        parsed = urllib.parse.urlsplit(url)
        query = dict(urllib.parse.parse_qsl(parsed.query, keep_blank_values=True))
        if "/stream" in parsed.path:
            query.setdefault("topic", self.args.video_topic)
            query.setdefault("width", str(self.args.video_width))
            query.setdefault("height", str(self.args.video_height))
            query.setdefault("quality", str(self.args.video_quality))
        path = self.video_path_for_topic(parsed.path, query.get("topic", ""))
        return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, path, urllib.parse.urlencode(query), parsed.fragment))

    @staticmethod
    def video_path_for_topic(path: str, topic: str) -> str:
        """
        Switch between normal video and depth video xApp routes.

        Normal route:

            /ric/v1/video/stream

        Depth route:

            /ric/v1/video/depth/stream
        """
        if topic == DEPTH_IMAGE_TOPIC and path.endswith("/ric/v1/video/stream"):
            return path[: -len("/ric/v1/video/stream")] + "/ric/v1/video/depth/stream"
        if topic != DEPTH_IMAGE_TOPIC and path.endswith("/ric/v1/video/depth/stream"):
            return path[: -len("/ric/v1/video/depth/stream")] + "/ric/v1/video/stream"
        return path

    def draw_video_frame(self) -> None:
        """
        Simple video draw method.

        Dashboard rendering overrides this method in `dashboard.py`.
        """
        return

    def build_command(self, axes: Sequence[float], buttons: Sequence[int]) -> Dict[str, Any]:
        """
        Build one steering command dictionary.

        Required JSON fields:

            seq
            timestamp_ms
            steering
            throttle
            brake
            enable

        ## TODO
        Set `enable` first:

            enable = True

        If an enable button is configured, replace `enable` with:

            enable = bool(button_value(buttons, self.args.enable_button, default=0))

        In the command dictionary, set:

            "seq": self.seq
            "timestamp_ms": self.command_time_ms()
            "steering": normalize_steering(
                axis_value(axes, self.args.steering_axis, 0.0),
                deadzone=self.args.steering_deadzone,
                invert=self.args.invert_steering,
            )
            "throttle": self.normalize_runtime_pedal(
                axis_value(axes, self.args.throttle_axis, 1.0),
                self.throttle_idle_raw,
                idle_deadzone=self.args.pedal_idle_deadzone,
                invert=self.args.invert_throttle,
            )
            "brake": self.normalize_runtime_pedal(
                axis_value(axes, self.args.brake_axis, 1.0),
                self.brake_idle_raw,
                idle_deadzone=self.args.pedal_idle_deadzone,
                invert=self.args.invert_brake,
            )
            "enable": enable
        """
        command = {
            "seq": self.seq,
            "timestamp_ms": self.command_time_ms(),
            "steering": 0.0,
            "throttle": 0.0,
            "brake": 0.0,
            "enable": True,
        }
        self.seq += 1
        return command

    def calibrate_pedal_idle(self, axes: Sequence[float]) -> None:
        """
        Save current pedal axis values as idle values.

        Assignments to make when calibration is enabled:

            self.throttle_idle_raw = axis_value(axes, self.args.throttle_axis, 1.0)
            self.brake_idle_raw = axis_value(axes, self.args.brake_axis, 1.0)
            self.clutch_idle_raw = axis_value(axes, self.args.clutch_axis, 1.0)
        """
        if not self.args.calibrate_pedals:
            return
        self.throttle_idle_raw = axis_value(axes, self.args.throttle_axis, 1.0)
        self.brake_idle_raw = axis_value(axes, self.args.brake_axis, 1.0)
        self.clutch_idle_raw = axis_value(axes, self.args.clutch_axis, 1.0)
        print(
            "Pedal idle calibration: "
            f"throttle={self.throttle_idle_raw:+.3f} "
            f"brake={self.brake_idle_raw:+.3f} "
            f"clutch={self.clutch_idle_raw:+.3f}"
        )

    def normalize_runtime_pedal(self, raw_value: float, idle_raw: float, idle_deadzone: float, invert: bool = False) -> float:
        """
        Convert raw pedal input using a measured idle value.

        ## TODO
        Set:

            value = clamp(float(raw_value), -1.0, 1.0)
            idle = clamp(float(idle_raw), -1.0, 1.0)

        If `invert` is true, set:

            denominator = max(1.0 - idle, 0.001)
            pressed = clamp((value - idle) / denominator, 0.0, 1.0)

        Otherwise set:

            denominator = max(idle + 1.0, 0.001)
            pressed = clamp((idle - value) / denominator, 0.0, 1.0)

        Return:

            0.0 if pressed < idle_deadzone else pressed
        """
        return 0.0

    def should_send_command(self, command: Dict[str, Any], now: float) -> bool:
        """
        Decide whether to POST a command.

        Send when:

            - there is no previous command
            - command changed by at least `command_deadband`, default 0.02
            - command is active and heartbeat elapsed, default 0.25 seconds
        """
        if self.last_sent_command is None:
            return True
        if self.command_changed(command, self.last_sent_command):
            return True
        if self.command_active(command):
            return now - self.last_sent_time >= self.args.active_heartbeat_seconds
        return False

    def command_changed(self, current: Dict[str, Any], previous: Dict[str, Any]) -> bool:
        """
        Compare steering, throttle, brake, and enable.

        ## TODO
        First compare enable values:

            if bool(current.get("enable", True)) != bool(previous.get("enable", True)):
                return True

        Then loop through:

            for key in ("steering", "throttle", "brake"):

        Set the difference expression to:

            abs(float(current.get(key, 0.0)) - float(previous.get(key, 0.0)))

        Return True when that difference is greater than or equal to:

            self.args.command_deadband

        Return False after the loop.
        """
        return True

    def command_active(self, command: Dict[str, Any]) -> bool:
        """
        Return True when steering, throttle, or brake is outside the deadband.
        """
        return any(abs(float(command.get(key, 0.0))) >= self.args.command_deadband for key in ("steering", "throttle", "brake"))

    def process_arm_buttons(self, axes: Sequence[float], buttons: Sequence[int], now: float) -> None:
        """
        Move arm servos from wheel buttons.

        Button map default:

            servo ids: 1, 2, 3, 4, 5, 10
            buttons:   5, 4, 7, 11, 6, 10

        Payload shape:

            {"duration": 0.2, "positions": [{"id": servo_id, "position": updated}]}

        ## TODO
        Return immediately when:

            not self.args.arm_enabled

        Set `reverse` to:

            self.normalize_runtime_pedal(
                axis_value(axes, self.args.clutch_axis, 1.0),
                self.clutch_idle_raw,
                idle_deadzone=self.args.pedal_idle_deadzone,
            ) >= self.args.clutch_reverse_threshold

        Set:

            repeat_interval = 1.0 / self.args.arm_repeat_hz

        In the servo loop, set:

            direction = -1 if reverse else 1
            lower, upper = ARM_LIMITS[servo_id]
            current = self.arm_positions[servo_id]
            updated = int(clamp(current + direction * self.args.arm_step, lower, upper))
            self.arm_next_send[servo_id] = now + repeat_interval

        If `updated == current`, continue.

        Otherwise set:

            self.arm_positions[servo_id] = updated
            payload = {"duration": self.args.arm_duration, "positions": [{"id": servo_id, "position": updated}]}
            response = self._post_json(self.arm_url, payload)
        """
        return

    def process_arm_default_button(self, buttons: Sequence[int]) -> None:
        """
        Send the default arm pose on a button edge.

        Default button:

            self.args.arm_default_button = 0
        """
        if not self.args.arm_enabled or self.args.arm_default_button < 0:
            return
        pressed = bool(button_value(buttons, self.args.arm_default_button))
        if pressed and not self.arm_default_button_was_pressed:
            self.send_default_arm_pose()
        self.arm_default_button_was_pressed = pressed

    def send_default_arm_pose(self) -> None:
        """
        Send user default pose when set, otherwise ROS workspace default pose.
        """
        payload = self.build_arm_pose_payload(
            ARM_LAUNCH_POSITIONS,
            duration=self.args.arm_launch_duration,
            label="user default arm pose",
            quiet_missing=True,
        )
        if payload is None:
            payload = self.build_arm_pose_payload(
                ARM_ROS_WORKSPACE_DEFAULT_POSITIONS,
                duration=self.args.arm_reset_duration,
                label="ROS workspace default arm pose",
            )
        if payload is not None:
            self._post_json(self.arm_url, payload)

    def send_launch_arm_pose(self) -> None:
        """
        Send optional launch arm pose.

        `ARM_LAUNCH_POSITIONS` contains `None` values by default.  In that case
        this method should skip sending.
        """
        if not self.args.arm_enabled:
            return
        payload = self.build_arm_pose_payload(
            ARM_LAUNCH_POSITIONS,
            duration=self.args.arm_launch_duration,
            label="launch arm pose",
        )
        if payload is not None:
            self._post_json(self.arm_url, payload)

    def build_arm_pose_payload(
        self,
        positions: Dict[int, Optional[int]],
        duration: float,
        label: str,
        quiet_missing: bool = False,
    ) -> Optional[Dict[str, Any]]:
        """
        Build a full arm-pose payload.

        ## TODO
        Set `missing` to:

            missing = [servo_id for servo_id in ARM_SERVO_IDS if positions.get(servo_id) is None]

        If `missing` is not empty and `quiet_missing` is false, print:

            print(f"Skipping {label}: servo position(s) unset for {missing}.")

        Then return:

            None

        For each servo id, set:

            value = int(positions[servo_id])
            lower, upper = ARM_LIMITS[servo_id]

        If the value is outside the allowed range, return `None`.

        Otherwise append:

            {"id": servo_id, "position": value}

        Return shape:

            {"duration": duration, "positions": [{"id": 1, "position": 500}, ...]}
        """
        missing = [servo_id for servo_id in ARM_SERVO_IDS if positions.get(servo_id) is None]
        if missing:
            if not quiet_missing:
                print(f"Skipping {label}: servo position(s) unset for {missing}.")
            return None
        payload_positions = [{"id": servo_id, "position": int(positions[servo_id])} for servo_id in ARM_SERVO_IDS]
        return {"duration": duration, "positions": payload_positions}

    def command_time_ms(self) -> int:
        return int(time.time() * 1000)

    def stop_requested(self, buttons: Sequence[int], _hats: Sequence[Tuple[int, int]]) -> bool:
        return self.args.stop_button >= 0 and bool(button_value(buttons, self.args.stop_button, default=0))

    def send_stop(self) -> None:
        try:
            response = self._post_json(self.stop_url, {})
            print("Sent stop command.")
            if response is not None:
                self.print_json_response("stop", response)
        except Exception as exc:
            print(f"stop request failed: {exc}")

    def reset_arm_on_exit(self) -> None:
        """
        Send ROS workspace default pose when exiting.

        Enabled by default:

            self.args.arm_reset_on_exit = True
        """
        if not self.args.arm_reset_on_exit:
            return
        payload = self.build_arm_pose_payload(
            ARM_ROS_WORKSPACE_DEFAULT_POSITIONS,
            duration=self.args.arm_reset_duration,
            label="exit arm reset",
        )
        if payload is not None:
            self._post_json(self.arm_url, payload)

    def _post_json(self, url: str, payload: Dict[str, Any]) -> Any:
        """
        POST JSON to an xApp URL.

        Function-call syntax:

            json.dumps(payload).encode("utf-8")
            urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
            urllib.request.urlopen(request, timeout=self.args.timeout)
        """
        data = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=self.args.timeout) as response:
                body = response.read().decode("utf-8", "replace")
                return self.parse_json_body(body)
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", "replace")
            parsed = self.parse_json_body(body)
            print(f"POST {url} returned {exc.code}:")
            self.print_json_response("error", parsed if parsed is not None else body)
            return None
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            print(f"POST {url} failed: {exc}")
            return None

    def _get_bytes(self, url: str, timeout: float) -> Optional[bytes]:
        request = urllib.request.Request(url, headers={"Accept": "image/jpeg,image/png,image/x-portable-pixmap,image/x-portable-graymap"})
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.read()
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError) as exc:
            print(f"GET {url} failed: {exc}")
        return None

    def extract_multipart_frames(self, buffer: bytes, boundary: bytes) -> bytes:
        """
        Extract complete frames from a multipart stream buffer.

        ## TODO
        Set:

            start = buffer.find(boundary)

        If `start < 0`, return:

            self.extract_jpeg_frames(buffer)

        Set:

            header_start = start + len(boundary)
            header_end = buffer.find(b"\r\n\r\n", header_start)
            content_length = self.multipart_content_length(headers)

        When a complete frame is found, call:

            self.store_video_frame(frame)

        Return the unfinished part of `buffer`.
        """
        return buffer

    def extract_jpeg_frames(self, buffer: bytes) -> bytes:
        """
        Fallback parser for raw JPEG bytes.

        JPEG start bytes:

            b"\\xff\\xd8"

        JPEG end bytes:

            b"\\xff\\xd9"
        """
        return buffer

    def store_video_frame(self, frame: bytes) -> None:
        with self.video_lock:
            self.video_frame = frame
            self.video_frame_id += 1
        if not self.video_first_frame_logged:
            print(f"video frame received: {len(frame)} bytes")
            self.video_first_frame_logged = True

    @staticmethod
    def multipart_content_length(headers: bytes) -> Optional[int]:
        for line in headers.replace(b"\r\n", b"\n").split(b"\n"):
            key, _, value = line.partition(b":")
            if key.strip().lower() != b"content-length":
                continue
            try:
                return int(value.strip())
            except ValueError:
                return None
        return None

    @staticmethod
    def _read_http_error_body(exc: urllib.error.HTTPError) -> str:
        try:
            body = exc.read(4096)
        except Exception:
            return ""
        return body.decode("utf-8", errors="replace").strip() if body else ""

    @staticmethod
    def multipart_boundary(content_type: str) -> Optional[bytes]:
        for item in content_type.split(";"):
            key, _, value = item.strip().partition("=")
            if key.lower() == "boundary" and value:
                token = value.strip().strip('"')
                if not token.startswith("--"):
                    token = "--" + token
                return token.encode("ascii", "ignore")
        return None

    @staticmethod
    def parse_json_body(body: str) -> Any:
        if not body:
            return None
        try:
            return json.loads(body)
        except ValueError:
            return body

    @staticmethod
    def print_json_response(label: str, payload: Any) -> None:
        print(f"{label} response:")
        if isinstance(payload, (dict, list)):
            print(json.dumps(payload, indent=2, sort_keys=True))
        else:
            print(payload)
