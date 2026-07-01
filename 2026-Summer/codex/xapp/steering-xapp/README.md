# Steering-Wheel Command xApp

This xApp receives normalized steering-wheel commands over REST, applies bounds,
rate checks and deadman stop behavior, then forwards the mapped
payload to the robot ROS stack through rosbridge WebSocket. The v1 command path
is REST/IP plus ROS bridge messaging, not E2 control:

```text
Logitech wheel -> wheel_client.py -> xApp REST -> gNB/CN forwarder -> rosbridge WebSocket -> ROS /cmd_vel
```

`RMRXapp` is still used for normal xApp framework startup, config loading, SDL,
registration, and RMR health handling. The descriptor does not advertise fake
E2 indication/control messages.

## Files

- `steering_xapp.py`: xApp entrypoint and REST command service.
- `steering_service.py`: pure command validation, mapping, forwarding, and deadman logic.
- `wheel_client.py`: pygame joystick client for Logitech-style wheels.
- `forwarder_helper.py`: optional gNB/core-side HTTP forwarder for older HTTP robot endpoints.
- `rosbridge_forwarder.py`: HTTP-to-rosbridge helper for the ROSOrin UE path when only the core network container can reach the UE IP.
- `config.json`: runtime controls for REST, RMR, safety limits, and robot mapping.
- `xapp-descriptor.json`: xApp descriptor shaped for the deployed `dms_cli` onboarder.
- `test_steering_xapp.py`: focused command-service unit tests.
- `Dockerfile`: container build file. It installs `ricxappframe` with pip and installs the O-RAN RMR native library; the local `../ricxappframe` folder is only reference material.

## REST API

Health/config:

- `GET /ric/v1/health/alive`
- `GET /ric/v1/health/ready`
- `GET /ric/v1/config`

Steering:

- `POST /ric/v1/steering/command`
- `GET /ric/v1/steering/state`
- `POST /ric/v1/steering/stop`

ORAN inventory:

- `GET /ric/v1/oran/gnbs`

Command body:

```json
{
  "seq": 123,
  "timestamp_ms": 1717800000000,
  "steering": -0.25,
  "throttle": 0.40,
  "brake": 0.0,
  "enable": true
}
```

`steering` is normalized to `[-1.0, 1.0]`; `throttle` and `brake` are normalized
to `[0.0, 1.0]`. Bounds are configured in `controls.bounds`. Inputs are clamped
by default; set `clampInputs` to `false` to reject out-of-range commands.

## Robot Mapping

The ROSOrin bringup launch starts `rosbridge_server` with
`rosbridge_websocket_launch.xml`. If the xApp can directly reach the robot UE IP,
configure `controls.robot.baseUrl` as the robot rosbridge WebSocket URL, usually
port `9090`:

```json
"robot": {
  "baseUrl": "ws://10.45.1.3:9090",
  "commandPath": "/cmd_vel",
  "stopPath": "/cmd_vel",
  "timeoutSeconds": 0.2,
  "payloadFormat": "rosbridge_twist",
  "maxLinearMps": 0.2,
  "maxAngularRadps": 0.5
}
```

In the current ORAN/CN deployment, the UE IP is reachable from the core network
path. For that case, run `rosbridge_forwarder.py` in the core network namespace
or pod context, expose its HTTP port with a Kubernetes Service, and configure
the xApp to send HTTP to that Service:

```json
"robot": {
  "baseUrl": "http://10.233.56.235:8090",
  "commandPath": "/cmd_vel",
  "stopPath": "/cmd_vel",
  "timeoutSeconds": 0.5,
  "payloadFormat": "ros_twist",
  "maxLinearMps": 0.2,
  "maxAngularRadps": 0.5
}
```

Supported payload formats:

- `normalized`: forwards `steering`, `throttle`, `brake`, and `enable`.
- `ros_twist`: sends `linear.x = (throttle - brake) * maxLinearMps` and flips steering into ROS angular sign.
- `rosorin_twist`: same JSON Twist mapping for an HTTP helper or custom HTTP ROS endpoint.
- `rosbridge_twist`: publishes a `geometry_msgs/Twist` over rosbridge WebSocket.

The copied ROSOrin workspace shows this active bringup path:

```text
bringup.launch.py
  -> rosbridge_server rosbridge_websocket_launch.xml
  -> controller.launch.py
  -> odom_publisher node
  -> ros_robot_controller node
```

The controller subscribes to three `geometry_msgs/Twist` topics:

- `controller/cmd_vel`: direct chassis command path.
- `app/cmd_vel`: Ackermann steering-angle helper path.
- `cmd_vel`: app-level command path with built-in clipping.

For the xApp, use `/cmd_vel` first. The controller clips `/cmd_vel` commands to:

- `linear.x`: `-0.2..0.2 m/s`
- `linear.y`: `-0.2..0.2 m/s`
- `angular.z`: `-0.5..0.5 rad/s`

This is why the default xApp mapping uses `maxLinearMps = 0.2` and
`maxAngularRadps = 0.5`. Positive wheel steering means right turn, while ROS
positive `angular.z` means left turn, so the mapping flips the sign.

The lower-level hardware path is:

```text
/cmd_vel Twist
  -> odom_publisher_node.py clips and forwards to cmd_vel_callback()
  -> Mecanum/Ackermann kinematics
  -> ros_robot_controller/set_motor and pwm_servo/set_state
  -> ros_robot_controller_node.py
  -> serial protocol on /dev/rrc at 1000000 baud
  -> controller board
```

If `baseUrl` is blank, commands are accepted and state is updated, but robot
forwarding is skipped. This is useful for Week 1/2 bench testing.

## Local Run

For local development without DBaaS and without waiting for an RMR routing table,
set these in `config.json`:

```json
"waitForRmrReady": false,
"useFakeSdl": true
```

Install the normal package/runtime dependencies, then run from inside `basic-xapp`:

```sh
python3 -m pip install ricxappframe
export CONFIG_FILE=./config.json
python3 steering_xapp.py
```

`steering_xapp.py` imports the native RMR wrapper. Outside the deployment image,
you also need the RMR shared library available on the host. The Dockerfile shows
the package used in the image: `rmr_4.9.4_amd64.deb` from O-RAN packagecloud.

Example commands:

```sh
curl -s http://127.0.0.1:8080/ric/v1/health/alive
curl -s http://127.0.0.1:8080/ric/v1/steering/state
curl -s http://127.0.0.1:8080/ric/v1/oran/gnbs
curl -s -X POST http://127.0.0.1:8080/ric/v1/steering/command \
  -H 'Content-Type: application/json' \
  -d '{"seq":1,"timestamp_ms":1717800000000,"steering":0.1,"throttle":0.2,"brake":0.0,"enable":true}'
curl -s -X POST http://127.0.0.1:8080/ric/v1/steering/stop
```

The xApp records the received `timestamp_ms` and includes `timestamp_date` in
responses using `m/dd/YYYY` format. Timestamp values are informational only;
wall-clock skew is not used to reject commands.

`/ric/v1/oran/gnbs` uses `RMRXapp.get_list_gnb_ids()` and returns a count plus
the RNIB gNB identity records. UE inventory is future work because this
`ricxappframe` reference exposes gNB/node RNIB helpers but no direct connected-UE
lookup helper.

Sample outputs from an ORAN host:

`GET /ric/v1/health/alive`

```json
{
  "alive": true,
  "name": "steering-xapp"
}
```

This means the HTTP server on port `8080` is up and the xApp process is alive.
It does not prove RMR/SDL readiness; use `/ric/v1/health/ready` for that.

`GET /ric/v1/steering/state` before any wheel command:

```json
{
  "limits": {
    "steering_min": -1.0,
    "steering_max": 1.0,
    "throttle_min": 0.0,
    "throttle_max": 1.0,
    "brake_min": 0.0,
    "brake_max": 1.0,
    "clamp_inputs": true,
    "command_rate_hz": 20.0,
    "deadman_timeout_ms": 500
  },
  "robot": {
    "base_url": "",
    "command_path": "/cmd_vel",
    "payload_format": "rosbridge_twist",
    "max_linear_mps": 0.2,
    "max_angular_radps": 0.5
  },
  "state": {
    "command_count": 0,
    "last_command": null,
    "last_seq": null,
    "rejected_count": 0,
    "stop_count": 0,
    "stopped": true
  }
}
```

This is the idle state. `command_count: 0` means no accepted wheel command has
arrived yet. `stopped: true` is expected at startup. If the `robot` block shows
`/api/steering`, `normalized`, and `max_linear_mps: 1.0`, the pod is running an
older config/image or an old ConfigMap; the current ROSOrin defaults are
`/cmd_vel`, `rosbridge_twist`, `maxLinearMps: 0.2`, and
`maxAngularRadps: 0.5`.

`GET /ric/v1/oran/gnbs`

```json
{
  "count": 3,
  "gnbs": [
    {
      "connection_status": "CONNECTED",
      "global_nb_id": {
        "nb_id": "0000000000000110011011",
        "plmn_id": "00F110"
      },
      "inventory_name": "gnbc_001_001_00019b_0"
    },
    {
      "connection_status": "CONNECTED",
      "global_nb_id": {
        "nb_id": "0000000000000110011011",
        "plmn_id": "00F110"
      },
      "inventory_name": "gnbd_001_001_00019b_0"
    },
    {
      "connection_status": "CONNECTED",
      "global_nb_id": {
        "nb_id": "0000000000000110011011",
        "plmn_id": "00F110"
      },
      "inventory_name": "gnb_001_001_00019b"
    }
  ],
  "source": "RMRXapp.get_list_gnb_ids"
}
```

This means SDL/RNIB is reachable and currently contains three connected gNB
identity records. `source` confirms the endpoint is using the framework helper,
not a hardcoded list.

## Wheel Client

Run on the host with the wheel device:

```sh
python3 -m pip install pygame
python3 wheel_client.py --joystick-index 0 --xapp-url http://127.0.0.1:8080 --rate-hz 20
```

The wheel client opens the robot camera window by default. Disable it for
command-only testing:

```sh
python3 wheel_client.py --joystick-index 0 --xapp-url http://127.0.0.1:8080 --rate-hz 10 --no-video
```

The video window connects to `GET /ric/v1/video/stream` in a background thread,
so wheel command POSTs continue while frames are being received.
By default, the video window uses the long-lived xApp stream endpoint:

```sh
python3 wheel_client.py \
  --xapp-url http://127.0.0.1:8080 \
  --video-url http://127.0.0.1:8080/ric/v1/video/stream
```

Axis defaults come from `logiwheel.py`: steering `0`, accelerator/throttle `1`,
brake `2`, clutch `3`. The xApp command uses steering, throttle, and brake;
clutch is logged by `logiwheel.py` but not sent to the robot command path.
These defaults are hardcoded in `DEFAULT_WHEEL_CONFIG` inside `wheel_client.py`;
command-line args override them when present.

Wheel axis assumptions:

- Steering is centered at raw `0`; negative raw values are left, positive raw values are right.
- Pedals idle at raw `+1.0` and move toward raw `-1.0` when pressed.
- Pedals are normalized so idle becomes `0.0` and fully pressed becomes `1.0`.
- Steering values inside the default `0.03` deadzone are sent as `0.0`.

Tune axes and inversion flags with:

```sh
python3 wheel_client.py --steering-axis 0 --throttle-axis 1 --brake-axis 2 --print-commands
```

The wheel client prints xApp responses in an indented JSON format, similar to
`curl ... | jq`.

Use `--invert-throttle` or `--invert-brake` only if a pedal reports idle `-1.0`
and pressed `+1.0`.

Use `logiwheel.py` when you only want to inspect raw axes/buttons:

```sh
python3 logiwheel.py
```

The client sends `POST /ric/v1/steering/stop` on shutdown.

## Arm Buttons

Arm control is enabled by default in the wheel client. Buttons map to servo
IDs in this order:

```text
button 5  -> servo id 1
button 4  -> servo id 2
button 7  -> servo id 3
button 11 -> servo id 4
button 6  -> servo id 5
button 10 -> servo id 10
```

Holding a button increases that servo position. Holding the clutch pedal while
holding a button decreases it. The client repeats held-button updates at 5 Hz
with a default step of 10 pulse units.

Disable arm controls:

```sh
python3 wheel_client.py --no-arm
```

Direct xApp arm command:

```sh
curl -s -X POST http://$APP_IP:8080/ric/v1/arm/pose \
  -H 'Content-Type: application/json' \
  -d '{"duration":0.3,"positions":[{"id":1,"position":510}]}' | jq
```

Current arm state:

```sh
curl -s http://$APP_IP:8080/ric/v1/arm/state | jq
```

The xApp clamps arm commands to observed action-group ranges:

```text
id1:  100..1000
id2:  100..765
id3:  0..468
id4:  88..654
id5:  125..700
id10: 200..700
```

## Optional Forwarder

Use `rosbridge_forwarder.py` when the xApp cannot directly reach the robot UE
IP, but the core network namespace can. The xApp sends HTTP to the core
network Service; the helper publishes the Twist to rosbridge from inside the
reachable network path.

Run the helper where `ws://10.45.1.3:9090` is reachable:

```sh
python3 -m pip install websocket-client
python3 rosbridge_forwarder.py \
  --listen-host 0.0.0.0 \
  --listen-port 8090 \
  --rosbridge-url ws://10.45.1.3:9090 \
  --default-topic /cmd_vel \
  --default-video-topic /depth_cam/rgb0/image_raw \
  --default-arm-topic /servo_controller
```

Expose `8090` from the core network deployment with the LoadBalancer Service
IP `10.233.56.235`. Then set the xApp robot base URL to that Service address:

```json
"baseUrl": "http://10.233.56.235:8090",
"payloadFormat": "ros_twist",
"commandPath": "/cmd_vel",
"stopPath": "/cmd_vel",
"videoSnapshotPath": "/video/snapshot",
"videoStreamPath": "/video/stream",
"armPosePath": "/arm/pose"
```

The helper accepts the xApp's Twist JSON over HTTP and sends this rosbridge
message to the robot:

```json
{
  "op": "publish",
  "topic": "/cmd_vel",
  "msg": {
    "linear": {"x": 0.1, "y": 0.0, "z": 0.0},
    "angular": {"x": 0.0, "y": 0.0, "z": -0.2}
  }
}
```

The older `forwarder_helper.py` is only for older/custom robot HTTP endpoints.
The ROSOrin path should use `rosbridge_forwarder.py`.

Video snapshot checks:

```sh
curl -s http://10.233.56.235:8090/video/snapshot --output frame.ppm
curl -s http://$APP_IP:8080/ric/v1/video/snapshot --output frame.ppm
```

The xApp proxies the forwarder's long-lived multipart frame stream:

```sh
curl http://$APP_IP:8080/ric/v1/video/stream --output video.multipart
```

For raw ROS camera images, the helper returns PPM/PGM bytes. If a compressed
ROS image topic is used, it returns the compressed bytes directly.

If the xApp cannot reach an older HTTP endpoint directly, run this on a host
that can:

```sh
python3 forwarder_helper.py --listen-port 8090 --target-base-url http://10.45.1.3:8000
```

Then set the xApp robot base URL to the helper:

```json
"baseUrl": "http://10.233.56.235:8090"
```

The helper forwards HTTP JSON bodies only. It does not speak rosbridge, does not
parse E2 messages, and does not require Ocudu gNB changes.

## Validation

From inside `basic-xapp`:

```sh
python3 -m json.tool config.json
python3 -m json.tool xapp-descriptor.json
python3 -m py_compile steering_xapp.py steering_service.py wheel_client.py forwarder_helper.py rosbridge_forwarder.py
python3 -m unittest test_steering_xapp.py test_wheel_client.py
```

The unit tests import `steering_service.py` directly, so they do not require
RMR or `ricxappframe`.

The bundled `xapp-embedded-schema.json` is older than the `dms_cli` validator on
your ORAN host. In particular, your onboarder expects `containers[].command` as
an array. Use the deployed onboarder as the descriptor validation authority:

```sh
dms_cli onboard xapp-descriptor.json config.json
```

## Five-Week Delivery Checklist

Week 1, Jun 7-Jun 13:

- REST/IP command path selected for v1; no E2 control or subscription dependency.
- xApp renamed and config/descriptor updated.
- Command, state, stop, config, and health endpoints implemented.
- Descriptor JSON is valid and is shaped for the deployed `dms_cli` onboarder.

Week 2, Jun 14-Jun 20:

- `wheel_client.py` maps wheel axes/buttons to normalized command JSON.
- Local curl and unit-test fixtures validate command ingestion without robot attached.

Week 3, Jun 21-Jun 27:

- Configure `controls.robot.baseUrl` as the core forwarder Service URL.
- Confirm `/cmd_vel` reaches the ROSOrin controller and triggers the built-in clips.

Week 4, Jun 28-Jul 4:

- Deadman stop and rate limiting are active.
- Bench test wheel, xApp, and robot endpoint together.

Week 5, Jul 5-Jul 11:

- Build and deploy container.
- Run end-to-end private ORAN network test.
- Demo health checks, command flow, stop behavior, failure recovery, and logs.

Build the container from inside `basic-xapp`:

```sh
docker build --network=host -t registry.local:5000/steering-xapp:1.0.0 .
docker push registry.local:5000/steering-xapp:1.0.0
```

The image build installs:

- `rmr_4.9.4_amd64.deb` from O-RAN packagecloud.
- `ricxappframe` and `pygame` from pip.
- a conditional musl compatibility symlink from `/usr/lib/x86_64-linux-musl/libc.so` to `/lib/libc.musl-x86_64.so.1` when that source file exists.
