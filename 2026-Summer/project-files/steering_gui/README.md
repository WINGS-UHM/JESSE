# Steering GUI

The GUI client is the operator program. It reads the Logitech steering wheel, sends movement and arm commands to the xApp, and displays robot video/status in a pygame window.

This guide assumes the GUI package is in:

```text
steering_gui/
```

Run from the repository root:

```bash
python3 -m steering_gui
```

## Module Layout

```text
steering_gui/
├── __init__.py
├── __main__.py
├── arguments.py
├── cameras.py
├── client.py
├── constants.py
├── control.py
├── dashboard.py
├── events.py
├── helpers.py
└── video.py
```

## What Each Module Does

- `__init__.py`: marks the folder as a Python package.
- `__main__.py`: lets the package run with `python3 -m steering_gui`.
- `arguments.py`: command-line arguments and validation.
- `constants.py`: default xApp URL, wheel axes, arm buttons, camera defaults, servo IDs, servo limits, and robot default arm pose.
- `helpers.py`: small utility functions for clamping, reading pygame joystick state, normalizing pedals, and parsing integer lists.
- `cameras.py`: camera topic names and hat-switch mappings.
- `events.py`: short rolling event log for the dashboard.
- `control.py`: base wheel client logic. Builds steering commands, sends REST requests, handles arm buttons, parses MJPEG frames, and handles HTTP errors.
- `video.py`: GUI video behavior. Starts the video thread, switches camera topics, reconnects streams, and updates latest frame time.
- `dashboard.py`: pygame drawing code for the video panel, status panel, control bars, arm values, and event log.
- `client.py`: top-level GUI class that combines `control.py`, `video.py`, and `dashboard.py`.

## Default Run

```bash
python3 -m steering_gui
```

Default behavior:

- Opens a pygame dashboard.
- Connects to the xApp at the default URL in `constants.py`.
- Starts RGB video by default.
- Reads steering, throttle, brake, clutch, buttons, and hat switch.
- Sends movement commands to the xApp.
- Sends arm reset on exit when enabled.

## Common Arguments

Set xApp URL:

```bash
python3 -m steering_gui --xapp-url http://192.168.50.247:8080
```

Print command payloads while testing:

```bash
python3 -m steering_gui --print-commands
```

Disable video:

```bash
python3 -m steering_gui --no-video
```

Disable arm commands:

```bash
python3 -m steering_gui --no-arm
```

Use a specific camera topic:

```bash
python3 -m steering_gui --video-topic /depth_cam/rgb0/image_raw
```

Use IR:

```bash
python3 -m steering_gui --video-topic /depth_cam/ir0/image_raw
```

Use YOLO processed image:

```bash
python3 -m steering_gui --video-topic /yolo/object_image
```

Use depth:

```bash
python3 -m steering_gui --video-topic /depth_cam/depth0/image_raw
```

## Wheel Mapping

Default axes:

- axis `0`: steering
- axis `1`: throttle pedal
- axis `2`: brake pedal
- axis `3`: clutch pedal

Default pedal convention:

- idle: `+1`
- pressed: toward `-1`

The GUI calibrates pedal idle values at startup by default.

Steering convention:

- `0.0`: centered
- negative: left
- positive: right

## Arm Mapping

Default arm buttons:

```text
buttons:   5, 4, 7, 11, 6, 10
servos:    1, 2, 3,  4, 5, 10
```

Normal button hold increases the servo value until its upper limit.

Holding the clutch pedal while pressing an arm button decreases the servo value until its lower limit.

Button `0` sends the user default arm pose if it is fully configured. If the user default pose is not configured, it sends the ROS workspace default pose.

On program exit, the client sends the ROS workspace default pose when `--arm-reset-on-exit` is enabled.

## Camera Mapping

Keyboard camera shortcuts:

- `1`: RGB
- `2`: Depth
- `3`: IR
- `4`: YOLO

Hat switch camera shortcuts:

- up: RGB
- left: Depth
- down: IR
- right: YOLO

## Dashboard

The dashboard shows:

- current camera/video
- xApp command status
- robot forwarding status
- video freshness
- arm status
- latest event log entries
- steering/throttle/brake bars
- current arm servo values

## Recommended Test Sequence

1. Verify the xApp is reachable:

```bash
curl -s http://192.168.50.247:8080/ric/v1/health/alive | jq
```

2. Start GUI without arm and with printed commands:

```bash
python3 -m steering_gui --no-arm --print-commands
```

3. Move wheel/pedals and confirm printed command values change.

4. Check xApp state:

```bash
curl -s http://192.168.50.247:8080/ric/v1/steering/state | jq '.state.last_command, .state.last_robot_status'
```

5. Enable arm after movement is confirmed:

```bash
python3 -m steering_gui --print-commands
```

## Notes

Video and movement use different robot-side paths:

```text
RGB/IR/YOLO video -> robot web_video_server :8080
movement/arm/depth raw -> robot rosbridge :9090
```

If RGB video works but movement/arm/depth fails, check the ROS bridge path first.
