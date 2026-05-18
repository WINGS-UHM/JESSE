# Hiwonder ROSOrin Pro 2 Jetson Orin NX Super Setup

This guide summarizes the minimum install and bring-up path for a Hiwonder ROSOrin Pro 2 robot using a Jetson Orin NX Super 16GB and a 1TB M.2 SSD.

## Hardware assumptions

- Robot/platform: Hiwonder ROSOrin Pro / ROSOrin Pro 2 chassis with STM32 lower controller, LiDAR, and Aurora930 depth camera.
- Compute: Jetson Orin NX Super 16GB module/controller.
- Storage: user-provided 1TB M.2 NVMe SSD. The Yahboom Orin NX Super docs say the SSD must be M.2 Key M or M.2 Key B+M, not Key B, at least 256GB, with 2280 recommended.
- Host PC: Windows 10 is recommended by both vendor docs for SSD image writing. Ubuntu 22.04 or the vendor VM is needed only for Jetson Linux/Super boot flashing.
- Display: connect a DP display or virtual display dongle for first boot and NoMachine access.
- Power: use the robot battery/charger as documented by Hiwonder; do not charge while the robot is powered on.

## Required downloads

- Hiwonder ROSOrin Pro documentation: https://wiki.hiwonder.com/projects/rosorin-pro/en/latest/
- Hiwonder ROSOrin Pro download folder: https://drive.google.com/drive/folders/1bcFSDrzzCERFSCJZst-LSljqQ7n39bpj
- Hiwonder image flashing tools folder: https://drive.google.com/drive/folders/1uvSJQj1So71ljqpwb4xJuxOnK7N1OYPZ?usp=sharing
- Yahboom Jetson Orin NX Super documentation source: https://www.yahboom.net/study/Orin-NX-SUPER
- Yahboom Jetson Orin NX Super GitHub docs: https://github.com/YahboomTechnology/Jetson-ORIN-NX-SUPER
- Yahboom download folder from the docs annex: https://drive.google.com/drive/folders/1iblAdrVDlsC2o59XiJ10GEjzVwwDGApR?usp=drive_link
- DiskGenius: https://www.diskgenius.com/
- Win32DiskImager: https://sourceforge.net/projects/win32diskimager/
- NVIDIA Jetson Linux 36.4.3 / JetPack 6.2 page: https://developer.nvidia.com/embedded/jetson-linux-r3643
- NVIDIA Driver Package BSP: https://developer.nvidia.com/downloads/embedded/l4t/r36_release_v4.3/release/Jetson_Linux_r36.4.3_aarch64.tbz2
- NVIDIA Sample Root Filesystem: https://developer.nvidia.com/downloads/embedded/l4t/r36_release_v4.3/release/Tegra_Linux_Sample-Root-Filesystem_r36.4.3_aarch64.tbz2

Needs verification: the Hiwonder wiki exposes the download folder but not a single direct image filename in the rendered page. For a complete robot install, prefer the Hiwonder ROSOrin Pro Jetson Orin NX SSD image from the Hiwonder Drive folder if present. Use the Yahboom factory image only for the Yahboom Jetson carrier/tutorial environment; it may not include Hiwonder robot packages.

## SSD flashing steps

1. On the Windows host, insert the 1TB SSD into an NVMe-to-USB enclosure/writer.
2. Download the matching factory image:
   - Preferred: Hiwonder ROSOrin Pro / Jetson Orin NX SSD image from the Hiwonder download folder.
   - Alternate for board-only Yahboom bring-up: Yahboom Orin NX Super factory image from the Yahboom download folder.
3. Extract the image locally. The image path should contain only English characters.
4. Open DiskGenius, select the SSD by size/device, delete all partitions, create a new recognizable partition, and save changes.
5. Open Win32DiskImager as administrator.
6. Select the extracted `*.img` file.
7. Select the SSD drive letter. Confirm this is the SSD, not a PC internal disk.
8. Click Write and wait for Write Successful.
9. If Windows prompts to format newly visible partitions after writing, cancel the prompt.
10. Install the SSD in the Jetson Orin NX controller.

## Boot from SSD

1. Confirm Super Boot is already flashed. The Yahboom docs state their package ships with Super Boot by default.
2. If Super Boot is not present, put the Jetson into recovery mode by shorting FC REC to GND, connect DC power plus USB-C to the Ubuntu 22.04 host or vendor VM, and verify `lsusb` shows `NVIDIA Corp. APX`.
3. In the vendor VM, run:

```bash
cd ~/jetpack_6.2/Linux_for_Tegra
sudo ./yahboom_flash.sh.x
```

4. Power off, remove the REC/GND jumper, keep the SSD installed, connect DP display, and power on.
5. Wait for the system to boot. On the Hiwonder robot, LED1 should blink in AP mode and a short beep should indicate startup completion.

## First boot checklist

- Connect a DP monitor or virtual display dongle before graphical remote access.
- Hiwonder AP mode:
  - Wi-Fi SSID starts with `HW`
  - Wi-Fi password: `hiwonder`
  - AP IP: `192.168.149.1`
  - Jetson Orin NX login: `ubuntu` / `ubuntu`
- Yahboom board image default:
  - Login: `jetson` / `yahboom`
- Connect with NoMachine for Jetson controllers, or SSH/MobaXterm for command-line access.
- Hiwonder ROS workspace should exist at:

```bash
ls
cd ~/ros2_ws
ls
cd ~/ros2_ws/src
ls
```

Expected Hiwonder source directories include `app`, `interfaces`, `bringup`, `driver`, `peripherals`, `calibration`, `navigation`, and `slam`.

## Jetson Super mode verification

Verify OS and JetPack/L4T:

```bash
cat /etc/os-release
uname -a
cat /etc/nv_tegra_release
```

Verify power modes:

```bash
sudo nvpmodel -q
sudo nvpmodel -m 0
sudo jetson_clocks
```

Optional monitor:

```bash
sudo apt update
sudo apt install python3-pip -y
sudo pip3 install -U jetson-stats
sudo reboot
jtop
```

The NVIDIA Jetson Linux 36.4.3 page maps to JetPack 6.2 and lists Super/MAXN modes for Jetson Orin NX 16GB. Needs verification: confirm the flashed image is based on Jetson Linux 36.4.3 / JetPack 6.2 or newer before assuming Super mode support.

## ROS environment verification

Use a ROS2 terminal:

```bash
source /opt/ros/humble/setup.bash
source ~/ros2_ws/install/setup.bash
ros2 --version
ros2 pkg list | head
ros2 node list
ros2 topic list
```

If the Hiwonder image is used, ROS 2 Humble should be preinstalled on Ubuntu 22.04 for Jetson Orin Nano / Orin NX controllers.

## Hiwonder robot dependencies

The Hiwonder robot image should already contain the required workspace and packages. Verify them instead of reinstalling blindly:

```bash
cd ~/ros2_ws/src
ls app interfaces bringup driver peripherals calibration
ros2 pkg list | grep -E 'controller|peripherals|interfaces|app|ros_robot_controller'
```

Needs verification: if these packages are missing, install or restore the Hiwonder ROSOrin Pro Jetson Orin NX image from the Hiwonder download folder. The public page does not provide a command-only dependency installer for rebuilding the robot stack from a clean JetPack image.

## Robot chassis bring-up

Put the robot on a flat open floor. Stop the app auto-start service before manual command tests:

```bash
sudo systemctl stop start_app_node.service
```

Start chassis control:

```bash
ros2 launch controller controller.launch.py
```

In another terminal, send a slow forward command:

```bash
ros2 topic pub -1 /controller/cmd_vel geometry_msgs/msg/Twist "{linear: {x: 0.10, y: 0.0, z: 0.0}, angular: {x: 0.0, y: 0.0, z: 0.0}}"
```

Stop the robot:

```bash
ros2 topic pub -1 /controller/cmd_vel geometry_msgs/msg/Twist "{linear: {x: 0.0, y: 0.0, z: 0.0}, angular: {x: 0.0, y: 0.0, z: 0.0}}"
```

Test a slow turn:

```bash
ros2 topic pub -1 /controller/cmd_vel geometry_msgs/msg/Twist "{linear: {x: 0.0, y: 0.0, z: 0.0}, angular: {x: 0.0, y: 0.0, z: 0.20}}"
ros2 topic pub -1 /controller/cmd_vel geometry_msgs/msg/Twist "{linear: {x: 0.0, y: 0.0, z: 0.0}, angular: {x: 0.0, y: 0.0, z: 0.0}}"
```

## Basic ROS topics and movement verification

IMU:

```bash
sudo systemctl stop start_app_node.service
ros2 launch ros_robot_controller ros_robot_controller.launch.py
ros2 launch peripherals imu_filter.launch.py
ros2 topic list
ros2 topic info /imu
ros2 topic echo /imu
```

Odometry:

```bash
sudo systemctl stop start_app_node.service
ros2 launch controller odom_publisher.launch.py
ros2 topic list
ros2 topic info /odom_raw
ros2 topic echo /odom_raw
```

Expected topics include `/imu`, `/odom_raw`, and `/controller/cmd_vel` when the relevant services are running.

## Basic camera verification

Hiwonder ROSOrin Pro uses an Aurora930 depth camera. If the package is installed:

```bash
ros2 launch deptrum-ros-driver-aurora930 aurora930_launch.py
```

In another terminal:

```bash
ros2 topic list | grep -E 'image|camera|depth|point'
ros2 launch deptrum-ros-driver-aurora930 viewer930_launch.py
```

Needs verification: the Hiwonder robot image may use a preintegrated camera launch path rather than the standalone Aurora930 package name above. If the launch file is missing, search the installed workspace:

```bash
find ~/ros2_ws/src \( -iname '*aurora*' -o -iname '*camera*' \)
```

## Basic LiDAR verification

Physical check: the LiDAR should light and rotate after startup.

Command check:

```bash
sudo systemctl stop start_app_node.service
ros2 launch app lidar_node.launch.py debug:=true
```

In another terminal:

```bash
ros2 service call /lidar_app/enter std_srvs/srv/Trigger {}
ros2 service call /lidar_app/set_running interfaces/srv/SetInt64 "{data: 1}"
ros2 service call /lidar_app/set_running interfaces/srv/SetInt64 "{data: 0}"
ros2 topic list | grep -E 'scan|lidar|laser'
```

Use `{data: 1}` for obstacle avoidance, `{data: 2}` for following, and `{data: 3}` for guarding. Keep the robot in a clear area before enabling any LiDAR behavior because these modes can move the chassis.

## Troubleshooting notes

- SSD does not boot: confirm the SSD image matches the JetPack/L4T version expected by the boot firmware. Yahboom notes that Jetson boot depends on JetPack version and mismatches may fail.
- No `HW` hotspot: long-press KEY1 for 5-10 seconds to return to AP mode. If LED1 does not blink, reseat or reflash the SSD.
- Remote desktop blank or unavailable: attach a DP monitor or virtual display dongle before using NoMachine on Jetson Orin Nano / Orin NX.
- Manual ROS commands do nothing: stop `start_app_node.service`, then start the required launch file manually.
- Robot keeps moving after a test: publish a zero `/controller/cmd_vel` command before pressing Ctrl+C.
- Missing Hiwonder packages: reflash the Hiwonder ROSOrin Pro image; the public docs do not list a clean-image dependency bootstrap script.
- LiDAR/camera topics missing: verify USB/serial wiring, confirm the device appears physically, then search the workspace for the actual launch file names.

## Final checklist

- [ ] Downloaded the matching Hiwonder ROSOrin Pro Jetson Orin NX image, or marked the image filename as Needs verification.
- [ ] Flashed the 1TB SSD with DiskGenius and Win32DiskImager.
- [ ] Installed SSD in the Jetson Orin NX controller.
- [ ] Confirmed Super Boot or flashed Super Boot for JetPack 6.2.
- [ ] Booted with DP display or display dongle connected.
- [ ] Logged in over AP mode or LAN.
- [ ] Verified Ubuntu version and JetPack/L4T version.
- [ ] Verified or enabled Super/MAXN mode.
- [ ] Confirmed `~/ros2_ws/src` contains Hiwonder robot packages.
- [ ] Verified ROS 2 Humble commands work.
- [ ] Stopped app service before manual chassis tests.
- [ ] Sent a low-speed `/controller/cmd_vel` movement command and then a stop command.
- [ ] Verified `/imu` and `/odom_raw`.
- [ ] Verified basic camera topics or RViz viewer.
- [ ] Verified LiDAR physical rotation and basic ROS/service bring-up.
