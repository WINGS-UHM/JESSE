#!/usr/bin/env python3

import urllib.parse
from typing import Tuple

from .constants import DEPTH_IMAGE_TOPIC


CAMERA_TOPICS: Tuple[Tuple[str, str], ...] = (
    ("RGB", "/depth_cam/rgb0/image_raw"),
    ("Depth", DEPTH_IMAGE_TOPIC),
    ("IR", "/depth_cam/ir0/image_raw"),
    ("YOLO", "/yolo/object_image"),
)

HAT_CAMERA_BINDINGS = {
    (0, 1): 0,    # up
    (-1, 0): 1,   # left
    (0, -1): 2,   # down
    (1, 0): 3,    # right
}

HAT_CAMERA_LABELS = {
    (0, 1): "Up RGB",
    (-1, 0): "Left Depth",
    (0, -1): "Down IR",
    (1, 0): "Right YOLO",
}


def camera_name_for_topic(topic: str) -> str:
    for name, value in CAMERA_TOPICS:
        if value == topic:
            return name
    return topic


def topic_from_url(url: str, default: str = "/depth_cam/rgb0/image_raw") -> str:
    parsed = urllib.parse.urlsplit(url)
    return dict(urllib.parse.parse_qsl(parsed.query)).get("topic", default)
