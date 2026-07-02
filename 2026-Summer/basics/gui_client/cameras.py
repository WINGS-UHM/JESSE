#!/usr/bin/env python3
"""
Camera topic names used by number keys in the GUI.

Key mapping used in the dashboard:

    1 -> RGB
    2 -> Depth
    3 -> IR
    4 -> YOLO
"""

import urllib.parse
from typing import Tuple

from .constants import DEPTH_IMAGE_TOPIC


CAMERA_TOPICS: Tuple[Tuple[str, str], ...] = (
    ("RGB", "/depth_cam/rgb0/image_raw"),
    ("Depth", DEPTH_IMAGE_TOPIC),
    ("IR", "/depth_cam/ir0/image_raw"),
    ("YOLO", "/yolo/object_image"),
)


def camera_name_for_topic(topic: str) -> str:
    for name, value in CAMERA_TOPICS:
        if value == topic:
            return name
    return topic


def topic_from_url(url: str, default: str = "/depth_cam/rgb0/image_raw") -> str:
    parsed = urllib.parse.urlsplit(url)
    return dict(urllib.parse.parse_qsl(parsed.query)).get("topic", default)
