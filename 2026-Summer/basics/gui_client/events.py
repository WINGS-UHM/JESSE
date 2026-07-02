#!/usr/bin/env python3
"""
Small in-memory event log for dashboard messages.

`deque(maxlen=7)` keeps only the newest seven messages.  When an eighth message
is added, the oldest one is automatically removed.
"""

import time
from collections import deque
from typing import Deque, Iterator, Tuple


class EventLog:
    def __init__(self, max_entries: int = 7) -> None:
        self.events: Deque[Tuple[float, str, str]] = deque(maxlen=max_entries)

    def add(self, kind: str, message: str) -> None:
        self.events.appendleft((time.monotonic(), kind, message))

    def __iter__(self) -> Iterator[Tuple[float, str, str]]:
        return iter(self.events)
