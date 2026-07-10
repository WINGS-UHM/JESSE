#!/usr/bin/env python3

import argparse

from .constants import DEFAULT_GUI_CONFIG
from .helpers import parse_int_list


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Modular pygame GUI client for the steering xApp")
    parser.add_argument("--joystick-index", type=int, default=DEFAULT_GUI_CONFIG["joystick_index"], help="pygame joystick index")
    parser.add_argument("--xapp-url", default=DEFAULT_GUI_CONFIG["xapp_url"], help="Base URL for the steering xApp")
    parser.add_argument("--rate-hz", type=float, default=DEFAULT_GUI_CONFIG["rate_hz"], help="Command publish rate")
    parser.add_argument("--active-heartbeat-seconds", type=float, default=DEFAULT_GUI_CONFIG["active_heartbeat_seconds"], help="Repeat unchanged non-zero commands at this interval")
    parser.add_argument("--command-deadband", type=float, default=DEFAULT_GUI_CONFIG["command_deadband"], help="Minimum normalized command change that triggers a new POST")
    parser.add_argument("--poll-seconds", type=float, default=DEFAULT_GUI_CONFIG["poll_seconds"], help="pygame polling delay")
    parser.add_argument("--timeout", type=float, default=DEFAULT_GUI_CONFIG["timeout"], help="HTTP timeout seconds")
    parser.add_argument("--video", dest="video", action="store_true", default=DEFAULT_GUI_CONFIG["video"], help="Open a live robot camera window while sending wheel commands")
    parser.add_argument("--no-video", dest="video", action="store_false", help="Disable the robot camera window")
    parser.add_argument("--video-url", default=None, help="Override video snapshot URL")
    parser.add_argument("--video-width", type=int, default=DEFAULT_GUI_CONFIG["video_width"], help="Requested compressed video width")
    parser.add_argument("--video-height", type=int, default=DEFAULT_GUI_CONFIG["video_height"], help="Requested compressed video height")
    parser.add_argument("--video-quality", type=int, default=DEFAULT_GUI_CONFIG["video_quality"], help="Requested JPEG quality")
    parser.add_argument("--video-topic", default=DEFAULT_GUI_CONFIG["video_topic"], help="ROS image topic requested through the xApp video proxy")
    parser.add_argument("--video-timeout", type=float, default=DEFAULT_GUI_CONFIG["video_timeout"], help="Video snapshot HTTP timeout seconds")
    parser.add_argument("--steering-axis", type=int, default=DEFAULT_GUI_CONFIG["steering_axis"])
    parser.add_argument("--throttle-axis", type=int, default=DEFAULT_GUI_CONFIG["throttle_axis"])
    parser.add_argument("--brake-axis", type=int, default=DEFAULT_GUI_CONFIG["brake_axis"])
    parser.add_argument("--clutch-axis", type=int, default=DEFAULT_GUI_CONFIG["clutch_axis"])
    parser.add_argument("--calibrate-pedals", dest="calibrate_pedals", action="store_true", default=DEFAULT_GUI_CONFIG["calibrate_pedals"], help="Treat current pedal positions at startup as idle")
    parser.add_argument("--no-calibrate-pedals", dest="calibrate_pedals", action="store_false", help="Use fixed pedal idle convention: idle +1.0, pressed toward -1.0")
    parser.add_argument("--enable-button", type=int, default=DEFAULT_GUI_CONFIG["enable_button"], help="Button that must be held; -1 always enables")
    parser.add_argument("--stop-button", type=int, default=DEFAULT_GUI_CONFIG["stop_button"], help="Button that stops the client and sends xApp stop")
    parser.add_argument("--arm-enabled", dest="arm_enabled", action="store_true", default=DEFAULT_GUI_CONFIG["arm_enabled"])
    parser.add_argument("--no-arm", dest="arm_enabled", action="store_false", help="Disable arm button controls")
    parser.add_argument("--arm-buttons", default=DEFAULT_GUI_CONFIG["arm_buttons"], help="Comma-separated buttons for servo ids 1,2,3,4,5,10")
    parser.add_argument("--arm-default-button", type=int, default=DEFAULT_GUI_CONFIG["arm_default_button"], help="Button that sends the user default arm pose, or ROS workspace default if user default is unset; -1 disables")
    parser.add_argument("--arm-step", type=int, default=DEFAULT_GUI_CONFIG["arm_step"], help="Servo pulse step per arm repeat")
    parser.add_argument("--arm-repeat-hz", type=float, default=DEFAULT_GUI_CONFIG["arm_repeat_hz"], help="Arm button hold repeat rate")
    parser.add_argument("--arm-duration", type=float, default=DEFAULT_GUI_CONFIG["arm_duration"], help="Arm servo command duration seconds")
    parser.add_argument("--arm-launch-duration", type=float, default=DEFAULT_GUI_CONFIG["arm_launch_duration"], help="Optional launch arm pose command duration seconds")
    parser.add_argument("--arm-reset-on-exit", dest="arm_reset_on_exit", action="store_true", default=DEFAULT_GUI_CONFIG["arm_reset_on_exit"], help="Reset arm to default pose when the client exits")
    parser.add_argument("--no-arm-reset-on-exit", dest="arm_reset_on_exit", action="store_false", help="Do not reset arm pose when the client exits")
    parser.add_argument("--arm-reset-duration", type=float, default=DEFAULT_GUI_CONFIG["arm_reset_duration"], help="Arm reset command duration seconds")
    parser.add_argument("--clutch-reverse-threshold", type=float, default=DEFAULT_GUI_CONFIG["clutch_reverse_threshold"], help="Normalized clutch value that reverses arm button direction")
    parser.add_argument("--steering-deadzone", type=float, default=DEFAULT_GUI_CONFIG["steering_deadzone"])
    parser.add_argument("--pedal-idle-deadzone", type=float, default=DEFAULT_GUI_CONFIG["pedal_idle_deadzone"])
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
    if args.video_width <= 0:
        parser.error("--video-width must be greater than 0")
    if args.video_height <= 0:
        parser.error("--video-height must be greater than 0")
    if not 1 <= args.video_quality <= 100:
        parser.error("--video-quality must be between 1 and 100")
    if args.arm_repeat_hz <= 0:
        parser.error("--arm-repeat-hz must be greater than 0")
    if args.arm_launch_duration <= 0:
        parser.error("--arm-launch-duration must be greater than 0")
    if args.arm_reset_duration <= 0:
        parser.error("--arm-reset-duration must be greater than 0")
    args.arm_buttons = parse_int_list(args.arm_buttons, expected=6, parser=parser, name="--arm-buttons")
    return args
