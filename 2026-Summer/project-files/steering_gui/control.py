#!/usr/bin/env python3
"""
Wheel, command, arm, HTTP, and MJPEG control logic for the modular GUI client.

This uses the same input model as logiwheel.py:
    axis 0: steering, centered at 0.0
    axis 1: accelerator, idle +1.0 and pressed toward -1.0
    axis 2: brake, idle +1.0 and pressed toward -1.0
    axis 3: clutch, idle +1.0 and pressed toward -1.0
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
    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        self.seq = 0
        self.keep_running = True
        self.command_url = args.xapp_url.rstrip("/") + "/ric/v1/steering/command"
        self.stop_url = args.xapp_url.rstrip("/") + "/ric/v1/steering/stop"
        self.arm_url = args.xapp_url.rstrip("/") + "/ric/v1/arm/pose"
        self.video_url = self.video_url_with_defaults(args.video_url or (args.xapp_url.rstrip("/") + "/ric/v1/video/stream"))
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
        if pygame is None:
            raise SystemExit("pygame is required to run the wheel client. Install it with: python3 -m pip install pygame")
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
                self.draw_video_frame()
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
                time.sleep(self.args.poll_seconds)
        finally:
            self.send_stop()
            self.reset_arm_on_exit()
            pygame.quit()

    def start_video(self) -> None:
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
        if "/stream" in self.video_url:
            self.video_stream_loop()
            return
        frame_interval = 1.0 / 15.0
        while self.keep_running:
            started = time.monotonic()
            frame = self._get_bytes(self.video_url, timeout=self.args.video_timeout)
            if frame:
                with self.video_lock:
                    self.video_frame = frame
                    self.video_frame_id += 1
            elapsed = time.monotonic() - started
            time.sleep(max(frame_interval - elapsed, 0.001))

    def video_stream_loop(self) -> None:
        request = urllib.request.Request(
            self.video_url,
            headers={"Accept": "multipart/x-mixed-replace,image/jpeg,image/x-portable-pixmap,image/x-portable-graymap"},
        )
        while self.keep_running:
            try:
                with urllib.request.urlopen(request, timeout=self.args.video_timeout) as response:
                    content_type = response.headers.get("Content-Type", "")
                    boundary = self.multipart_boundary(content_type) or b"--frame"
                    if not self.video_stream_logged:
                        print(f"video stream connected: content_type={content_type or 'unknown'} boundary={boundary.decode('utf-8', errors='replace')}")
                        self.video_stream_logged = True
                    buffer = b""
                    while self.keep_running:
                        chunk = response.read(8192)
                        if not chunk:
                            break
                        buffer += chunk
                        buffer = self.extract_multipart_frames(buffer, boundary)
            except urllib.error.HTTPError as exc:
                if self.keep_running:
                    body = self._read_http_error_body(exc)
                    detail = f": {body}" if body else ""
                    print(f"video stream failed: HTTP {exc.code} {exc.reason}{detail}; retrying")
                    time.sleep(1.0)
            except Exception as exc:
                if self.keep_running:
                    print(f"video stream failed: {exc}; retrying")
                    time.sleep(1.0)

    def video_url_with_defaults(self, url: str) -> str:
        parsed = urllib.parse.urlsplit(url)
        query = dict(urllib.parse.parse_qsl(parsed.query, keep_blank_values=True))
        if "/stream" in parsed.path:
            query.setdefault("topic", self.args.video_topic)
            query.setdefault("width", str(self.args.video_width))
            query.setdefault("height", str(self.args.video_height))
            query.setdefault("quality", str(self.args.video_quality))
        path = self.video_path_for_topic(parsed.path, query.get("topic", ""))
        return urllib.parse.urlunsplit(
            (parsed.scheme, parsed.netloc, path, urllib.parse.urlencode(query), parsed.fragment)
        )

    @staticmethod
    def video_path_for_topic(path: str, topic: str) -> str:
        if topic == DEPTH_IMAGE_TOPIC and path.endswith("/ric/v1/video/stream"):
            return path[: -len("/ric/v1/video/stream")] + "/ric/v1/video/depth/stream"
        if topic != DEPTH_IMAGE_TOPIC and path.endswith("/ric/v1/video/depth/stream"):
            return path[: -len("/ric/v1/video/depth/stream")] + "/ric/v1/video/stream"
        return path

    def draw_video_frame(self) -> None:
        if not self.args.video or not self.video_window_started:
            return
        with self.video_lock:
            if self.video_frame is None or self.video_frame_id == self.video_drawn_id:
                return
            frame = self.video_frame
            frame_id = self.video_frame_id
        try:
            image = pygame.image.load(io.BytesIO(frame))
            window = pygame.display.get_surface()
            if window is None:
                return
            scaled = pygame.transform.smoothscale(image.convert(), window.get_size())
            window.blit(scaled, (0, 0))
            pygame.display.flip()
            self.video_drawn_id = frame_id
        except pygame.error as exc:
            print(f"video frame decode failed: {exc}")
            self.video_drawn_id = frame_id

    def build_command(self, axes: Sequence[float], buttons: Sequence[int]) -> Dict[str, Any]:
        enable = True
        if self.args.enable_button >= 0:
            enable = bool(button_value(buttons, self.args.enable_button, default=0))

        command = {
            "seq": self.seq,
            "timestamp_ms": self.command_time_ms(),
            "steering": normalize_steering(
                axis_value(axes, self.args.steering_axis, 0.0),
                deadzone=self.args.steering_deadzone,
                invert=self.args.invert_steering,
            ),
            "throttle": self.normalize_runtime_pedal(
                axis_value(axes, self.args.throttle_axis, 1.0),
                self.throttle_idle_raw,
                idle_deadzone=self.args.pedal_idle_deadzone,
                invert=self.args.invert_throttle,
            ),
            "brake": self.normalize_runtime_pedal(
                axis_value(axes, self.args.brake_axis, 1.0),
                self.brake_idle_raw,
                idle_deadzone=self.args.pedal_idle_deadzone,
                invert=self.args.invert_brake,
            ),
            "enable": enable,
        }
        self.seq += 1
        return command

    def calibrate_pedal_idle(self, axes: Sequence[float]) -> None:
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
        value = clamp(float(raw_value), -1.0, 1.0)
        idle = clamp(float(idle_raw), -1.0, 1.0)
        if invert:
            denominator = max(1.0 - idle, 0.001)
            pressed = clamp((value - idle) / denominator, 0.0, 1.0)
        else:
            denominator = max(idle + 1.0, 0.001)
            pressed = clamp((idle - value) / denominator, 0.0, 1.0)
        return 0.0 if pressed < idle_deadzone else pressed

    def should_send_command(self, command: Dict[str, Any], now: float) -> bool:
        if self.last_sent_command is None:
            return True
        if self.command_changed(command, self.last_sent_command):
            return True
        if self.command_active(command):
            return now - self.last_sent_time >= self.args.active_heartbeat_seconds
        return False

    def command_changed(self, current: Dict[str, Any], previous: Dict[str, Any]) -> bool:
        if bool(current.get("enable", True)) != bool(previous.get("enable", True)):
            return True
        for key in ("steering", "throttle", "brake"):
            if abs(float(current.get(key, 0.0)) - float(previous.get(key, 0.0))) >= self.args.command_deadband:
                return True
        return False

    def command_active(self, command: Dict[str, Any]) -> bool:
        if not command.get("enable", True):
            return True
        return any(abs(float(command.get(key, 0.0))) >= self.args.command_deadband for key in ("steering", "throttle", "brake"))

    def process_arm_buttons(self, axes: Sequence[float], buttons: Sequence[int], now: float) -> None:
        if not self.args.arm_enabled:
            return
        reverse = self.normalize_runtime_pedal(
            axis_value(axes, self.args.clutch_axis, 1.0),
            self.clutch_idle_raw,
            idle_deadzone=self.args.pedal_idle_deadzone,
        ) >= self.args.clutch_reverse_threshold
        repeat_interval = 1.0 / self.args.arm_repeat_hz
        for servo_id, button_index in self.arm_buttons.items():
            if button_index < 0 or not button_value(buttons, button_index):
                continue
            if now < self.arm_next_send[servo_id]:
                continue
            direction = -1 if reverse else 1
            lower, upper = ARM_LIMITS[servo_id]
            current = self.arm_positions[servo_id]
            updated = int(clamp(current + direction * self.args.arm_step, lower, upper))
            self.arm_next_send[servo_id] = now + repeat_interval
            if updated == current:
                continue
            self.arm_positions[servo_id] = updated
            payload = {"duration": self.args.arm_duration, "positions": [{"id": servo_id, "position": updated}]}
            response = self._post_json(self.arm_url, payload)
            if self.args.print_commands:
                print(f"arm id={servo_id} button={button_index} position={updated} reverse={reverse}")
            if response is not None:
                self.print_json_response("arm", response)

    def process_arm_default_button(self, buttons: Sequence[int]) -> None:
        if not self.args.arm_enabled or self.args.arm_default_button < 0:
            return
        pressed = bool(button_value(buttons, self.args.arm_default_button))
        if pressed and not self.arm_default_button_was_pressed:
            self.send_default_arm_pose()
        self.arm_default_button_was_pressed = pressed

    def send_default_arm_pose(self) -> None:
        payload = self.build_arm_pose_payload(
            ARM_LAUNCH_POSITIONS,
            duration=self.args.arm_launch_duration,
            label="user default arm pose",
            quiet_missing=True,
        )
        label = "user default arm"
        if payload is None:
            payload = self.build_arm_pose_payload(
                ARM_ROS_WORKSPACE_DEFAULT_POSITIONS,
                duration=self.args.arm_reset_duration,
                label="ROS workspace default arm pose",
            )
            label = "ROS workspace default arm"
        if payload is None:
            return
        response = self._post_json(self.arm_url, payload)
        if response is not None:
            for item in payload["positions"]:
                self.arm_positions[int(item["id"])] = int(item["position"])
            print(f"Sent {label} command.")
            self.print_json_response(label, response)

    def send_launch_arm_pose(self) -> None:
        if not self.args.arm_enabled:
            return
        payload = self.build_arm_pose_payload(
            ARM_LAUNCH_POSITIONS,
            duration=self.args.arm_launch_duration,
            label="launch arm pose",
        )
        if payload is None:
            return
        response = self._post_json(self.arm_url, payload)
        if response is not None:
            for item in payload["positions"]:
                self.arm_positions[int(item["id"])] = int(item["position"])
            print("Sent launch arm pose command.")
            self.print_json_response("launch arm", response)

    def build_arm_pose_payload(
        self,
        positions: Dict[int, Optional[int]],
        duration: float,
        label: str,
        quiet_missing: bool = False,
    ) -> Optional[Dict[str, Any]]:
        missing = [servo_id for servo_id in ARM_SERVO_IDS if positions.get(servo_id) is None]
        if missing:
            if not quiet_missing:
                print(f"Skipping {label}: servo position(s) unset for {missing}.")
            return None

        payload_positions = []
        for servo_id in ARM_SERVO_IDS:
            try:
                value = int(positions[servo_id])
            except (TypeError, ValueError):
                print(f"Skipping {label}: servo id {servo_id} value {positions[servo_id]!r} is not numeric.")
                return None
            lower, upper = ARM_LIMITS[servo_id]
            if not lower <= value <= upper:
                print(
                    f"Skipping {label}: servo id {servo_id} value {value} "
                    f"is outside allowed range {lower}..{upper}."
                )
                return None
            payload_positions.append({"id": servo_id, "position": value})
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
        if not self.args.arm_reset_on_exit:
            return
        self.send_arm_reset_pose(label="arm reset")

    def send_arm_reset_pose(self, label: str = "ROS workspace arm reset") -> None:
        payload = self.build_arm_pose_payload(
            ARM_ROS_WORKSPACE_DEFAULT_POSITIONS,
            duration=self.args.arm_reset_duration,
            label=label,
        )
        if payload is None:
            return
        try:
            response = self._post_json(self.arm_url, payload)
            print(f"Sent {label} command.")
            if response is not None:
                for item in payload["positions"]:
                    self.arm_positions[int(item["id"])] = int(item["position"])
                self.print_json_response("arm reset", response)
        except Exception as exc:
            print(f"arm reset request failed: {exc}")

    def _post_json(self, url: str, payload: Dict[str, Any]) -> Any:
        data = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=self.args.timeout) as response:
                body = response.read().decode("utf-8", "replace")
                parsed = self.parse_json_body(body)
                if response.status >= 400:
                    print(f"POST {url} returned {response.status}:")
                    self.print_json_response("error", parsed if parsed is not None else body)
                return parsed
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", "replace")
            parsed = self.parse_json_body(body)
            print(f"POST {url} returned {exc.code}:")
            self.print_json_response("error", parsed if parsed is not None else body)
            return None
        except urllib.error.URLError as exc:
            print(f"POST {url} failed: {exc}")
            return None
        except TimeoutError as exc:
            print(f"POST {url} timed out: {exc}")
            return None
        except OSError as exc:
            print(f"POST {url} failed: {exc}")
            return None

    def _get_bytes(self, url: str, timeout: float) -> Optional[bytes]:
        request = urllib.request.Request(url, headers={"Accept": "image/jpeg,image/png,image/x-portable-pixmap,image/x-portable-graymap"})
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.read()
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", "replace")
            print(f"GET {url} returned {exc.code}: {body[:200]}")
        except urllib.error.URLError as exc:
            print(f"GET {url} failed: {exc}")
        except TimeoutError as exc:
            print(f"GET {url} timed out: {exc}")
        except OSError as exc:
            print(f"GET {url} failed: {exc}")
        return None

    def extract_multipart_frames(self, buffer: bytes, boundary: bytes) -> bytes:
        while True:
            start = buffer.find(boundary)
            if start < 0:
                return self.extract_jpeg_frames(buffer)
            if start > 0:
                buffer = buffer[start:]
                start = 0

            header_start = start + len(boundary)
            while header_start < len(buffer) and buffer[header_start : header_start + 1] in (b"\r", b"\n"):
                header_start += 1

            header_end = buffer.find(b"\r\n\r\n", header_start)
            separator_len = 4
            if header_end < 0:
                header_end = buffer.find(b"\n\n", header_start)
                separator_len = 2
            if header_end < 0:
                return self.extract_jpeg_frames(buffer[start:])

            headers = buffer[header_start:header_end]
            body_start = header_end + separator_len
            content_length = self.multipart_content_length(headers)
            if content_length is not None:
                body_end = body_start + content_length
                if len(buffer) < body_end:
                    return buffer[start:]
                frame = buffer[body_start:body_end]
                buffer = buffer[body_end:].lstrip(b"\r\n")
            else:
                next_start = buffer.find(boundary, body_start)
                if next_start < 0:
                    return buffer[start:]
                frame = buffer[body_start:next_start].strip(b"\r\n")
                buffer = buffer[next_start:]

            if frame:
                self.store_video_frame(frame)

    def extract_jpeg_frames(self, buffer: bytes) -> bytes:
        max_keep = 1024 * 1024
        while True:
            start = buffer.find(b"\xff\xd8")
            if start < 0:
                return buffer[-min(len(buffer), max_keep):]
            end = buffer.find(b"\xff\xd9", start + 2)
            if end < 0:
                return buffer[start:]
            frame = buffer[start : end + 2]
            self.store_video_frame(frame)
            buffer = buffer[end + 2 :]

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
        if not body:
            return ""
        try:
            return body.decode("utf-8", errors="replace").strip()
        except Exception:
            return repr(body[:512])

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
