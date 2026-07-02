#!/usr/bin/env python3
"""
Small helper functions used by the GUI client.

These helpers are mostly complete because many later TODO sections depend on
them.  Use them as reference patterns for type conversion, bounds checking, and
list building.
"""

import argparse
from typing import Any, List, Sequence, Tuple

from .constants import AXIS_NAMES, AXIS_PRECISION, PEDAL_IDLE_DEADZONE, STEERING_DEADZONE


def clamp(value: float, lower: float, upper: float) -> float:
    """
    Keep a number inside a lower and upper limit.

    Examples:

        clamp(1.5, 0.0, 1.0)  -> 1.0
        clamp(-0.4, 0.0, 1.0) -> 0.0
        clamp(0.7, 0.0, 1.0)  -> 0.7
    """
    return min(max(value, lower), upper)


def normalize_steering(raw_value: float, deadzone: float = STEERING_DEADZONE, invert: bool = False) -> float:
    """
    Convert steering axis input into -1.0 through 1.0.

    Set `deadzone` to `0.03` by default so tiny wheel noise becomes `0.0`.
    """
    value = clamp(float(raw_value), -1.0, 1.0)
    if abs(value) < deadzone:
        value = 0.0
    if invert:
        value = -value
    return value


def normalize_pedal(raw_value: float, idle_deadzone: float = PEDAL_IDLE_DEADZONE, invert: bool = False) -> float:
    """
    Convert a pedal axis into 0.0 through 1.0.

    Logitech-style pedals often report:

        +1.0 when idle
        -1.0 when fully pressed
    """
    value = clamp(float(raw_value), -1.0, 1.0)
    if invert:
        value = -value
    pressed = clamp((1.0 - value) / 2.0, 0.0, 1.0)
    return 0.0 if pressed < idle_deadzone else pressed


def read_state(joystick: Any) -> Tuple[List[float], List[int], List[Tuple[int, int]]]:
    """
    Read axes, buttons, and hats from a pygame joystick object.

    Function-call syntax:

        joystick.get_axis(index)
        joystick.get_button(index)
        joystick.get_hat(index)
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
    return axes[index] if 0 <= index < len(axes) else default


def button_value(buttons: Sequence[int], index: int, default: int = 0) -> int:
    return buttons[index] if 0 <= index < len(buttons) else default


def format_axes(axes: Sequence[float]) -> str:
    parts = []
    for index, value in enumerate(axes):
        name = AXIS_NAMES[index] if index < len(AXIS_NAMES) else f"X{index}"
        parts.append(f"{name}={value:+.3f}")
    return " ".join(parts)


def parse_int_list(value: str, expected: int, parser: argparse.ArgumentParser, name: str) -> List[int]:
    """
    Convert a comma-separated string into a list of integers.

    Example:

        "5,4,7,11,6,10" -> [5, 4, 7, 11, 6, 10]
    """
    try:
        items = [int(item.strip()) for item in value.split(",")]
    except ValueError:
        parser.error(f"{name} must be a comma-separated list of integers")
    if len(items) != expected:
        parser.error(f"{name} must contain {expected} integers")
    return items
