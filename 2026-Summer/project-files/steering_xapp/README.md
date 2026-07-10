# xApp Setup And Deployment

This guide assumes the xApp files are in:

```text
steering_xapp/
```

Run build and onboarding commands from inside that directory unless noted otherwise.

## Files

- `steering_xapp.py`: main xApp process and REST handlers.
- `steering_service.py`: steering validation, mapping, deadman, robot forwarding, and state.
- `config.json`: runtime config mounted/read by the xApp.
- `xapp-descriptor.json`: descriptor used by `dms_cli onboard`.
- `Dockerfile`: container build definition.
- `routes.txt`: RMR seed route file.
- `rosbridge_forwarder.py`: helper that runs near/in the core network path and forwards to robot ROS bridge.

## Build Image

The image name in the descriptor is:

```text
registry.local:5000/steering-xapp:1.0.0
```

Build from inside `steering_xapp/`:

```bash
docker build --network=host -t registry.local:5000/steering-xapp:1.0.0 .
```

Push to the local registry:

```bash
docker push registry.local:5000/steering-xapp:1.0.0
```

`docker push` does not have a no-cache flag. Use `docker build --no-cache ...` when a clean rebuild is needed.

## Dockerfile Notes

The Dockerfile installs:

- `ricxappframe` through `pip`
- O-RAN RMR native library package `rmr_4.9.4_amd64.deb`
- `websocket-client`, `pygame`, `numpy`, and `pillow`

The local `ricxappframe` reference folder is not copied into the image. In deployment, the package is imported from the normal Python package location.

## Onboard And Install

From inside `steering_xapp/`:

```bash
dms_cli onboard xapp-descriptor.json config.json
```

Install into the `ricxapp` namespace:

```bash
dms_cli install steering-xapp 1.0.0 ricxapp
```

Check pod and service:

```bash
kubectl -n ricxapp get pods -l app=ricxapp-steering-xapp -o wide
kubectl -n ricxapp get svc service-ricxapp-steering-xapp-http
```

## Expose xApp HTTP Service

For testing from a separate host, patch the xApp HTTP service to `LoadBalancer`:

```bash
kubectl -n ricxapp patch svc service-ricxapp-steering-xapp-http -p '{"spec":{"type":"LoadBalancer"}}'
```

Get the xApp service IP:

```bash
APP_IP=$(kubectl get svc -n ricxapp --field-selector metadata.name=service-ricxapp-steering-xapp-http -o jsonpath='{.items[0].status.loadBalancer.ingress[0].ip}')
echo "$APP_IP"
```

If the load balancer IP is not assigned, inspect the service:

```bash
kubectl -n ricxapp get svc service-ricxapp-steering-xapp-http -o wide
```

## Health Checks

```bash
curl -s http://$APP_IP:8080/ric/v1/health/alive | jq
curl -s http://$APP_IP:8080/ric/v1/health/ready | jq
curl -s http://$APP_IP:8080/ric/v1/config | jq
```

Expected alive response:

```json
{
  "alive": true,
  "name": "steering-xapp"
}
```

## Steering API

Send one command:

```bash
curl -s -X POST http://$APP_IP:8080/ric/v1/steering/command \
  -H "Content-Type: application/json" \
  -d '{"seq":1,"timestamp_ms":1783540917501,"steering":0.0,"throttle":0.2,"brake":0.0,"enable":true}' | jq
```

Stop:

```bash
curl -s -X POST http://$APP_IP:8080/ric/v1/steering/stop | jq
```

State:

```bash
curl -s http://$APP_IP:8080/ric/v1/steering/state | jq
```

Useful state fields:

- `.state.last_command`: last accepted normalized command.
- `.state.last_mapped_payload`: payload sent toward the robot/CN forwarder.
- `.state.last_robot_status`: last response/error from the CN forwarder.
- `.robot.base_url`: configured CN forwarder URL.

## Arm API

Get current arm state:

```bash
curl -s http://$APP_IP:8080/ric/v1/arm/state | jq
```

Send a full arm pose:

```bash
curl -s -X POST http://$APP_IP:8080/ric/v1/arm/pose \
  -H "Content-Type: application/json" \
  -d '{"duration":1.0,"positions":[{"id":1,"position":500},{"id":2,"position":725},{"id":3,"position":50},{"id":4,"position":150},{"id":5,"position":500},{"id":10,"position":500}]}' | jq
```

## Video API

RGB stream:

```bash
curl --max-time 5 -o rgb_stream.mjpeg "http://$APP_IP:8080/ric/v1/video/stream?topic=/depth_cam/rgb0/image_raw&width=640&height=400&quality=60"
```

IR stream:

```bash
curl --max-time 5 -o ir_stream.mjpeg "http://$APP_IP:8080/ric/v1/video/stream?topic=/depth_cam/ir0/image_raw&width=640&height=400&quality=60"
```

Depth stream uses the xApp depth route:

```bash
curl --max-time 5 -o depth_stream.mjpeg "http://$APP_IP:8080/ric/v1/video/depth/stream?topic=/depth_cam/depth0/image_raw&width=640&height=400&quality=60"
```

Convert MJPEG capture to MP4:

```bash
ffmpeg -y -f mjpeg -i rgb_stream.mjpeg -c:v libx264 -pix_fmt yuv420p rgb_stream.mp4
```

## CN Forwarder

Run `rosbridge_forwarder.py` where it can reach the robot UE IP and ROS bridge/web video server:

```bash
python3 rosbridge_forwarder.py
```

Default important paths:

- HTTP listen: `0.0.0.0:8090`
- Robot ROS bridge: `ws://10.45.1.3:9090`
- Robot web video server: `http://10.45.1.3:8080`
- Movement topic: `/cmd_vel`
- Arm topic: `/servo_controller`

Health check:

```bash
curl -i http://10.233.56.235:8090/health
```

Command path test:

```bash
curl -i --max-time 8 -X POST http://10.233.56.235:8090/cmd_vel \
  -H "Content-Type: application/json" \
  -d '{"linear":{"x":0.0,"y":0.0,"z":0.0},"angular":{"x":0.0,"y":0.0,"z":0.0},"enable":false}'
```

Expected working response:

```text
HTTP/1.0 202 Accepted
```

Robot ROS bridge probe from CN:

```bash
curl -i --max-time 5 http://10.45.1.3:9090
```

Expected response:

```text
HTTP/1.1 400 Bad Request
Can "Upgrade" only to "WebSocket"
```

## Troubleshooting

If video works but movement does not, remember these are different robot paths:

```text
RGB/IR/YOLO video -> robot web_video_server :8080
movement/arm/depth raw -> robot rosbridge :9090
```

If `/cmd_vel` returns `502`, check:

```bash
nc -vz -w 5 10.45.1.3 9090
curl -i --max-time 5 http://10.45.1.3:9090
```

If xApp state shows old video/depth requests after the GUI is closed, restart the xApp pod:

```bash
kubectl -n ricxapp delete pod <STEERING_XAPP_POD>
```

Find the pod:

```bash
kubectl get pods -A -o wide | grep ricxapp-steering-xapp
```
