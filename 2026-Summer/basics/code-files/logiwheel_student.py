"""
Student Copy: Logitech Wheel Input Logger

This file is a commented version of logiwheel.py.

What the program does:
1. Connects to a Logitech wheel or joystick using pygame.
2. Prints information about the device.
3. Repeatedly checks the wheel, pedals, and buttons.
4. Prints axes or buttons only when their values change.
5. Cleans up pygame when the user presses Ctrl+C.
"""

import time

import pygame


# ---------------------------------------------------------------------------
# SETTINGS
# ---------------------------------------------------------------------------

# How long the loop waits between controller checks.
# A smaller number checks more often. A larger number checks less often.
POLL_SECONDS = 0.05

# How many decimal places to keep when printing axis values.
AXIS_PRECISION = 3

# Controllers sometimes report tiny changes even when nobody touches them.
# This threshold prevents tiny idle noise from printing forever.
AXIS_CHANGE_LOG_THRESHOLD = 0.02

# Friendly names for the first four axes.
# For our wheel, we expect the axes list to look like:
# [S, A, B, C]
AXIS_NAMES = ("S", "A", "B", "C")


# ---------------------------------------------------------------------------
# TERMINAL COLORS
# ---------------------------------------------------------------------------


class Color:
    """
    ANSI color codes for terminal output.

    These are special text sequences. The terminal reads them as instructions
    like "start blue text" or "reset back to normal".
    """

    RESET = "\033[0m"
    DIM = "\033[2m"
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN = "\033[36m"


def paint(text, color):
    """
    Return text wrapped in a terminal color.

    Example:
    paint("AXES", Color.BLUE)
    """
    return f"{color}{text}{Color.RESET}"


def label(text, color):
    """
    Create a colored label with a colon.

    The <10 formatting keeps labels lined up:
    AXES:
    BUTTONS:
    """
    return paint(f"{text + ':':<10}", color)


# ---------------------------------------------------------------------------
# PRINTING HELPERS
# ---------------------------------------------------------------------------


def print_device_summary(joystick):
    """
    Print startup information about the connected controller.

    The joystick object comes from pygame. It gives us methods like:
    - get_name()
    - get_numaxes()
    - get_numbuttons()
    - get_numhats()
    """
    print(paint("\nLOGITECH WHEEL BASIC INPUT LOGGER", Color.CYAN))
    print(paint("-" * 40, Color.DIM))
    print(f"{label('Device', Color.GREEN)} {joystick.get_name()}")
    print(f"{label('Axes', Color.BLUE)} {joystick.get_numaxes()}")
    print(f"{label('Buttons', Color.MAGENTA)} {joystick.get_numbuttons()}")
    print(f"{label('Hats', Color.YELLOW)} {joystick.get_numhats()}")
    print(paint("-" * 40, Color.DIM))
    print(paint("Only axes and button changes are printed. Ctrl+C exits.\n", Color.DIM))


def format_axes(axes):
    """
    Convert the axes list into readable text.

    Example input:
    [0.0, 1.0, -0.5, 1.0]

    Example output:
    S=+0.000 A=+1.000 B=-0.500 C=+1.000
    """
    named_axes = []

    for index, value in enumerate(axes):
        if index < len(AXIS_NAMES):
            name = AXIS_NAMES[index]
        else:
            name = f"X{index}"

        named_axes.append(f"{name}={value:+.3f}")

    return " ".join(named_axes)


def print_buttons(buttons):
    """
    Print which buttons are currently pressed.

    pygame reports each button as:
    - 0 if not pressed
    - 1 if pressed
    """
    pressed = [
        index
        for index, value in enumerate(buttons)
        if value == 1
    ]
    print(f"{label('BUTTONS', Color.MAGENTA)} pressed={pressed}")


# ---------------------------------------------------------------------------
# CONTROLLER READING
# ---------------------------------------------------------------------------


def read_state(joystick):
    """
    Read axes, buttons, and hats from the controller.

    Returns three lists:
    - axes: wheel and pedal values
    - buttons: button pressed states
    - hats: directional pad states, if the controller has them
    """
    axes = [
        round(joystick.get_axis(index), AXIS_PRECISION)
        for index in range(joystick.get_numaxes())
    ]
    buttons = [
        joystick.get_button(index)
        for index in range(joystick.get_numbuttons())
    ]
    hats = [
        joystick.get_hat(index)
        for index in range(joystick.get_numhats())
    ]
    return axes, buttons, hats


def axes_changed_enough(current_axes, last_axes):
    """
    Decide whether the axes changed enough to print.

    We do not use a plain current_axes != last_axes check because real
    controller values can wiggle slightly while idle. The threshold keeps the
    terminal readable.
    """
    if last_axes is None:
        return True

    if len(current_axes) != :  # Check if the length of axes changed, variables: `current_axes` and `last_axes`, function: len()
        return True

    for index, value in enumerate(current_axes):
        change = abs(value - last_axes[index])

        if change > AXIS_CHANGE_LOG_THRESHOLD:
            return True

    return False


# ---------------------------------------------------------------------------
# MAIN PROGRAM
# ---------------------------------------------------------------------------


def main():
    """
    Run the basic input logger.

    The program keeps polling the controller in a while loop. It only prints
    when axes or buttons change.
    """
    pygame.init()  # Initialize pygame to set up the library and prepare it for use.
    pygame.joystick.init() # Initialize the joystick module to detect and manage joystick devices.

    if pygame.joystick.get_count() == 0:
        print(paint("No joystick or wheel detected.", Color.RED))
        return 1

    joystick = pygame.joystick.Joystick(0)
    joystick.init()

    print_device_summary(joystick)

    # Read the first state and store it as the baseline.
    # This prevents the program from printing a fake "change" at startup.
    pygame.event.pump()
    initial_axes, initial_buttons, _ = read_state(joystick)

    last_axes = initial_axes
    last_buttons = initial_buttons

    try:
        while True:
            # pygame.event.pump() lets pygame process controller updates.
            pygame.event.pump()

            axes, buttons, _ = read_state(joystick)

            if axes_changed_enough(axes, last_axes):
                print(f"{label('AXES', Color.BLUE)} {format_axes(axes)}")
                last_axes = axes

            if :  # Use inequality operator to check for changes `buttons` and `last_buttons`
                print_buttons(buttons)
                last_buttons = buttons

            time.sleep(POLL_SECONDS)

    except KeyboardInterrupt:
        # This runs when the user presses Ctrl+C.
        print(paint("\nStopped.", Color.DIM))
        return 0

    finally:
        # This runs whether the program stops normally or by Ctrl+C.
        pygame.quit()


if __name__ == "__main__":
    raise SystemExit(main())


# ---------------------------------------------------------------------------
# ADVANCED HELD-INPUT LOGGER
# ---------------------------------------------------------------------------
#
# The advanced version below is copied from logiwheel.py and commented out.
# It adds:
# - repeated logs while a pedal or wheel direction is held
# - STATUS text such as "accelerating right" or "reversing left"
# - status colors for idle, accelerating, and reversing
#
# To use it:
# 1. Comment out the if __name__ == "__main__" block above.
# 2. Uncomment the advanced constants and functions below.
# 3. Add this at the bottom:
#
#    
#
# HELD_AXIS_LOG_SECONDS = 0.25   # How often to repeat logs while holding a pedal or wheel direction.
# STEERING_AXIS_INDEX = 0        # The index of the steering axis in the axes list. For our wheel, this is 0.
# ACCEL_AXIS_INDEX = 1           # The index of the acceleration axis in the axes list. For our wheel, this is 1.
# BRAKE_AXIS_INDEX = 2           # The index of the brake axis in the axes list. For our wheel, this is 2.
# STEERING_DEADZONE = 0.03       # The threshold for considering the steering axis as idle.
# PEDAL_ACTIVE_THRESHOLD = 0.95  # The threshold for considering a pedal as active.


# def axes_are_active(axes):
#     """
#     Return True when steering or pedals are active.
#     """
#     if len(axes) <= STEERING_AXIS_INDEX:
#         return False

#     steering_active = abs(axes[STEERING_AXIS_INDEX]) > STEERING_DEADZONE
#     pedal_active = any(
#         value < PEDAL_ACTIVE_THRESHOLD
#         for value in axes[1:]
#     )
#     return !!!  # Use logical `or` to check if either steering or pedals are active, variables: `steering_active` and `pedal_active`


# def pedal_is_pressed(axes, index):
#     """
#     Return True if a pedal axis is below the active threshold.
#     """
#     return len(axes)  index  axes[index]  PEDAL_ACTIVE_THRESHOLD  # Check if length of axes is greater than index
#                                                                        # and if the value at that index is less than the active threshold, 
#                                                                        # variables: `axes`, `index`, and `PEDAL_ACTIVE_THRESHOLD` , operators: `>`, `<` `and`


# def get_expected_status(axes):
#     """
#     Convert raw axes into a robot-style status string.
#     """
#     status = []

#     if len(axes)  STEERING_AXIS_INDEX:  # IDLE if there are not enough axes to include steering
#         return "idle"                     # Check if length of axes is less than or equal to the steering axis index, variables: `axes` and `STEERING_AXIS_INDEX`

#     if function_name(axes, ACCEL_AXIS_INDEX):  # Check if the acceleration pedal is pressed using the `pedal_is_pressed` function, variables: `axes` and `ACCEL_AXIS_INDEX`
#         status.append("accelerating")

#     if function_name(axes, BRAKE_AXIS_INDEX):  # Check if the brake pedal is pressed using the `pedal_is_pressed` function, variables: `axes` and `BRAKE_AXIS_INDEX`
#         status.append("reversing")

#     steering = axes[STEERING_AXIS_INDEX]
#     if steering < -STEERING_DEADZONE:
#         status.append("left")
#     elif steering > STEERING_DEADZONE:
#         status.append("right")

#     if not status:
#         return "idle"

#     return " ".join(status)


# def color_status(status):
#     """
#     Color the status text based on the main action.
#     """
#     if status == "idle":
#         return paint(status, Color.YELLOW)

#     if "accelerating" in status:
#         return paint(status, Color.GREEN)

#     if "reversing" in status:
#         return paint(status, Color.RED)

#     return !!!  # Return the the value of `status`  


# def print_advanced_axes(axes, name="AXES"):
#     """
#     Print raw axes and expected robot status on the same line.
#     """
#     axes_text = format_axes(axes)
#     status_text = (
#         f"{paint('STATUS:', Color.DIM)} "
#         f"{color_status(get_expected_status(axes))}"
#     )
#     print(f"{label(name, Color.BLUE)} {axes_text}      {status_text}")


# def advanced_main():
#     """
#     Run the advanced logger that also repeats held inputs.
#     """
#     pygame.init()
#     pygame.joystick.init()

#     if pygame.joystick.get_count() == 0:
#         print(paint("No joystick or wheel detected.", Color.RED))
#         return 1

#     joystick = pygame.joystick.Joystick(0)
#     joystick.init()

#     print_device_summary(joystick)
#     pygame.event.pump()
#     initial_axes, initial_buttons, _ = read_state(joystick)

#     last_axes = initial_axes
#     last_buttons = initial_buttons
#     last_held_axis_log = 0.0
#     axes_changed_after_startup = False

#     try:
#         while :   # Add some condition remember we have boolean `True`, `False` or you can add a counter to recoord only `n` number of logs
#             pygame.event.pump()
#             axes, buttons, _ = read_state(joystick)
#             now = time.monotonic()

#             if : # Check if axes changed enough to log using the `axes_changed_enough` function, variables: `axes` and `last_axes`
#                 print_advanced_axes(axes)
#                 last_axes = axes
#                 last_held_axis_log = now
#                 axes_changed_after_startup = True
#             elif (
#                 axes_changed_after_startup
#                 operator axes_are_active(axes)
#                 operator now - last_held_axis_log >= HELD_AXIS_LOG_SECONDS    # replace the operator with the correct logical operator, opttions `and`, `or`, `>=`, `<=`, `>`, `<`
#             ):
#                 print_advanced_axes(axes, "AXES held")
#                 last_held_axis_log = now

#             if buttons != last_buttons:
#                 print_buttons(buttons)
#                 last_buttons = buttons

#             time.sleep(POLL_SECONDS)
#     except KeyboardInterrupt:
#         print(paint("\nStopped.", Color.DIM))
#         return 0
#     finally:
#         pygame.quit()
# if __name__ == "__main__":
#     raise SystemExit(advanced_main())