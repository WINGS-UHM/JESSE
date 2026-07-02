#!/usr/bin/env python3
"""
Shared numeric settings for the modular GUI wheel client.

Most values in this file are complete reference values.  Keeping these in one
place prevents every module from hardcoding numbers separately.

Dictionary syntax:

    "setting_name": value,

Examples:

    "rate_hz": 10.0,
    "video_width": 640,
    "arm_step": 10,
"""

DEFAULT_GUI_CONFIG = {
    "joystick_index": 0,
    "xapp_url": "http://192.168.50.247:8080",
    "rate_hz": 10.0,
    "active_heartbeat_seconds": 0.25,
    "command_deadband": 0.02,
    "poll_seconds": 0.005,
    "timeout": 5.0,
    "video": True,
    "video_width": 640,
    "video_height": 400,
    "video_quality": 60,
    "video_topic": "/depth_cam/rgb0/image_raw",
    "video_timeout": 8.0,
    "steering_axis": 0,
    "throttle_axis": 1,
    "brake_axis": 2,
    "clutch_axis": 3,
    "calibrate_pedals": True,
    "left_paddle_button": 4,
    "right_paddle_button": 5,
    "enable_button": -1,
    "stop_button": -1,
    "arm_enabled": True,
    "arm_buttons": "5,4,7,11,6,10",
    "arm_default_button": 0,
    "arm_step": 10,
    "arm_repeat_hz": 5.0,
    "arm_duration": 0.2,
    "arm_launch_duration": 1.0,
    "arm_reset_on_exit": True,
    "arm_reset_duration": 1.0,
    "clutch_reverse_threshold": 0.5,
    "steering_deadzone": 0.03,
    "pedal_idle_deadzone": 0.05,
}

AXIS_PRECISION = 3
AXIS_NAMES = ("S", "A", "B", "C")
STEERING_DEADZONE = DEFAULT_GUI_CONFIG["steering_deadzone"]
PEDAL_IDLE_DEADZONE = DEFAULT_GUI_CONFIG["pedal_idle_deadzone"]

# Servo ids used by the robot arm.
ARM_SERVO_IDS = (1, 2, 3, 4, 5, 10)

# `None` means no custom launch pose is set.  That is intentional.
ARM_LAUNCH_POSITIONS = {1: None, 2: None, 3: None, 4: None, 5: None, 10: None}

ARM_ROS_WORKSPACE_DEFAULT_POSITIONS = {1: 500, 2: 725, 3: 50, 4: 150, 5: 500, 10: 500}
ARM_LIMITS = {
    1: (100, 1000),
    2: (100, 765),
    3: (0, 468),
    4: (88, 654),
    5: (125, 700),
    10: (200, 700),
}

DEPTH_IMAGE_TOPIC = "/depth_cam/depth0/image_raw"
