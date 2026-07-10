#!/usr/bin/env python3

import threading
import time
import urllib.error
import urllib.parse
import urllib.request

from .cameras import CAMERA_TOPICS, camera_name_for_topic, topic_from_url


class GuiVideoMixin:
    def start_video(self) -> None:
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
                    if not self.video_stream_logged:
                        print(
                            "video stream connected: "
                            f"content_type={content_type or 'unknown'} "
                            f"boundary={boundary.decode('utf-8', errors='replace')}"
                        )
                        self.video_stream_logged = True
                    buffer = b""
                    while self.keep_running and self.video_url == active_url and self.video_generation == thread_generation:
                        chunk = response.read(8192)
                        if not chunk:
                            break
                        if self.video_generation != thread_generation:
                            break
                        buffer += chunk
                        buffer = self.extract_multipart_frames(buffer, boundary)
            except urllib.error.HTTPError as exc:
                if self.keep_running:
                    body = self._read_http_error_body(exc)
                    detail = f": {body}" if body else ""
                    self.add_event("warn", f"video HTTP {exc.code}")
                    print(f"video stream failed: HTTP {exc.code} {exc.reason}{detail}; retrying")
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
        before = self.video_frame_id
        remaining = super().extract_multipart_frames(buffer, boundary)
        if self.video_frame_id != before:
            self.last_video_frame_at = time.monotonic()
        return remaining

    def set_camera_topic(self, index: int) -> None:
        if not 0 <= index < len(CAMERA_TOPICS):
            return
        name, topic = CAMERA_TOPICS[index]
        now = time.monotonic()
        if now - self.last_camera_switch_at < 0.25:
            return
        self.last_camera_switch_at = now
        parsed = urllib.parse.urlsplit(self.video_url)
        query = dict(urllib.parse.parse_qsl(parsed.query, keep_blank_values=True))
        if query.get("topic") == topic:
            return
        query["topic"] = topic
        path = self.video_path_for_topic(parsed.path, topic)
        self.video_url = urllib.parse.urlunsplit(
            (parsed.scheme, parsed.netloc, path, urllib.parse.urlencode(query), parsed.fragment)
        )
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
