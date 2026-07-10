# Steering xApp Project

This repository is organized around two runtime pieces:

- `steering_xapp/`: the ORAN xApp, robot command service, Docker/deployment files, and CN-side ROS bridge forwarder.
- `steering_gui/`: the pygame wheel/dashboard client used by the operator.

## Repository Tree

```text
.
├── steering_xapp/
│   ├── Dockerfile
│   ├── config.json
│   ├── xapp-descriptor.json
│   ├── routes.txt
│   ├── steering_xapp.py
│   ├── steering_service.py
│   ├── rosbridge_forwarder.py
│   ├── forwarder_helper.py
│   └── wheel_client.py
├── steering_gui/
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

## Description

- `steering_xapp/steering_xapp.py`: xApp entrypoint. Starts the xApp framework and exposes REST endpoints for health, steering, arm control, video proxying, and state.
- `steering_xapp/steering_service.py`: command validation and mapping logic. Converts normalized wheel input into robot-safe movement commands.
- `steering_xapp/rosbridge_forwarder.py`: CN-side HTTP forwarder. Receives HTTP from the xApp and publishes to the robot through ROS bridge/web video server.
- `steering_xapp/config.json`: runtime xApp config, including robot/CN forwarder URL, movement limits, deadman timeout, REST port, and RMR settings.
- `steering_xapp/xapp-descriptor.json`: ORAN-SC xApp onboarding descriptor.
- `steering_xapp/Dockerfile`: builds the xApp image with `ricxappframe`, RMR library, and required Python dependencies.
- `steering_xapp/routes.txt`: seed route file for RMR startup.
- `steering_xapp/wheel_client.py`: earlier single-file wheel client kept for reference/prototype use.
- `steering_gui/`: modular GUI client. Reads the steering wheel, sends commands to the xApp, shows video, displays status, and handles arm/camera controls.

## Runtime Flow

```text
Logitech wheel
  -> steering_gui
  -> steering_xapp REST API
  -> CN rosbridge_forwarder.py
  -> robot ROS bridge / web video server
  -> ROS topics such as /cmd_vel, /servo_controller, camera topics
```

The command path is REST/IP plus ROS bridge. It is not using E2 control for movement in this version.
