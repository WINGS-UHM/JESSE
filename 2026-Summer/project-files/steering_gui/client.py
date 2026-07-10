#!/usr/bin/env python3

import signal
import threading
import time
from typing import Any, Dict, Optional, Sequence

from .arguments import parse_args
from .cameras import HAT_CAMERA_BINDINGS
from .control import WheelControlClient, pygame
from .helpers import button_value, read_state

from .dashboard import DashboardRenderer
from .events import EventLog
from .video import GuiVideoMixin


class GuiWheelClient(GuiVideoMixin, DashboardRenderer, WheelControlClient):
    def __init__(self, args: Any) -> None:
        super().__init__(args)
        self.pygame = pygame
        self.event_log = EventLog(max_entries=7)
        self.current_axes = []
        self.current_command: Optional[Dict[str, Any]] = None
        self.video_surface: Optional[Any] = None
        self.last_video_frame_at: Optional[float] = None
        self.last_command_status = "idle"
        self.last_robot_status = "unknown"
        self.last_arm_status = "idle"
        self.video_generation = 0
        self.video_response_lock = threading.Lock()
        self.active_video_response: Optional[Any] = None
        self.last_camera_switch_at = 0.0
        self.last_hat_direction = (0, 0)
        self.font = None
        self.small_font = None
        self.title_font = None
        self.add_event("info", "GUI client started")

    def run(self) -> None:
        if pygame is None:
            raise SystemExit("pygame is required to run the GUI client. Install it with: python3 -m pip install pygame")
        pygame.init()
        pygame.joystick.init()
        if pygame.joystick.get_count() == 0:
            raise SystemExit("No joystick or wheel detected by pygame.")

        joystick = pygame.joystick.Joystick(self.args.joystick_index)
        joystick.init()
        self.add_event("info", f"wheel={joystick.get_name()}")
        print(
            f"Using {joystick.get_name()} "
            f"axes={joystick.get_numaxes()} buttons={joystick.get_numbuttons()} hats={joystick.get_numhats()}"
        )
        if self.args.video:
            self.start_video()
        self.send_launch_arm_pose()

        next_send = 0.0
        try:
            while self.keep_running:
                self.handle_pygame_events()
                axes, buttons, hats = read_state(joystick)
                self.current_axes = axes
                now = time.monotonic()
                self.process_arm_default_button(buttons)
                self.process_camera_hat(hats)
                self.process_arm_buttons(axes, buttons, now)
                if now >= next_send:
                    command = self.build_command(axes, buttons)
                    self.current_command = command
                    if self.should_send_command(command, now):
                        response = self._post_json(self.command_url, command)
                        self.last_sent_command = command
                        self.last_sent_time = now
                        if self.args.print_commands:
                            print(f"seq={command['seq']} cmd={command}")
                        if response is not None:
                            self.last_command_status = "accepted"
                    next_send = time.monotonic() + (1.0 / self.args.rate_hz)
                if self.stop_requested(buttons, hats):
                    self.keep_running = False
                self.draw_video_frame()
                time.sleep(self.args.poll_seconds)
        finally:
            self.send_stop()
            self.reset_arm_on_exit()
            pygame.quit()

    def handle_pygame_events(self) -> None:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.keep_running = False
            elif event.type == pygame.KEYDOWN:
                if event.key in (pygame.K_ESCAPE, pygame.K_q):
                    self.keep_running = False
                elif event.key == pygame.K_r:
                    self.send_default_arm_pose()
                elif pygame.K_1 <= event.key <= pygame.K_4:
                    self.set_camera_topic(event.key - pygame.K_1)

    def build_command(self, axes: Sequence[float], buttons: Sequence[int]) -> Dict[str, Any]:
        command = super().build_command(axes, buttons)
        self.current_command = command
        return command

    def process_arm_default_button(self, buttons: Sequence[int]) -> None:
        if self.args.arm_default_button < 0:
            return
        pressed = bool(button_value(buttons, self.args.arm_default_button))
        if pressed and not self.arm_default_button_was_pressed:
            self.send_default_arm_pose()
            self.add_event("info", "default arm button")
        self.arm_default_button_was_pressed = pressed

    def process_camera_hat(self, hats: Sequence[Any]) -> None:
        direction = tuple(hats[0]) if hats else (0, 0)
        if direction == self.last_hat_direction:
            return
        self.last_hat_direction = direction
        if direction == (0, 0):
            return
        camera_index = HAT_CAMERA_BINDINGS.get(direction)
        if camera_index is not None:
            self.set_camera_topic(camera_index)

    def _post_json(self, url: str, payload: Dict[str, Any]) -> Any:
        response = super()._post_json(url, payload)
        if "/steering/command" in url:
            if response is None:
                self.last_command_status = "error"
                self.last_robot_status = "unknown"
            else:
                robot = response.get("robot", {}) if isinstance(response, dict) else {}
                self.last_robot_status = "ok" if robot.get("ok") else "error"
                if robot and not robot.get("ok"):
                    self.add_event("warn", f"robot {robot.get('status_code', 'error')}")
        elif "/arm/pose" in url:
            self.last_arm_status = "ok" if response is not None else "error"
            self.add_event("info" if response is not None else "warn", f"arm {self.last_arm_status}")
        elif "/steering/stop" in url:
            self.add_event("info", "stop sent")
        return response

    def add_event(self, kind: str, message: str) -> None:
        self.event_log.add(kind, message)


def main() -> None:
    args = parse_args()
    client = GuiWheelClient(args)

    def stop(_signum: int, _frame: Any) -> None:
        client.keep_running = False

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    client.run()


if __name__ == "__main__":
    main()
