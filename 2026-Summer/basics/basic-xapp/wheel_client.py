#!/usr/bin/env python3
"""
Wheel client for the steering xApp.

This program reads a Logitech-style steering wheel with pygame and sends JSON
commands to the xApp over HTTP.

Data path:

    steering wheel -> pygame -> wheel_client.py -> xApp REST endpoint

The xApp expects commands like:

    {
        "seq": 1,
        "timestamp_ms": 1717800000000,
        "steering": 0.1,
        "throttle": 0.2,
        "brake": 0.0,
        "enable": true
    }

Keep the jobs separate:

    wheel_client.py      -> reads wheel input and sends command JSON
    steering_xapp.py     -> receives REST requests
    steering_service.py  -> validates commands and forwards robot payloads

Typical Logitech-style axis model:

    axis 0: steering, centered near 0.0
    axis 1: accelerator, idle near +1.0 and pressed toward -1.0
    axis 2: brake, idle near +1.0 and pressed toward -1.0
    axis 3: clutch, idle near +1.0 and pressed toward -1.0
"""

import argparse
import io
import json
import signal
import threading
import time
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional, Sequence, Tuple

import pygame


# ---------------------------------------------------------------------------
# Default settings
# ---------------------------------------------------------------------------

DEFAULT_WHEEL_CONFIG = {
    "joystick_index": 0,
    "xapp_url": "http://192.168.50.103:18080",
    "rate_hz": 10.0,
    "poll_seconds": 0.005,
    "timeout": 0.2,
    "video": False,
    "video_fps": 10.0,
    "video_timeout": 2.0,
    "steering_axis": 0,
    "throttle_axis": 1,
    "brake_axis": 2,
    "clutch_axis": 3,
    "left_paddle_button": 4,
    "right_paddle_button": 5,
    "enable_button": -1,
    "stop_button": -1,
    "steering_deadzone": 0.03,
    "pedal_idle_deadzone": 0.05,
}

"""
Concept:

Dictionary syntax:

    "key_name": value,

Examples:

    "poll_seconds": 0.005,
    "timeout": 0.2,
    "steering_axis": 0,

Button index concept:

    A button index of -1 means "disabled."  For example, if stop_button is -1,
    no wheel button is used as the stop button.

Video settings are included in the dictionary so the command-line parser and
client object have a clear place to attach video work.  The video methods lower
in the file are the remaining TODO sections.
"""


# Constants make the rest of the file easier to read.  The first few are left
# as patterns.  Add the remaining constants after the config dictionary is
# completed.
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


# ---------------------------------------------------------------------------
# Input normalization helpers
# ---------------------------------------------------------------------------

def clamp(value: float, lower: float, upper: float) -> float:
    """
    Keep a number inside a lower and upper limit.

    Example:

        clamp(1.5, 0.0, 1.0)  -> 1.0
        clamp(-0.4, 0.0, 1.0) -> 0.0
        clamp(0.7, 0.0, 1.0)  -> 0.7
    """
    return min(max(value, lower), upper)


def normalize_steering(raw_value: float, deadzone: float = STEERING_DEADZONE, invert: bool = False) -> float:
    """
    Convert a raw wheel steering value into a clean value from -1.0 to 1.0.

    Steps:

        1. Convert the raw value to float.
        2. Clamp it between -1.0 and 1.0.
        3. If the value is very close to zero, make it exactly 0.0.
        4. If `invert` is True, multiply by -1.
        5. Return the final value.

    Concept:

        Real wheels can report tiny values even when nobody is touching them.
        A deadzone prevents tiny noise from becoming robot commands.

    Function-call syntax used here:

        float(raw_value)
        clamp(value, -1.0, 1.0)
        abs(value)

    Assignment syntax:

        value = clamp(float(raw_value), -1.0, 1.0)

    `abs(value)` means "distance from zero."  For example:

        abs(-0.03) -> 0.03
    """
    value = clamp(float(raw_value), -1.0, 1.0)
    if abs(value) < deadzone:
        value = 0.0
    if invert:
        value = -value
    return value


def normalize_pedal(raw_value: float, idle_deadzone: float = PEDAL_IDLE_DEADZONE, invert: bool = False) -> float:
    """
    Convert a raw pedal axis value into a pressed amount from 0.0 to 1.0.

    Many Logitech-style pedals report:

        +1.0 when idle
        -1.0 when fully pressed

    Mapping formula:

        pressed = (1.0 - value) / 2.0

    Examples:

        raw +1.0 -> pressed 0.0
        raw  0.0 -> pressed 0.5
        raw -1.0 -> pressed 1.0

    Code pattern:

        1. Convert raw value to float.
        2. Clamp it between -1.0 and 1.0.
        3. Invert it if `invert` is True.
        4. Convert it to a pressed amount.
        5. Clamp pressed amount between 0.0 and 1.0.
        6. Return 0.0 when the pressed amount is smaller than idle_deadzone.
        7. Otherwise return the pressed amount.

    Syntax examples:

        value = clamp(float(raw_value), -1.0, 1.0)

        if invert:
            value = -value

        pressed = clamp((1.0 - value) / 2.0, 0.0, 1.0)

        if pressed < idle_deadzone:
            return 0.0

        return pressed
    """
    value = clamp(float(raw_value), -1.0, 1.0)
    if invert:
        value = -value
    pressed = clamp((1.0 - value) / 2.0, 0.0, 1.0)
    return 0.0 if pressed < idle_deadzone else pressed


def read_state(joystick: Any) -> Tuple[List[float], List[int], List[Tuple[int, int]]]:
    """
    Read all axes, buttons, and hats from a pygame joystick object.

    pygame gives separate counts for each input type:

        joystick.get_numaxes()
        joystick.get_numbuttons()
        joystick.get_numhats()

    Return shape:

        axes, buttons, hats

    Where:

        axes    -> list of float values
        buttons -> list of 0/1 values
        hats    -> list of directional pad tuples

    Code pattern:

    Axis example:

        axes = [
            round(float(joystick.get_axis(index)), AXIS_PRECISION)
            for index in range(joystick.get_numaxes())
        ]

    Function syntax:

        joystick.get_axis(index)
        joystick.get_button(index)
        joystick.get_hat(index)

    Count syntax:

        joystick.get_numaxes()
        joystick.get_numbuttons()
        joystick.get_numhats()

    List-comprehension syntax:

        new_list = [
            expression
            for item in group
        ]

    `range(joystick.get_numaxes())` creates indexes:

        0, 1, 2, ... up to one less than the number of axes
    """
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
    """
    Safely read one axis.

    If the requested index does not exist, return `default`.

    This protects the program when a wheel has fewer axes than expected.
    """
    return axes[index] if 0 <= index < len(axes) else default


def button_value(buttons: Sequence[int], index: int, default: int = 0) -> int:
    """
    Safely read one button.

    Code pattern:

    Sequence indexing syntax:

        buttons[index]

    Bounds-check syntax:

        0 <= index < len(buttons)

    Complete pattern:

        return buttons[index] if 0 <= index < len(buttons) else default
    """
    return buttons[index] if 0 <= index < len(buttons) else default


def format_axes(axes: Sequence[float]) -> str:
    """
    Format axis values for readable terminal output.

    Example output:

        S=+0.000 A=+1.000 B=+1.000 C=+1.000

    Code pattern:

    Loop through axes with `enumerate`.
    Use `AXIS_NAMES` for known axes.
    Use `X{index}` for extra axes.
    Join the formatted parts with spaces.

    Useful syntax:

        parts = []

        for index, value in enumerate(axes):
            ...

        parts.append("text")
        return " ".join(parts)

    `enumerate(axes)` gives both:

        index -> 0, 1, 2, ...
        value -> the axis value at that index

    f-string formatting example:

        f"{name}={value:+.3f}"

    `+.3f` means show a sign and three digits after the decimal point.
    """
    parts = []
    for index, value in enumerate(axes):
        name = AXIS_NAMES[index] if index < len(AXIS_NAMES) else f"X{index}"
        parts.append(f"{name}={value:+.3f}")
    return " ".join(parts)


# ---------------------------------------------------------------------------
# Wheel client class
# ---------------------------------------------------------------------------

class WheelClient:
    """
    Reads wheel input and sends commands to the xApp.

    This class owns:

        - command sequence numbers
        - xApp command and stop URLs
        - the main pygame loop
        - command JSON creation
        - HTTP POST requests
    """

    def __init__(self, args: argparse.Namespace) -> None:
        """
        Save command-line settings and build xApp URLs.

        Code pattern:

            self.args
            self.seq
            self.keep_running
            self.command_url
            self.stop_url

        URL pattern:

            base = args.xapp_url.rstrip("/")
            self.command_url = base + "/ric/v1/steering/command"
            self.stop_url = base + "/ric/v1/steering/stop"

        Attribute syntax:

            self.args = args
            self.seq = 0

        `self` means "this WheelClient object."

        String method syntax:

            args.xapp_url.rstrip("/")

        `.rstrip("/")` removes trailing slash characters from the right side of
        the URL so paths can be joined cleanly.
        """
        self.args = args
        self.seq = 0
        self.keep_running = True
        base = args.xapp_url.rstrip("/")
        self.command_url = base + "/ric/v1/steering/command"
        self.stop_url = base + "/ric/v1/steering/stop"
        self.video_url = args.video_url or (base + "/ric/v1/video/stream")
        self.video_lock = threading.Lock()
        self.video_frame: Optional[bytes] = None
        self.video_frame_id = 0
        self.video_drawn_id = -1
        self.video_window_started = False
        self.video_thread: Optional[threading.Thread] = None

    def run(self) -> None:
        """
        Main pygame loop.

        Overall flow:

            1. Initialize pygame.
            2. Initialize pygame joystick support.
            3. Check that at least one joystick exists.
            4. Open the selected joystick.
            5. Print basic wheel information.
            6. Pump pygame events each loop.
            7. Read wheel state.
            8. Send commands at `rate_hz`.
            9. Stop if the stop button is requested.
            10. Sleep briefly between polls.
            11. Always send a final stop command.
            12. Always call `pygame.quit()`.

        Concept:

            The final stop command and pygame cleanup should happen even if the
            loop exits because of Ctrl+C or another shutdown signal.

        Useful snippets:

            pygame.init()
            pygame.joystick.init()

            if pygame.joystick.get_count() == 0:
                raise SystemExit("No joystick or wheel detected by pygame.")

            joystick = pygame.joystick.Joystick(self.args.joystick_index)
            joystick.init()

            next_send = 0.0

        pygame syntax:

            pygame.event.pump()

        updates pygame's internal event state before reading joystick values.

        Loop syntax:

            while self.keep_running:
                ...

        Time syntax:

            now = time.monotonic()

        `time.monotonic()` is good for measuring elapsed time because it only
        moves forward.

        Rate syntax:

            next_send = now + (1.0 / self.args.rate_hz)

        If `rate_hz` is 20, this sends about 20 commands per second.

        Cleanup syntax:

            try:
                ...
            finally:
                self.send_stop()
                pygame.quit()
        """
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
                if now >= next_send:
                    command = self.build_command(axes, buttons)
                    response = self._post_json(self.command_url, command)
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
        """
        Start the robot camera window and background video thread.

        Concept:

            Command sending and frame fetching run at the same time.  A thread
            lets video network reads happen without blocking wheel commands.

        Function syntax from the complete reference:

            pygame.display.set_caption("Robot camera")
            pygame.display.set_mode((640, 480), pygame.RESIZABLE)
            self.video_thread = threading.Thread(target=self.video_loop, daemon=True)
            self.video_thread.start()

        Attribute updates:

            self.video_window_started = True

        Terminal message example:

            print(f"Video window started from {self.video_url}")

        ## TODO
        Complete the video startup logic.
        """
        print("video streaming TODO: start_video")

    def handle_pygame_events(self) -> None:
        """
        Process pygame window events.

        Concept:

            If the video window is open, pygame sends a `pygame.QUIT` event
            when the window close button is pressed.

        Event-loop syntax:

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.keep_running = False

        ## TODO
        Complete video window event handling.
        """
        pygame.event.pump()

    def video_loop(self) -> None:
        """
        Fetch camera frames in the background.

        Concept:

            A snapshot URL returns one image per GET request.  A stream URL
            keeps one HTTP response open and sends many image parts.

        ## TODO
        Decide whether `self.video_url` is a stream or snapshot URL and call
        the matching helper.

        Stream check example:

            if "/stream" in self.video_url:
                self.video_stream_loop()
                return

        Snapshot timing example:

            frame_interval = 1.0 / self.args.video_fps
            started = time.monotonic()
            elapsed = time.monotonic() - started
            time.sleep(max(frame_interval - elapsed, 0.001))

        Shared-frame update syntax:

            with self.video_lock:
                self.video_frame = frame
                self.video_frame_id += 1
        """
        return

    def video_stream_loop(self) -> None:
        """
        Read a multipart camera stream.

        Concept:

            `multipart/x-mixed-replace` is one HTTP response containing many
            parts.  Each part has small headers followed by one image frame.

        Request syntax from the complete reference:

            urllib.request.Request(
                self.video_url,
                headers={"Accept": "multipart/x-mixed-replace,image/jpeg"},
            )

        ## TODO
        Open the stream, read chunks, and pass bytes into
        `extract_multipart_frames`.

        Open-response syntax:

            with urllib.request.urlopen(request, timeout=self.args.video_timeout) as response:
                boundary = self.multipart_boundary(response.headers.get("Content-Type", "")) or b"--frame"
                buffer = b""

        Read-loop syntax:

            chunk = response.read(8192)
            if not chunk:
                return
            buffer += chunk
            buffer = self.extract_multipart_frames(buffer, boundary)
        """
        return

    def draw_video_frame(self) -> None:
        """
        Draw the newest camera frame into the pygame window.

        Concept:

            `pygame.image.load(io.BytesIO(frame))` turns image bytes into a
            pygame image surface.  The surface can then be scaled and drawn.

        ## TODO
        Decode `self.video_frame`, scale it to the window size, draw it, and
        call `pygame.display.flip()`.

        Lock-and-skip syntax:

            with self.video_lock:
                if self.video_frame is None or self.video_frame_id == self.video_drawn_id:
                    return
                frame = self.video_frame
                frame_id = self.video_frame_id

        Draw syntax:

            image = pygame.image.load(io.BytesIO(frame))
            window = pygame.display.get_surface()
            scaled = pygame.transform.smoothscale(image.convert(), window.get_size())
            window.blit(scaled, (0, 0))
            pygame.display.flip()
        """
        return

    def build_command(self, axes: Sequence[float], buttons: Sequence[int]) -> Dict[str, Any]:
        """
        Convert current wheel state into one xApp command dictionary.

        Command fields:

            seq: increasing command number
            timestamp_ms: current wall-clock time in milliseconds
            steering: normalized steering value
            throttle: normalized accelerator pedal value
            brake: normalized brake pedal value
            enable: True/False

        Code pattern:

            1. Start with `enable = True`.
            2. If `self.args.enable_button >= 0`, read that button.
            3. Build the command dictionary.
            4. Use `normalize_steering` for steering.
            5. Use `normalize_pedal` for throttle and brake.
            6. Increment `self.seq`.
            7. Return the command.

        Useful timestamp expression:

            int(time.time() * 1000)

        Useful axis reads:

            axis_value(axes, self.args.steering_axis, 0.0)
            axis_value(axes, self.args.throttle_axis, 1.0)
            axis_value(axes, self.args.brake_axis, 1.0)

        Dictionary-building syntax:

            command = {
                "seq": self.seq,
                "timestamp_ms": int(time.time() * 1000),
            }

        Function-call syntax with keyword arguments:

            normalize_steering(
                axis_value(axes, self.args.steering_axis, 0.0),
                deadzone=self.args.steering_deadzone,
                invert=self.args.invert_steering,
            )

        Increment syntax:

            self.seq += 1

        means the same idea as:

            self.seq = self.seq + 1
        """
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

    def command_time_ms(self) -> int:
        """
        Return current wall-clock time in milliseconds.

        Code pattern:

            int(time.time() * 1000)
        """
        return int(time.time() * 1000)

    def stop_requested(self, buttons: Sequence[int], _hats: Sequence[Tuple[int, int]]) -> bool:
        """
        Return True when the configured stop button is pressed.

        If `self.args.stop_button` is -1, no stop button is configured.

        Code pattern:

        Boolean syntax:

            self.args.stop_button >= 0

        means a stop button is configured.

        Function-call syntax:

            button_value(buttons, self.args.stop_button, default=0)

        `bool(...)` converts 0 to False and 1 to True.
        """
        return self.args.stop_button >= 0 and bool(button_value(buttons, self.args.stop_button, default=0))

    def send_stop(self) -> None:
        """
        Send the xApp stop request.

        This is called when the client exits.  It should try to send:

            POST /ric/v1/steering/stop

        The body can be an empty dictionary.

        Code pattern:

        Call `_post_json(self.stop_url, {})`.
        Print a short success message.
        Catch exceptions and print a short failure message.

        Method-call syntax:

            self._post_json(self.stop_url, {})

        Empty dictionary syntax:

            {}

        Exception syntax:

            try:
                ...
            except Exception as exc:
                print(f"stop request failed: {exc}")
        """
        try:
            response = self._post_json(self.stop_url, {})
            print("Sent stop command.")
            if response is not None:
                self.print_json_response("stop", response)
        except Exception as exc:
            print(f"stop request failed: {exc}")

    def _post_json(self, url: str, payload: Dict[str, Any]) -> Any:
        """
        Send one HTTP POST request with a JSON body.

        Steps:

            1. Convert payload dictionary to JSON text with `json.dumps`.
            2. Encode the text as UTF-8 bytes.
            3. Create `urllib.request.Request`.
            4. Set Content-Type to application/json.
            5. Use method "POST".
            6. Call `urllib.request.urlopen` with a timeout.
            7. Print HTTP errors and URL errors.

        Useful pattern:

            data = json.dumps(payload).encode("utf-8")
            request = urllib.request.Request(
                url,
                data=data,
                headers={"Content-Type": "application/json"},
                method="POST",
            )

        Code pattern:

        JSON syntax:

            json.dumps(payload)

        converts a Python dictionary into JSON text.

        Byte encoding syntax:

            text.encode("utf-8")

        HTTP request syntax:

            urllib.request.Request(url, data=data, headers=headers, method="POST")

        Open URL syntax:

            urllib.request.urlopen(request, timeout=self.args.timeout)

        Context-manager syntax:

            with urllib.request.urlopen(request, timeout=self.args.timeout) as response:
                ...

        Error handling syntax:

            except urllib.error.HTTPError as exc:
                ...

            except urllib.error.URLError as exc:
                ...
        """
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
        """
        Fetch one binary response from a URL.

        Concept:

            Images are bytes, so this helper returns `bytes` instead of a JSON
            dictionary.

        ## TODO
        Use `urllib.request.urlopen` to read one snapshot image.

        Request syntax:

            request = urllib.request.Request(
                url,
                headers={"Accept": "image/jpeg,image/png,image/x-portable-pixmap,image/x-portable-graymap"},
            )

        Read syntax:

            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.read()

        Error handling can follow the same `urllib.error.HTTPError`,
        `urllib.error.URLError`, `TimeoutError`, and `OSError` structure used in
        `_post_json`.
        """
        return None

    def extract_multipart_frames(self, buffer: bytes, boundary: bytes) -> bytes:
        """
        Extract image frames from a multipart stream buffer.

        Concept:

            Network reads may stop in the middle of a frame.  This function
            should keep unfinished bytes in `buffer` and only store complete
            image frames.

        ## TODO
        Search for the boundary marker, split complete parts, and store the
        newest image bytes in `self.video_frame`.

        Boundary search syntax:

            start = buffer.find(boundary)
            next_start = buffer.find(boundary, start + len(boundary))

        Header/body split syntax:

            header_end = part.find(b"\\r\\n\\r\\n")
            frame = part[header_end + 4:].strip(b"\\r\\n")

        Shared-frame update syntax:

            with self.video_lock:
                self.video_frame = frame
                self.video_frame_id += 1
        """
        return buffer

    @staticmethod
    def multipart_boundary(content_type: str) -> Optional[bytes]:
        """
        Read the boundary token from a multipart Content-Type header.

        Header example:

            multipart/x-mixed-replace; boundary=frame

        ## TODO
        Parse the `boundary=...` value and return it as bytes with a leading
        `--`.

        Header parsing syntax:

            for item in content_type.split(";"):
                key, _, value = item.strip().partition("=")

        Boundary token syntax:

            token = value.strip().strip('"')
            if not token.startswith("--"):
                token = "--" + token
            return token.encode("ascii", "ignore")
        """
        return None

    @staticmethod
    def parse_json_body(body: str) -> Any:
        """
        Convert response text into JSON when possible.
        """
        if not body:
            return None
        try:
            return json.loads(body)
        except ValueError:
            return body

    @staticmethod
    def print_json_response(label: str, payload: Any) -> None:
        """
        Print JSON responses in a readable format.
        """
        print(f"{label} response:")
        if isinstance(payload, (dict, list)):
            print(json.dumps(payload, indent=2, sort_keys=True))
        else:
            print(payload)


# ---------------------------------------------------------------------------
# Command-line arguments
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    """
    Read command-line options.

    `argparse` lets the same program run with different settings:

        python3 wheel_client.py --xapp-url http://127.0.0.1:8080
        python3 wheel_client.py --rate-hz 10
        python3 wheel_client.py --print-commands

    Concept:

        The movement arguments are complete.  The video arguments are present
        so the remaining video TODO methods have command-line settings to use.
    """
    parser = argparse.ArgumentParser(description="Logitech wheel client for the steering xApp")
    parser.add_argument(
        "--joystick-index",
        type=int,
        default=DEFAULT_WHEEL_CONFIG["joystick_index"],
        help="pygame joystick index",
    )
    parser.add_argument("--xapp-url", default=DEFAULT_WHEEL_CONFIG["xapp_url"], help="Base URL for the steering xApp")
    parser.add_argument("--rate-hz", type=float, default=DEFAULT_WHEEL_CONFIG["rate_hz"], help="Command publish rate")
    parser.add_argument("--poll-seconds", type=float, default=DEFAULT_WHEEL_CONFIG["poll_seconds"], help="pygame polling delay")
    parser.add_argument("--timeout", type=float, default=DEFAULT_WHEEL_CONFIG["timeout"], help="HTTP timeout seconds")
    parser.add_argument("--video", dest="video", action="store_true", default=DEFAULT_WHEEL_CONFIG["video"], help="Open a live robot camera window")
    parser.add_argument("--no-video", dest="video", action="store_false", help="Disable the robot camera window")
    parser.add_argument("--video-url", default=None, help="Override video stream or snapshot URL")
    parser.add_argument("--video-fps", type=float, default=DEFAULT_WHEEL_CONFIG["video_fps"], help="Video snapshot fetch rate")
    parser.add_argument("--video-timeout", type=float, default=DEFAULT_WHEEL_CONFIG["video_timeout"], help="Video HTTP timeout seconds")
    parser.add_argument("--steering-axis", type=int, default=DEFAULT_WHEEL_CONFIG["steering_axis"])
    parser.add_argument("--throttle-axis", type=int, default=DEFAULT_WHEEL_CONFIG["throttle_axis"])
    parser.add_argument("--brake-axis", type=int, default=DEFAULT_WHEEL_CONFIG["brake_axis"])
    parser.add_argument("--enable-button", type=int, default=DEFAULT_WHEEL_CONFIG["enable_button"], help="Button that must be held; -1 always enables")
    parser.add_argument("--stop-button", type=int, default=DEFAULT_WHEEL_CONFIG["stop_button"], help="Button that stops the client and sends xApp stop")
    parser.add_argument("--steering-deadzone", type=float, default=DEFAULT_WHEEL_CONFIG["steering_deadzone"])
    parser.add_argument("--pedal-idle-deadzone", type=float, default=DEFAULT_WHEEL_CONFIG["pedal_idle_deadzone"])
    parser.add_argument("--invert-steering", action="store_true")
    parser.add_argument("--invert-throttle", action="store_true", help="Use if the pedal reports idle -1 and pressed +1")
    parser.add_argument("--invert-brake", action="store_true", help="Use if the pedal reports idle -1 and pressed +1")
    parser.add_argument("--print-commands", action="store_true", help="Print axes and JSON command payloads while sending")
    args = parser.parse_args()
    if args.rate_hz <= 0:
        parser.error("--rate-hz must be greater than 0")
    if args.video_fps <= 0:
        parser.error("--video-fps must be greater than 0")
    return args


# ---------------------------------------------------------------------------
# Entrypoint and shutdown signals
# ---------------------------------------------------------------------------

def main() -> None:
    """
    Program entrypoint.

    Code pattern:

        1. Parse arguments.
        2. Create `WheelClient(args)`.
        3. Define a small `stop` function that sets `client.keep_running = False`.
        4. Register that function for SIGINT and SIGTERM.
        5. Call `client.run()`.

    Concept:

        SIGINT usually comes from Ctrl+C.
        SIGTERM is commonly used by tools that ask a program to shut down.

    Function-inside-function syntax:

        def stop(_signum, _frame) -> None:
            client.keep_running = False

    Signal registration syntax:

        signal.signal(signal.SIGINT, stop)
        signal.signal(signal.SIGTERM, stop)

    Object creation syntax:

        client = WheelClient(args)

    Method-call syntax:

        client.run()
    """
    args = parse_args()
    client = WheelClient(args)

    def stop(_signum, _frame) -> None:
        client.keep_running = False

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    client.run()


if __name__ == "__main__":
    main()
