#!/usr/bin/env python3
"""
GUI-specific video behavior.

This mixin overrides selected methods from `WheelControlClient`:

    start_video()
    video_stream_loop()
    extract_multipart_frames()

It also adds camera switching with number keys.
"""

import threading
import time
import urllib.error
import urllib.parse
import urllib.request

from .cameras import CAMERA_TOPICS, camera_name_for_topic, topic_from_url


class GuiVideoMixin:
    def start_video(self) -> None:
        """
        Start the dashboard window.

        Concrete GUI values:

            window width: 1120
            window height: 720
            title: "Steering xApp dashboard"
            base font: consolas size 18
            small font: consolas size 15
            title font: consolas size 22 bold
        """
        self.video_window_started = True
        self.pygame.display.set_caption("Steering xApp dashboard")
        self.pygame.display.set_mode((1120, 720), self.pygame.RESIZABLE)
        self.font = self.pygame.font.SysFont("consolas", 18)
        self.small_font = self.pygame.font.SysFont("consolas", 15)
        self.title_font = self.pygame.font.SysFont("consolas", 22, bold=True)
        self.video_thread = threading.Thread(target=self.video_loop, daemon=True)
        self.video_thread.start()
        self.add_event("info", f"video={self.active_topic_name()}")
        print(f"Dashboard video started from {self.video_url}")

    def video_stream_loop(self) -> None:
        """
        Read a stream while allowing camera switching.

        Concept:

            `video_generation` changes when the camera topic changes.  The
            stream loop should stop reading the old response when generation
            changes.

        ## TODO
        Set:

            thread_generation = self.video_generation
            active_url = self.video_url
            request = urllib.request.Request(active_url, headers={...})

        When the response opens, set:

            self.active_video_response = response
            content_type = response.headers.get("Content-Type", "")
            boundary = self.multipart_boundary(content_type) or b"--frame"
            buffer = b""

        In the inner loop, keep reading while both are true:

            self.video_url == active_url
            self.video_generation == thread_generation

        For each chunk, set:

            chunk = response.read(8192)
            buffer += chunk
            buffer = self.extract_multipart_frames(buffer, boundary)
        """
        thread_generation = self.video_generation
        while self.keep_running and self.video_generation == thread_generation:
            active_url = self.video_url
            request = urllib.request.Request(
                active_url,
                headers={"Accept": "multipart/x-mixed-replace,image/jpeg,image/x-portable-pixmap,image/x-portable-graymap"},
            )
            try:
                with urllib.request.urlopen(request, timeout=self.args.video_timeout) as response:
                    with self.video_response_lock:
                        self.active_video_response = response
                    content_type = response.headers.get("Content-Type", "")
                    boundary = self.multipart_boundary(content_type) or b"--frame"
                    buffer = b""
                    while self.keep_running and self.video_url == active_url and self.video_generation == thread_generation:
                        chunk = response.read(8192)
                        if not chunk:
                            break
                        buffer += chunk
                        buffer = self.extract_multipart_frames(buffer, boundary)
            except urllib.error.HTTPError as exc:
                if self.keep_running:
                    self.add_event("warn", f"video HTTP {exc.code}")
                    time.sleep(1.0)
            except Exception as exc:
                if self.keep_running:
                    self.add_event("warn", f"video reconnect: {exc}")
                    time.sleep(1.0)
            finally:
                with self.video_response_lock:
                    if self.video_generation == thread_generation:
                        self.active_video_response = None

    def extract_multipart_frames(self, buffer: bytes, boundary: bytes) -> bytes:
        """
        Extend base extraction by recording when the newest frame arrived.

        Method-call syntax:

            remaining = super().extract_multipart_frames(buffer, boundary)
        """
        before = self.video_frame_id
        remaining = super().extract_multipart_frames(buffer, boundary)
        if self.video_frame_id != before:
            self.last_video_frame_at = time.monotonic()
        return remaining

    def set_camera_topic(self, index: int) -> None:
        """
        Switch camera topic by index.

        Key mapping:

            0 -> RGB
            1 -> Depth
            2 -> IR
            3 -> YOLO

        ## TODO
        Set:

            name, topic = CAMERA_TOPICS[index]
            parsed = urllib.parse.urlsplit(self.video_url)
            query = dict(urllib.parse.parse_qsl(parsed.query, keep_blank_values=True))
            query["topic"] = topic
            path = self.video_path_for_topic(parsed.path, topic)

        Then set:

            self.video_url = urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, path, urllib.parse.urlencode(query), parsed.fragment))
            self.video_generation += 1
            self.video_stream_logged = False

        Clear old video state by setting:

            self.video_frame = None
            self.video_frame_id += 1
            self.video_surface = None
            self.video_drawn_id = self.video_frame_id
            self.last_video_frame_at = None

        Start the new stream thread with:

            self.video_thread = threading.Thread(target=self.video_loop, daemon=True)
            self.video_thread.start()
        """
        if not 0 <= index < len(CAMERA_TOPICS):
            return
        name, topic = CAMERA_TOPICS[index]
        parsed = urllib.parse.urlsplit(self.video_url)
        query = dict(urllib.parse.parse_qsl(parsed.query, keep_blank_values=True))
        query["topic"] = topic
        path = self.video_path_for_topic(parsed.path, topic)
        self.video_url = urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, path, urllib.parse.urlencode(query), parsed.fragment))
        self.video_generation += 1
        self.video_stream_logged = False
        with self.video_response_lock:
            if self.active_video_response is not None:
                self.active_video_response.close()
                self.active_video_response = None
        with self.video_lock:
            self.video_frame = None
            self.video_frame_id += 1
        self.video_surface = None
        self.video_drawn_id = self.video_frame_id
        self.last_video_frame_at = None
        self.video_thread = threading.Thread(target=self.video_loop, daemon=True)
        self.video_thread.start()
        self.add_event("info", f"camera={name}")

    def active_topic_name(self) -> str:
        return camera_name_for_topic(topic_from_url(self.video_url))
