# Week 2 Final Lab: Prove The Wheel-To-xApp Command Path

## Goal

Trace and test this path:

```text
wheel_client.py -> xApp REST API -> steering_service.py -> robot payload
```

Focus areas:

- wheel input becomes command JSON
- the xApp accepts valid commands
- the xApp rejects invalid commands
- the stop endpoint works
- the state endpoint reports useful status

---

## Lab Task List

| Task | Activity | Output |
|---|---|---|
| Task 1 | Trace the code path and choose xApp name | Small diagram and unique app name |
| Task 2 | Convert raw wheel values into command JSON without the controller | Completed input/output table |
| Task 3 | Copy, build, push, onboard, and install | Running xApp with unique name |
| Task 4 | Test REST endpoints with curl | Curl commands and response examples |
| Task 5 | Practice robot payload mapping | 3 to 5 mapped payload examples |
| Task 6 | Timed physical wheel checkout | Wheel command examples |
| Task 7 | Complete final review | Final checklist |

Physical wheel testing happens last. The controller is shared, so REST, curl,
deployment, and paper command-mapping work are completed before using the
physical wheel.

---

# Task 1: Trace The Code Path

## Task

Trace what happens when the wheel client sends one command.

Use this path:

```text
wheel_client.py
    |
    | POST /ric/v1/steering/command
    v
steering_xapp.py
    |
    | app.command_service.submit(body)
    v
steering_service.py
```

## Questions

Expected answers:

1. Which file reads the steering wheel?
2. Which file creates the JSON command?
3. Which file receives the REST request?
4. Which function handles `POST /ric/v1/steering/command`?
5. Which file validates the command?
6. Which file remembers the latest command state?
7. Which endpoint sends a stop command?

## Expected Output

Path from wheel input to xApp command handling:

Example:

```text
wheel axis values
    -> normalize_steering / normalize_pedal
    -> command dictionary
    -> HTTP POST
    -> REST handler
    -> command service
```

---

# Task 2: Command Payload Practice Without The Physical Wheel

## Raw Input Rules

For the wheel:

| Input | Raw Idle | Raw Pressed | Normalized Meaning |
|---|---:|---:|---|
| steering | `0.0` | left/right movement | `-1.0` left, `+1.0` right |
| throttle pedal | `+1.0` | `-1.0` | `0.0` idle, `1.0` fully pressed |
| brake pedal | `+1.0` | `-1.0` | `0.0` idle, `1.0` fully pressed |

Pedal formula:

```python
pressed = (1.0 - raw_value) / 2.0
```

## Example

Raw values:

```text
steering = 0.5
throttle_raw = 0.0
brake_raw = 1.0
```

Normalized:

```text
steering = 0.5
throttle = 0.5
brake = 0.0
```

Command JSON:

```json
{
  "seq": 1,
  "timestamp_ms": 123456789,
  "steering": 0.5,
  "throttle": 0.5,
  "brake": 0.0,
  "enable": true
}
```

## Practice Table

Complete this table.

| Case | Raw Steering | Raw Throttle | Raw Brake | Normalized Steering | Normalized Throttle | Normalized Brake |
|---|---:|---:|---:|---:|---:|---:|
| 1 | `0.0` | `1.0` | `1.0` |  |  |  |
| 2 | `0.5` | `0.0` | `1.0` |  |  |  |
| 3 | `-0.5` | `-1.0` | `1.0` |  |  |  |
| 4 | `0.0` | `1.0` | `-1.0` |  |  |  |
| 5 | `0.02` | `0.9` | `1.0` |  |  |  |

## Expected Output

Each row has a command JSON payload that would be sent to the xApp.

Use this shape:

```json
{
  "seq": 1,
  "timestamp_ms": 123456789,
  "steering": 0.0,
  "throttle": 0.0,
  "brake": 0.0,
  "enable": true
}
```

---

# Task 3: Build, Push, Onboard, Install

Use a unique xApp name before building and onboarding.

Name format:

```text
steering-wheel-command-xapp-<name_or_identifier>
```

Examples:

```text
steering-wheel-command-xapp-alex
steering-wheel-command-xapp-team1
steering-wheel-command-xapp-jlee
```

In the commands below, replace:

```text
<APP_NAME>
```

with the chosen unique name.

Example:

```sh
APP_NAME=steering-wheel-command-xapp-team1
```

## JSON Name Changes

Update `config.json`.

Change these fields:

```json
{
  "name": "<APP_NAME>",
  "xapp_name": "<APP_NAME>",
  "json_url": "<APP_NAME>"
}
```

Also update each `container` value in `config.json`:

```json
"messaging": {
  "ports": [
    {
      "name": "http",
      "container": "<APP_NAME>",
      "port": 8080
    },
    {
      "name": "rmr-data",
      "container": "<APP_NAME>",
      "port": 4562
    }
  ]
}
```

Update `xapp-descriptor.json`.

Change these fields:

```json
{
  "xapp_name": "<APP_NAME>",
  "json_url": "<APP_NAME>"
}
```

Change the container name:

```json
"containers": [
  {
    "name": "<APP_NAME>"
  }
]
```

Change the image name:

```json
"image": {
  "registry": "registry.local:5000",
  "name": "<APP_NAME>",
  "tag": "1.0.0"
}
```

Also update each `container` value in `xapp-descriptor.json`:

```json
"messaging": {
  "ports": [
    {
      "name": "http",
      "container": "<APP_NAME>",
      "port": 8080
    },
    {
      "name": "rmr-data",
      "container": "<APP_NAME>",
      "port": 4562
    }
  ]
}
```

Do not change these unless instructed:

- `version`
- `APP_NAMESPACE`
- `CONFIG_PATH`
- REST paths such as `/ric/v1/health/alive`
- port `8080`
- port `4562`
- command `["python3", "/opt/xapp/steering_xapp.py"]`

## Build And Push

Run the copy commands from the local computer. Run the build, push, onboard,
install, logs, and service commands on the ORAN host.

Use one terminal for local commands first. After the files are copied, use SSH
to enter the ORAN host and continue there.

## Terminal Variables

Commands in this section use terminal variables such as:

```sh
APP_NAME=steering-wheel-command-xapp-team1
```

After that line is entered, `${APP_NAME}` means:

```text
use the value stored in APP_NAME
```

Example:

```sh
echo ${APP_NAME}
```

prints:

```text
steering-wheel-command-xapp-team1
```

Another variable used later is:

```sh
APP_IP=10.233.48.169
```

Then:

```sh
curl "http://${APP_IP}:8080/ric/v1/health/alive"
```

means:

```sh
curl "http://10.233.48.169:8080/ric/v1/health/alive"
```

Terminal variables are temporary. If the terminal window closes, the variables
are gone. If a new terminal or a new SSH session is opened, set the variables
again.

Check a variable:

```sh
echo ${APP_NAME}
```

If the output is blank, set it again:

```sh
APP_NAME=steering-wheel-command-xapp-<name_or_identifier>
```

## Python Virtual Environment For `dms_cli`

`dms_cli` is available after activating the onboarder Python virtual
environment on the ORAN host.

A virtual environment, or venv, is a folder that contains a separate Python
setup for one project or tool. It helps development because packages for one
tool can be installed without changing the system Python or other projects.

Activate the venv on the ORAN host before running `dms_cli`:

```sh
source ~/xapp_onboarder/.venv/bin/activate
```

After activation, the terminal prompt may show `(.venv)` at the beginning.
That means the terminal is inside the xApp onboarder Python environment.

Check that `dms_cli` is available:

```sh
which dms_cli
```

The venv activation is also temporary. If the terminal window closes, or a new
SSH session is opened, activate it again before using `dms_cli`.

## Copy Project To ORAN Host

Start in the local project directory:

```sh
cd /path/to/basic-xapp
```

Set a unique app name:

```sh
APP_NAME=steering-wheel-command-xapp-<name_or_identifier>
```

Try the ORAN host names in this order:

```text
admin@corsairx
admin@corsairx.local
admin@192.168.50.103
```

Use the first address that connects successfully. Use that same address for the
`mkdir`, `scp`, and `ssh` commands.

Create the target folder on the ORAN host:

```sh
ssh admin@corsairx "mkdir -p /tmp/${APP_NAME}"
```

If that host name does not work, try:

```sh
ssh admin@corsairx.local "mkdir -p /tmp/${APP_NAME}"
```

If that also does not work, try:

```sh
ssh admin@192.168.50.103 "mkdir -p /tmp/${APP_NAME}"
```

Copy the project files into `/tmp/<APP_NAME>`.

Using `admin@corsairx`:

```sh
scp -r ./* admin@corsairx:/tmp/${APP_NAME}/
```

Using `admin@corsairx.local`:

```sh
scp -r ./* admin@corsairx.local:/tmp/${APP_NAME}/
```

Using `admin@192.168.50.103`:

```sh
scp -r ./* admin@192.168.50.103:/tmp/${APP_NAME}/
```

After the copy finishes, enter the ORAN host:

```sh
ssh admin@corsairx
```

If needed, use one of the other host addresses:

```sh
ssh admin@corsairx.local
```

```sh
ssh admin@192.168.50.103
```

After SSH login, the terminal starts in the home directory. Move to the copied
project folder:

```sh
cd /tmp/${APP_NAME}
```

Check the files:

```sh
pwd
ls
```

Expected location:

```text
/tmp/steering-wheel-command-xapp-<name_or_identifier>
```

Expected files include:

```text
Dockerfile
config.json
xapp-descriptor.json
steering_xapp.py
steering_service.py
wheel_client.py
```

Stay in this SSH terminal for the build, push, onboard, install, log, and curl
commands below.

Activate the onboarder venv in this SSH terminal:

```sh
source ~/xapp_onboarder/.venv/bin/activate
```

If the prompt starts with `(.venv)`, the xApp onboarder environment is active.

Check `dms_cli`:

```sh
which dms_cli
```

## Terminal Location Check

Before running Docker or `dms_cli`, confirm the terminal is inside the copied
application directory:

```sh
pwd
```

Expected output shape:

```text
/tmp/steering-wheel-command-xapp-team1
```

If the terminal is in the home directory, go to the copied folder:

```sh
cd /tmp/${APP_NAME}
```

## Build From Application Directory

The build command below is run from inside:

```text
/tmp/<APP_NAME>
```

Directory shape:

```text
<APP_NAME>/
  Dockerfile
  steering_xapp.py
  steering_service.py
  wheel_client.py
```

## Dockerfile File Check

Before building, check the `COPY` lines in `Dockerfile`.

The file list should match files that exist in the current folder.

Open the file:

```sh
nano Dockerfile
```

For building from inside `/tmp/<APP_NAME>`, use local filenames in the `COPY`
lines, not `basic-xapp/...` paths.

Use this style:

```dockerfile
COPY steering_xapp.py /opt/xapp/
COPY steering_service.py /opt/xapp/
COPY wheel_client.py /opt/xapp/
COPY xapp-descriptor.json /opt/xapp/
COPY routes.txt /opt/xapp/
COPY README.md /opt/xapp/
COPY config.json /opt/ric/config/config-file.json
```

Avoid this style when building from inside `/tmp/<APP_NAME>`:

```dockerfile
COPY basic-xapp/steering_xapp.py /opt/xapp/
```

Save and exit `nano`:

```text
Ctrl+O
Enter
Ctrl+X
```

Expected project files:

```text
steering_xapp.py
steering_service.py
wheel_client.py
xapp-descriptor.json
routes.txt
README.md
config.json
```

If a `COPY` line names a file that is not in the folder, remove that `COPY`
line or add the missing file before building.

Set the app name again inside the SSH terminal:

```sh
APP_NAME=steering-wheel-command-xapp-<name_or_identifier>
```

Build:

```sh
docker build --network=host -f Dockerfile -t registry.local:5000/${APP_NAME}:1.0.0 .
```

Push:

```sh
docker push registry.local:5000/${APP_NAME}:1.0.0
```

## Onboard

Run from the copied application directory on the ORAN host:

```sh
pwd
```

Expected shape:

```text
/tmp/<APP_NAME>
```

Then onboard:

```sh
dms_cli onboard xapp-descriptor.json config.json
```

## Install

Use the same app name used in the JSON files and Docker image:

```sh
dms_cli install ${APP_NAME} 1.0.0 ricxapp
```

## Logs

View logs:

```sh
kubectl logs -f -n ricxapp -l app=ricxapp-${APP_NAME}
```

## Service IP

Get the HTTP service IP:

```sh
APP_IP=$(kubectl get svc -n ricxapp \
  --field-selector metadata.name=service-ricxapp-${APP_NAME}-http \
  -o jsonpath='{.items[0].spec.clusterIP}')

echo "${APP_IP}"
```

Use `APP_IP` for curl tests:

```sh
curl -s "http://${APP_IP}:8080/ric/v1/health/alive"
curl -s "http://${APP_IP}:8080/ric/v1/steering/state"
```

## Expected Output

- [ ] Unique app name selected.
- [ ] `config.json` `name` changed.
- [ ] `config.json` `xapp_name` changed.
- [ ] `config.json` `json_url` changed.
- [ ] `config.json` messaging container names changed.
- [ ] `xapp-descriptor.json` `xapp_name` changed.
- [ ] `xapp-descriptor.json` `json_url` changed.
- [ ] `xapp-descriptor.json` container name changed.
- [ ] `xapp-descriptor.json` image name changed.
- [ ] `xapp-descriptor.json` messaging container names changed.
- [ ] Docker image built with the same app name.
- [ ] Docker image pushed with the same app name.
- [ ] `dms_cli onboard` completed.
- [ ] `dms_cli install` completed.
- [ ] Logs are visible with `kubectl logs`.
- [ ] Service IP found with `kubectl get svc`.
- [ ] Alive endpoint tested with `APP_IP`.

---

# Task 4: REST Testing With Curl

## Setup

Complete Task 3 first. Use the installed xApp service IP from `APP_IP`.

Check the variable:

```sh
echo "${APP_IP}"
```

If the output is blank, get the service IP again:

```sh
APP_IP=$(kubectl get svc -n ricxapp \
  --field-selector metadata.name=service-ricxapp-${APP_NAME}-http \
  -o jsonpath='{.items[0].spec.clusterIP}')

echo "${APP_IP}"
```

## Test 1: Alive

```sh
curl -s "http://${APP_IP}:8080/ric/v1/health/alive"
```

Expected idea:

```json
{
  "alive": true,
  "name": "steering-wheel-command-xapp"
}
```

## Test 2: State

```sh
curl -s "http://${APP_IP}:8080/ric/v1/steering/state"
```

Look for:

- command count
- rejected count
- stop count
- last command
- stopped state

## Test 3: Send A Valid Command

Use a current timestamp if the service checks stale timestamps.

```sh
curl -s -X POST "http://${APP_IP}:8080/ric/v1/steering/command" \
  -H 'Content-Type: application/json' \
  -d '{"seq":1,"timestamp_ms":123456789,"steering":0.1,"throttle":0.2,"brake":0.0,"enable":true}'
```

## Test 4: Stop

```sh
curl -s -X POST "http://${APP_IP}:8080/ric/v1/steering/stop"
```

## Test 5: Missing Field

This request is missing `brake`.

```sh
curl -s -X POST "http://${APP_IP}:8080/ric/v1/steering/command" \
  -H 'Content-Type: application/json' \
  -d '{"seq":2,"timestamp_ms":123456789,"steering":0.1,"throttle":0.2,"enable":true}'
```

## Test 6: Out-Of-Range Steering

This steering value is outside the normal `-1.0` to `1.0` range.

```sh
curl -s -X POST "http://${APP_IP}:8080/ric/v1/steering/command" \
  -H 'Content-Type: application/json' \
  -d '{"seq":3,"timestamp_ms":123456789,"steering":2.0,"throttle":0.2,"brake":0.0,"enable":true}'
```

## Test 7: Repeated Sequence Number

Send the same `seq` twice.

```sh
curl -s -X POST "http://${APP_IP}:8080/ric/v1/steering/command" \
  -H 'Content-Type: application/json' \
  -d '{"seq":4,"timestamp_ms":123456789,"steering":0.0,"throttle":0.1,"brake":0.0,"enable":true}'
```

```sh
curl -s -X POST "http://${APP_IP}:8080/ric/v1/steering/command" \
  -H 'Content-Type: application/json' \
  -d '{"seq":4,"timestamp_ms":123456789,"steering":0.0,"throttle":0.1,"brake":0.0,"enable":true}'
```

## Expected Output

Expected output for each curl test:

- command used
- success or failure status
- the response body
- short response meaning

---

# Task 5: Robot Payload Mapping Preview

## Goal

Practice converting xApp command JSON into robot movement JSON.

This is preparation for Week 3.

## Normalized Command

Example xApp command:

```json
{
  "steering": 0.25,
  "throttle": 0.6,
  "brake": 0.1,
  "enable": true
}
```

## Mapping Rule

Simple ROS-style mapping:

```text
linear.x = throttle - brake
angular.z = -steering
```

Steering sign note:

```text
positive wheel steering = right
positive ROS angular.z = left
```

Right steering usually becomes negative `angular.z`.

## Example Robot Payload

```json
{
  "linear": {
    "x": 0.5,
    "y": 0.0,
    "z": 0.0
  },
  "angular": {
    "x": 0.0,
    "y": 0.0,
    "z": -0.25
  },
  "enable": true
}
```

## Practice Commands

Map each command into a robot payload.

### Case 1

```json
{
  "steering": 0.0,
  "throttle": 0.4,
  "brake": 0.0,
  "enable": true
}
```

### Case 2

```json
{
  "steering": 0.5,
  "throttle": 0.3,
  "brake": 0.0,
  "enable": true
}
```

### Case 3

```json
{
  "steering": -0.5,
  "throttle": 0.3,
  "brake": 0.0,
  "enable": true
}
```

### Case 4

```json
{
  "steering": 0.0,
  "throttle": 0.0,
  "brake": 1.0,
  "enable": false
}
```

## Expected Output

Expected output for each case:

- `linear.x`
- `angular.z`
- full robot payload JSON
- whether this means forward, stop, left turn, or right turn

---

# Task 6: Timed Physical Wheel Checkout

## Setup

Use the physical wheel after Task 4 curl tests are complete.

Only one group uses the controller at a time. Keep each turn short and note
the results before passing the controller to the next group.

## Before Connecting The Wheel

Check the xApp is reachable:

```sh
curl -s "http://${APP_IP}:8080/ric/v1/health/alive"
```

Check current state:

```sh
curl -s "http://${APP_IP}:8080/ric/v1/steering/state"
```

## Wheel Test

Run the wheel client from the machine connected to the controller.

Example shape:

```sh
python3 wheel_client.py --xapp-url "http://${APP_IP}:8080" --print-commands
```

If the wheel client runs on a different machine, replace `${APP_IP}` with the
reachable xApp service address for that machine.

## Test Motions

Expected output for each motion:

- wheel centered, no pedals
- turn left
- turn right
- light throttle
- light brake
- stop or shutdown

## Rotation Notes

Expected output for each turn with the controller:

- group name
- start time
- end time
- command JSON example
- problem found, if any
- stop command confirmed

## Expected Output

After the controller test, run:

```sh
curl -s "http://${APP_IP}:8080/ric/v1/steering/state"
```

Expected state fields:

- latest command
- command count
- stop count
- rejected count
- stopped status

---

# Task 7: Week 2 Final Notes

## Required Sections

Expected sections:

### 1. What Works

Working items:

Examples:

- read wheel axes
- normalize steering
- normalize throttle and brake
- create command JSON
- send command JSON to the xApp
- send a stop command

### 2. Endpoints Tested

Endpoint test list:

- `GET /ric/v1/health/alive`
- `GET /ric/v1/steering/state`
- `POST /ric/v1/steering/command`
- `POST /ric/v1/steering/stop`

### 3. Wheel Configuration

Axis and button mapping:

Example:

```text
steering_axis = 0
throttle_axis = 1
brake_axis = 2
enable_button = -1
stop_button = -1
```

### 4. Example Command JSON

Example command from the client:

```json
{
  "seq": 1,
  "timestamp_ms": 123456789,
  "steering": 0.1,
  "throttle": 0.2,
  "brake": 0.0,
  "enable": true
}
```

### 5. Known Problems

Known problems:

Examples:

- joystick axis order is different on another computer
- timestamps were stale
- xApp was not reachable
- stop button is not configured
- robot endpoint is not connected yet

### 6. Week 3 Questions

Week 3 questions:

Examples:

- What is the robot base URL?
- Is `/controller/cmd_vel` the correct path?
- Does the robot expect ROS Twist JSON?
- What is the safe maximum forward speed?
- Which direction should positive `angular.z` turn?

---

# Final Checklist

Before leaving, check each item.

- [ ] I can explain the path from wheel input to xApp command.
- [ ] I can show one valid command JSON.
- [ ] I can explain `seq`.
- [ ] I can explain `timestamp_ms`.
- [ ] I can explain steering normalization.
- [ ] I can explain pedal normalization.
- [ ] I tested the alive endpoint.
- [ ] I tested the state endpoint.
- [ ] I tested the command endpoint.
- [ ] I tested the stop endpoint.
- [ ] I tried one bad request and understood the response.
- [ ] I can map throttle/brake to `linear.x`.
- [ ] I can map steering to `angular.z`.

---

# Optional Challenge

Create a small Python dictionary for a command and convert it to JSON text.

```python
import json

command = {
    "seq": 1,
    "timestamp_ms": 123456789,
    "steering": 0.1,
    "throttle": 0.2,
    "brake": 0.0,
    "enable": True,
}

print(json.dumps(command, sort_keys=True))
```

## Expected Output

Change the values and explain the expected robot movement.
