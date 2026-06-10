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
import json
import signal
import time
import urllib.error
import urllib.request
from typing import Any, Dict, List, Sequence, Tuple

import pygame


# ---------------------------------------------------------------------------
# Default settings
# ---------------------------------------------------------------------------

DEFAULT_WHEEL_CONFIG = {
    "joystick_index": 0,
    "xapp_url": "http://127.0.0.1:8080",
    "rate_hz": 20.0,
    # TODO: add the remaining default settings from the notes below.
}

"""
## TODO
Add the remaining keys to `DEFAULT_WHEEL_CONFIG`.

Dictionary syntax:

    "key_name": value,

Examples:

    "poll_seconds": 0.005,
    "timeout": 0.2,
    "steering_axis": 0,

Settings to add:

    poll_seconds: small sleep between pygame polls, default 0.005
    timeout: HTTP timeout seconds, default 0.2
    steering_axis: wheel steering axis index, default 0
    throttle_axis: accelerator pedal axis index, default 1
    brake_axis: brake pedal axis index, default 2
    clutch_axis: clutch pedal axis index, default 3
    left_paddle_button: left paddle button index, default 4
    right_paddle_button: right paddle button index, default 5
    enable_button: button that must be held, default -1
    stop_button: button that stops the client, default -1
    steering_deadzone: ignore tiny steering movement, default 0.03
    pedal_idle_deadzone: ignore tiny pedal movement, default 0.05

Why use -1 for buttons?

    A button index of -1 means "disabled."  For example, if stop_button is -1,
    no wheel button is used as the stop button.
"""


# Constants make the rest of the file easier to read.  The first few are left
# as patterns.  Add the remaining constants after the config dictionary is
# completed.
STEERING_AXIS_INDEX = DEFAULT_WHEEL_CONFIG["steering_axis"]
# TODO: add ACCEL_AXIS_INDEX, BRAKE_AXIS_INDEX, and CLUTCH_AXIS_INDEX.
# TODO: add LEFT_PADDLE_BUTTON and RIGHT_PADDLE_BUTTON.
# TODO: add STEERING_DEADZONE and PEDAL_IDLE_DEADZONE.
#
# Constant syntax:
#
#     CONSTANT_NAME = DEFAULT_WHEEL_CONFIG["config_key"]
#
# Example:
#
#     ACCEL_AXIS_INDEX = DEFAULT_WHEEL_CONFIG["throttle_axis"]
#
# What the square brackets mean:
#
#     DEFAULT_WHEEL_CONFIG["throttle_axis"]
#
# reads the value stored under the key `"throttle_axis"` in the dictionary.

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

    Why use a deadzone?

        Real wheels can report tiny values even when nobody is touching them.
        A deadzone prevents tiny noise from becoming robot commands.

    ## TODO
    Implement the steps above.

    Function-call syntax used here:

        float(raw_value)
        clamp(value, -1.0, 1.0)
        abs(value)

    Assignment syntax:

        value = clamp(float(raw_value), -1.0, 1.0)

    `abs(value)` means "distance from zero."  For example:

        abs(-0.03) -> 0.03
    """
    # TODO: normalize steering input.


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

    ## TODO
    Implement this flow:

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
    # TODO: normalize pedal input.


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

    ## TODO
    Use list comprehensions to build each list.

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
    # TODO: read axes, buttons, and hats from pygame.


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

    ## TODO
    Follow the same pattern as `axis_value`.

    Sequence indexing syntax:

        buttons[index]

    Bounds-check syntax:

        0 <= index < len(buttons)

    Complete pattern:

        return buttons[index] if 0 <= index < len(buttons) else default
    """
    # TODO: return the button value or the default.


def format_axes(axes: Sequence[float]) -> str:
    """
    Format axis values for readable terminal output.

    Example output:

        S=+0.000 A=+1.000 B=+1.000 C=+1.000

    ## TODO
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
    # TODO: format axis values as a single string.


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

        ## TODO
        Initialize:

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
        # TODO: initialize the client object.

    def run(self) -> None:
        """
        Main pygame loop.

        Overall flow:

            1. Initialize pygame.
            2. Initialize pygame joystick support.
            3. Check that at least one joystick exists.
            4. Open the selected joystick.
            5. Print basic wheel information.
            6. Repeatedly pump pygame events.
            7. Read wheel state.
            8. Send commands at `rate_hz`.
            9. Stop if the stop button is requested.
            10. Sleep briefly between polls.
            11. Always send a final stop command.
            12. Always call `pygame.quit()`.

        Why `try/finally`?

            The final stop command and pygame cleanup should happen even if the
            loop exits because of Ctrl+C or another shutdown signal.

        ## TODO
        Implement the flow above.

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
        # TODO: implement pygame setup, polling loop, command sending, cleanup.

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

        ## TODO
        Implement this flow:

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
        # TODO: build and return one command dictionary.

    def stop_requested(self, buttons: Sequence[int], _hats: Sequence[Tuple[int, int]]) -> bool:
        """
        Return True when the configured stop button is pressed.

        If `self.args.stop_button` is -1, no stop button is configured.

        ## TODO
        Use `button_value` to safely read the stop button.

        Boolean syntax:

            self.args.stop_button >= 0

        means a stop button is configured.

        Function-call syntax:

            button_value(buttons, self.args.stop_button, default=0)

        `bool(...)` converts 0 to False and 1 to True.
        """
        # TODO: return whether stop was requested.

    def send_stop(self) -> None:
        """
        Send the xApp stop request.

        This is called when the client exits.  It should try to send:

            POST /ric/v1/steering/stop

        The body can be an empty dictionary.

        ## TODO
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
        # TODO: send final stop request.

    def _post_json(self, url: str, payload: Dict[str, Any]) -> None:
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

        ## TODO
        Implement the request and error handling.

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
        # TODO: POST JSON to the xApp.


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

    The first argument is completed as the pattern.  Add the rest from the TODO
    list.

    ## TODO
    Add arguments for:

        --xapp-url
        --rate-hz
        --poll-seconds
        --timeout
        --steering-axis
        --throttle-axis
        --brake-axis
        --enable-button
        --stop-button
        --steering-deadzone
        --pedal-idle-deadzone
        --invert-steering
        --invert-throttle
        --invert-brake
        --print-commands
    """
    parser = argparse.ArgumentParser(description="Logitech wheel client for the steering xApp")
    parser.add_argument(
        "--joystick-index",
        type=int,
        default=DEFAULT_WHEEL_CONFIG["joystick_index"],
        help="pygame joystick index",
    )
    # TODO: add the remaining parser.add_argument(...) calls.
    #
    # argparse syntax:
    #
    #     parser.add_argument("--name", type=some_type, default=value, help="text")
    #
    # Examples:
    #
    #     parser.add_argument("--rate-hz", type=float, default=20.0)
    #     parser.add_argument("--xapp-url", default="http://127.0.0.1:8080")
    #
    # Boolean flag syntax:
    #
    #     parser.add_argument("--print-commands", action="store_true")
    #
    # `action="store_true"` means the value is False unless the flag appears on
    # the command line.
    return parser.parse_args()


# ---------------------------------------------------------------------------
# Entrypoint and shutdown signals
# ---------------------------------------------------------------------------

def main() -> None:
    """
    Program entrypoint.

    ## TODO
    Implement this flow:

        1. Parse arguments.
        2. Create `WheelClient(args)`.
        3. Define a small `stop` function that sets `client.keep_running = False`.
        4. Register that function for SIGINT and SIGTERM.
        5. Call `client.run()`.

    Why signals?

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
    # TODO: parse args, create client, register signals, run client.


if __name__ == "__main__":
    main()
