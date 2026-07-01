#!/usr/bin/env python3
"""
Read a Logitech wheel with pygame and POST steering commands to the xApp.

This uses the same input model as logiwheel.py:
    axis 0: steering, centered at 0.0
    axis 1: accelerator, idle +1.0 and pressed toward -1.0
    axis 2: brake, idle +1.0 and pressed toward -1.0
    axis 3: clutch, idle +1.0 and pressed toward -1.0
"""

import argparse
import io
import json
import signal
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional, Sequence, Tuple
try:
    import pygame
except ImportError:
    pygame = None


DEFAULT_WHEEL_CONFIG = {
    "joystick_index": 0,
    "xapp_url": "http://192.168.50.103:18080",
    "rate_hz": 10.0,
    "active_heartbeat_seconds": 0.25,
    "command_deadband": 0.02,
    "poll_seconds": 0.005,
    "timeout": 5.0,
    "video": True,
    "video_fps": 4.0,
    "video_timeout": 8.0,
    "steering_axis": 0,
    "throttle_axis": 1,
    "brake_axis": 2,
    "clutch_axis": 3,
    "left_paddle_button": 4,
    "right_paddle_button": 5,
    "enable_button": -1,
    "stop_button": -1,
    "arm_enabled": True,
    "arm_buttons": "5,4,7,11,6,10",
    "arm_step": 10,
    "arm_repeat_hz": 5.0,
    "arm_duration": 0.2,
    "clutch_reverse_threshold": 0.5,
    "steering_deadzone": 0.03,
    "pedal_idle_deadzone": 0.05,
}

STEERING_AXIS_INDEX = DEFAULT_WHEEL_CONFIG["steering_axis"]
ACCEL_AXIS_INDEX = DEFAULT_WHEEL_CONFIG["throttle_axis"]
BRAKE_AXIS_INDEX = DEFAULT_WHEEL_CONFIG["brake_axis"]
CLUTCH_AXIS_INDEX = DEFAULT_WHEEL_CONFIG["clutch_axis"]
LEFT_PADDLE_BUTTON = DEFAULT_WHEEL_CONFIG["left_paddle_button"]
RIGHT_PADDLE_BUTTON = DEFAULT_WHEEL_CONFIG["right_paddle_button"]
STEERING_DEADZONE = DEFAULT_WHEEL_CONFIG["steering_deadzone"]
PEDAL_IDLE_DEADZONE = DEFAULT_WHEEL_CONFIG["pedal_idle_deadzone"]
AXIS_PRECISION = 3
AXIS_NAMES = ("S", "A", "B", "C")
ARM_SERVO_IDS = (1, 2, 3, 4, 5, 10)
ARM_DEFAULT_POSITIONS = {1: 500, 2: 725, 3: 50, 4: 150, 5: 500, 10: 500}
ARM_LIMITS = {
    1: (100, 1000),
    2: (100, 765),
    3: (0, 468),
    4: (88, 654),
    5: (125, 700),
    10: (200, 700),
}


def clamp(value: float, lower: float, upper: float) -> float:
    return min(max(value, lower), upper)


def normalize_steering(raw_value: float, deadzone: float = STEERING_DEADZONE, invert: bool = False) -> float:
    value = clamp(float(raw_value), -1.0, 1.0)
    if abs(value) < deadzone:
        value = 0.0
    if invert:
        value = -value
    return value


def normalize_pedal(raw_value: float, idle_deadzone: float = PEDAL_IDLE_DEADZONE, invert: bool = False) -> float:
    value = clamp(float(raw_value), -1.0, 1.0)
    if invert:
        value = -value
    pressed = clamp((1.0 - value) / 2.0, 0.0, 1.0)
    return 0.0 if pressed < idle_deadzone else pressed


def read_state(joystick: Any) -> Tuple[List[float], List[int], List[Tuple[int, int]]]:
    axes = [
        round(float(joystick.get_axis(index)), AXIS_PRECISION)
        for index in range(joystick.get_numaxes())
    ]
    buttons = [
        int(joystick.get_button(index))
        for index in range(joystick.get_numbuttons())
    ]
    hats = [
        joystick.get_hat(index)
        for index in range(joystick.get_numhats())
    ]
    return axes, buttons, hats


def axis_value(axes: Sequence[float], index: int, default: float) -> float:
    return axes[index] if 0 <= index < len(axes) else default


def button_value(buttons: Sequence[int], index: int, default: int = 0) -> int:
    return buttons[index] if 0 <= index < len(buttons) else default


def format_axes(axes: Sequence[float]) -> str:
    parts = []
    for index, value in enumerate(axes):
        name = AXIS_NAMES[index] if index < len(AXIS_NAMES) else f"X{index}"
        parts.append(f"{name}={value:+.3f}")
    return " ".join(parts)


class WheelClient:
    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        self.seq = 0
        self.keep_running = True
        self.command_url = args.xapp_url.rstrip("/") + "/ric/v1/steering/command"
        self.stop_url = args.xapp_url.rstrip("/") + "/ric/v1/steering/stop"
        self.arm_url = args.xapp_url.rstrip("/") + "/ric/v1/arm/pose"
        self.video_url = self.video_url_with_defaults(args.video_url or (args.xapp_url.rstrip("/") + "/ric/v1/video/stream"))
        self.arm_positions = ARM_DEFAULT_POSITIONS.copy()
        self.arm_buttons = dict(zip(ARM_SERVO_IDS, args.arm_buttons))
        self.arm_next_send = {servo_id: 0.0 for servo_id in ARM_SERVO_IDS}
        self.video_lock = threading.Lock()
        self.video_frame: Optional[bytes] = None
        self.video_frame_id = 0
        self.video_drawn_id = -1
        self.video_window_started = False
        self.video_thread: Optional[threading.Thread] = None
        self.last_sent_command: Optional[Dict[str, Any]] = None
        self.last_sent_time = 0.0

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

        next_send = 0.0
        try:
            while self.keep_running:
                self.handle_pygame_events()
                self.draw_video_frame()
                axes, buttons, hats = read_state(joystick)
                now = time.monotonic()
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
        frame_interval = 1.0 / self.args.video_fps
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
                    boundary = self.multipart_boundary(response.headers.get("Content-Type", "")) or b"--frame"
                    buffer = b""
                    while self.keep_running:
                        chunk = response.read(8192)
                        if not chunk:
                            break
                        buffer += chunk
                        buffer = self.extract_multipart_frames(buffer, boundary)
            except Exception as exc:
                if self.keep_running:
                    print(f"video stream failed: {exc}; retrying")
                    time.sleep(1.0)

    def video_url_with_defaults(self, url: str) -> str:
        parsed = urllib.parse.urlsplit(url)
        query = dict(urllib.parse.parse_qsl(parsed.query, keep_blank_values=True))
        if "/stream" in parsed.path:
            query.setdefault("fps", str(self.args.video_fps))
        return urllib.parse.urlunsplit(
            (parsed.scheme, parsed.netloc, parsed.path, urllib.parse.urlencode(query), parsed.fragment)
        )

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
            "throttle": normalize_pedal(
                axis_value(axes, self.args.throttle_axis, 1.0),
                idle_deadzone=self.args.pedal_idle_deadzone,
                invert=self.args.invert_throttle,
            ),
            "brake": normalize_pedal(
                axis_value(axes, self.args.brake_axis, 1.0),
                idle_deadzone=self.args.pedal_idle_deadzone,
                invert=self.args.invert_brake,
            ),
            "enable": enable,
        }
        self.seq += 1
        return command

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
        reverse = normalize_pedal(axis_value(axes, self.args.clutch_axis, 1.0)) >= self.args.clutch_reverse_threshold
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
                return buffer[-len(boundary):]
            next_start = buffer.find(boundary, start + len(boundary))
            if next_start < 0:
                return buffer[start:]
            part = buffer[start + len(boundary):next_start].strip(b"\r\n")
            buffer = buffer[next_start:]
            header_end = part.find(b"\r\n\r\n")
            if header_end < 0:
                continue
            frame = part[header_end + 4:].strip(b"\r\n")
            if frame:
                with self.video_lock:
                    self.video_frame = frame
                    self.video_frame_id += 1

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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Logitech wheel client for the steering xApp")
    parser.add_argument("--joystick-index", type=int, default=DEFAULT_WHEEL_CONFIG["joystick_index"], help="pygame joystick index")
    parser.add_argument("--xapp-url", default=DEFAULT_WHEEL_CONFIG["xapp_url"], help="Base URL for the steering xApp")
    parser.add_argument("--rate-hz", type=float, default=DEFAULT_WHEEL_CONFIG["rate_hz"], help="Command publish rate")
    parser.add_argument("--active-heartbeat-seconds", type=float, default=DEFAULT_WHEEL_CONFIG["active_heartbeat_seconds"], help="Repeat unchanged non-zero commands at this interval")
    parser.add_argument("--command-deadband", type=float, default=DEFAULT_WHEEL_CONFIG["command_deadband"], help="Minimum normalized command change that triggers a new POST")
    parser.add_argument("--poll-seconds", type=float, default=DEFAULT_WHEEL_CONFIG["poll_seconds"], help="pygame polling delay")
    parser.add_argument("--timeout", type=float, default=DEFAULT_WHEEL_CONFIG["timeout"], help="HTTP timeout seconds")
    parser.add_argument("--video", dest="video", action="store_true", default=DEFAULT_WHEEL_CONFIG["video"], help="Open a live robot camera window while sending wheel commands")
    parser.add_argument("--no-video", dest="video", action="store_false", help="Disable the robot camera window")
    parser.add_argument("--video-url", default=None, help="Override video snapshot URL")
    parser.add_argument("--video-fps", type=float, default=DEFAULT_WHEEL_CONFIG["video_fps"], help="Video stream rate; 0 disables video")
    parser.add_argument("--video-timeout", type=float, default=DEFAULT_WHEEL_CONFIG["video_timeout"], help="Video snapshot HTTP timeout seconds")
    parser.add_argument("--steering-axis", type=int, default=DEFAULT_WHEEL_CONFIG["steering_axis"])
    parser.add_argument("--throttle-axis", type=int, default=DEFAULT_WHEEL_CONFIG["throttle_axis"])
    parser.add_argument("--brake-axis", type=int, default=DEFAULT_WHEEL_CONFIG["brake_axis"])
    parser.add_argument("--clutch-axis", type=int, default=DEFAULT_WHEEL_CONFIG["clutch_axis"])
    parser.add_argument("--enable-button", type=int, default=DEFAULT_WHEEL_CONFIG["enable_button"], help="Button that must be held; -1 always enables")
    parser.add_argument("--stop-button", type=int, default=DEFAULT_WHEEL_CONFIG["stop_button"], help="Button that stops the client and sends xApp stop")
    parser.add_argument("--arm-enabled", dest="arm_enabled", action="store_true", default=DEFAULT_WHEEL_CONFIG["arm_enabled"])
    parser.add_argument("--no-arm", dest="arm_enabled", action="store_false", help="Disable arm button controls")
    parser.add_argument("--arm-buttons", default=DEFAULT_WHEEL_CONFIG["arm_buttons"], help="Comma-separated buttons for servo ids 1,2,3,4,5,10")
    parser.add_argument("--arm-step", type=int, default=DEFAULT_WHEEL_CONFIG["arm_step"], help="Servo pulse step per arm repeat")
    parser.add_argument("--arm-repeat-hz", type=float, default=DEFAULT_WHEEL_CONFIG["arm_repeat_hz"], help="Arm button hold repeat rate")
    parser.add_argument("--arm-duration", type=float, default=DEFAULT_WHEEL_CONFIG["arm_duration"], help="Arm servo command duration seconds")
    parser.add_argument("--clutch-reverse-threshold", type=float, default=DEFAULT_WHEEL_CONFIG["clutch_reverse_threshold"], help="Normalized clutch value that reverses arm button direction")
    parser.add_argument("--steering-deadzone", type=float, default=DEFAULT_WHEEL_CONFIG["steering_deadzone"])
    parser.add_argument("--pedal-idle-deadzone", type=float, default=DEFAULT_WHEEL_CONFIG["pedal_idle_deadzone"])
    parser.add_argument("--invert-steering", action="store_true")
    parser.add_argument("--invert-throttle", action="store_true", help="Use if the pedal reports idle -1 and pressed +1")
    parser.add_argument("--invert-brake", action="store_true", help="Use if the pedal reports idle -1 and pressed +1")
    parser.add_argument("--print-commands", action="store_true", help="Print axes and JSON command payloads while sending")
    args = parser.parse_args()
    if args.rate_hz <= 0:
        parser.error("--rate-hz must be greater than 0")
    if args.active_heartbeat_seconds <= 0:
        parser.error("--active-heartbeat-seconds must be greater than 0")
    if args.command_deadband < 0:
        parser.error("--command-deadband must be greater than or equal to 0")
    if args.video_fps < 0:
        parser.error("--video-fps must be greater than or equal to 0")
    if args.arm_repeat_hz <= 0:
        parser.error("--arm-repeat-hz must be greater than 0")
    args.arm_buttons = parse_int_list(args.arm_buttons, expected=6, parser=parser, name="--arm-buttons")
    return args


def parse_int_list(value: str, expected: int, parser: argparse.ArgumentParser, name: str) -> List[int]:
    try:
        items = [int(item.strip()) for item in value.split(",")]
    except ValueError:
        parser.error(f"{name} must be a comma-separated list of integers")
    if len(items) != expected:
        parser.error(f"{name} must contain {expected} integers")
    return items


def main() -> None:
    args = parse_args()
    if args.video_fps == 0:
        args.video = False
    client = WheelClient(args)

    def stop(_signum, _frame) -> None:
        client.keep_running = False

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    client.run()


if __name__ == "__main__":
    main()
