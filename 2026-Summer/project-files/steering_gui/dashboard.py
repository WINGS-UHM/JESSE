#!/usr/bin/env python3

import io
import time
from typing import Any, Optional, Tuple

from .constants import ARM_LIMITS, ARM_SERVO_IDS


class DashboardRenderer:
    def draw_video_frame(self) -> None:
        if not self.args.video or not self.video_window_started:
            return
        with self.video_lock:
            frame = self.video_frame
            frame_id = self.video_frame_id
        if frame is not None and frame_id != self.video_drawn_id:
            try:
                self.video_surface = self.pygame.image.load(io.BytesIO(frame)).convert()
                self.video_drawn_id = frame_id
            except self.pygame.error as exc:
                self.add_event("warn", f"video decode: {exc}")
                self.video_drawn_id = frame_id
        self.draw_dashboard()

    def draw_dashboard(self) -> None:
        window = self.pygame.display.get_surface()
        if window is None:
            return
        width, height = window.get_size()
        window.fill((18, 20, 24))

        margin = 14
        status_w = max(280, min(340, width // 3))
        bottom_h = 170
        video_rect = self.pygame.Rect(margin, margin, width - status_w - 3 * margin, height - bottom_h - 2 * margin)
        status_rect = self.pygame.Rect(video_rect.right + margin, margin, status_w, video_rect.height)
        bottom_rect = self.pygame.Rect(margin, video_rect.bottom + margin, width - 2 * margin, bottom_h - margin)

        self.draw_panel(window, video_rect, "Video")
        video_content_rect = self.pygame.Rect(video_rect.x + 8, video_rect.y + 44, video_rect.width - 16, video_rect.height - 52)
        self.draw_video_panel(window, video_content_rect)
        self.draw_status_panel(window, status_rect)
        self.draw_bottom_panel(window, bottom_rect)
        self.pygame.display.flip()

    def draw_video_panel(self, window: Any, rect: Any) -> None:
        self.pygame.draw.rect(window, (8, 10, 12), rect, border_radius=4)
        if self.video_surface is None:
            self.draw_text(window, "waiting for video...", (rect.x + 18, rect.y + 18), (220, 220, 220))
            return
        source = self.video_surface
        sw, sh = source.get_size()
        scale = min(rect.width / sw, rect.height / sh)
        target = (max(1, int(sw * scale)), max(1, int(sh * scale)))
        image = self.pygame.transform.smoothscale(source, target)
        window.blit(image, (rect.centerx - target[0] // 2, rect.centery - target[1] // 2))
        self.draw_text(window, self.active_topic_name(), (rect.x + 10, rect.y + 8), (255, 255, 255))

    def draw_status_panel(self, window: Any, rect: Any) -> None:
        self.draw_panel(window, rect, "Status")
        x, y = rect.x + 16, rect.y + 44
        video_age = None if self.last_video_frame_at is None else max(0.0, time.monotonic() - self.last_video_frame_at)
        video_status = "waiting" if video_age is None else ("fresh" if video_age < 1.5 else "stale")
        rows = [
            ("xApp", self.last_command_status),
            ("Robot", self.last_robot_status),
            ("Video", video_status),
            ("Camera", self.active_topic_name()),
            ("Arm", self.last_arm_status),
        ]
        for label, value in rows:
            color = (110, 220, 145) if value in ("ok", "fresh", "accepted") else (235, 190, 90)
            if value in ("error", "stale"):
                color = (235, 95, 95)
            self.draw_text(window, f"{label:8s}", (x, y), (170, 180, 190))
            self.draw_text(window, str(value), (x + 95, y), color)
            y += 30
        y += 10
        self.draw_text(window, "Keys", (x, y), (230, 230, 230), self.title_font)
        y += 32
        for text in ("^ RGB  < Depth", "v IR   > YOLO", "B0/R default arm", "Esc/Q quit"):
            self.draw_text(window, text, (x, y), (185, 195, 205), self.small_font)
            y += 24
        y += 8
        self.draw_text(window, "Log", (x, y), (230, 230, 230), self.title_font)
        y += 30
        for message_time, _kind, text in self.event_log:
            age = max(0, int(time.monotonic() - message_time))
            self.draw_text(window, f"{age:2d}s {text}"[:32], (x, y), (190, 200, 210), self.small_font)
            y += 22

    def draw_bottom_panel(self, window: Any, rect: Any) -> None:
        self.draw_panel(window, rect, "Controls")
        command = self.current_command or self.last_sent_command or {}
        x, y = rect.x + 16, rect.y + 42
        self.draw_bar(window, self.pygame.Rect(x, y, 300, 22), float(command.get("steering", 0.0)), -1.0, 1.0, "Steering")
        self.draw_bar(window, self.pygame.Rect(x, y + 38, 300, 22), float(command.get("throttle", 0.0)), 0.0, 1.0, "Throttle")
        self.draw_bar(window, self.pygame.Rect(x, y + 76, 300, 22), float(command.get("brake", 0.0)), 0.0, 1.0, "Brake")
        arm_x = x + 340
        self.draw_text(window, "Arm servos", (arm_x, y), (230, 230, 230), self.title_font)
        for offset, servo_id in enumerate(ARM_SERVO_IDS):
            lower, upper = ARM_LIMITS[servo_id]
            curr = self.arm_positions.get(servo_id, 0)
            row = offset // 2
            col = offset % 2
            self.draw_text(
                window,
                f"id{servo_id:<2} {curr:>4}  {lower}-{upper}",
                (arm_x + col * 210, y + 34 + row * 30),
                (190, 205, 215),
                self.small_font,
            )

    def draw_panel(self, window: Any, rect: Any, title: str) -> None:
        self.pygame.draw.rect(window, (28, 32, 38), rect, border_radius=6)
        self.pygame.draw.rect(window, (64, 72, 84), rect, width=1, border_radius=6)
        self.draw_text(window, title, (rect.x + 14, rect.y + 12), (235, 238, 240), self.title_font)

    def draw_bar(self, window: Any, rect: Any, value: float, lower: float, upper: float, label: str) -> None:
        self.pygame.draw.rect(window, (45, 50, 58), rect, border_radius=4)
        normalized = max(0.0, min(1.0, (value - lower) / (upper - lower)))
        fill = self.pygame.Rect(rect.x, rect.y, int(rect.width * normalized), rect.height)
        self.pygame.draw.rect(window, (75, 160, 220), fill, border_radius=4)
        self.pygame.draw.rect(window, (78, 88, 100), rect, width=1, border_radius=4)
        self.draw_text(window, f"{label}: {value:+.2f}", (rect.x + 8, rect.y + 2), (245, 245, 245), self.small_font)

    def draw_text(self, window: Any, text: str, pos: Tuple[int, int], color: Tuple[int, int, int], font: Optional[Any] = None) -> None:
        selected_font = font or self.font
        if selected_font is None:
            return
        window.blit(selected_font.render(text, True, color), pos)
