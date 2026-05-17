# 2026 Summer Robotics Testbed

This folder documents the 2026 Summer robotics platform and supporting hardware. The primary system is a Hiwonder ROSOrin Pro ROS2 smart car configured with the Jetson Orin NX Super 16GB compute board. The platform is intended for ROS2 robotics development, autonomy experiments, perception, manipulation, SLAM mapping, navigation, and edge AI model deployment.

## O-RAN Drive: xApp-Enabled Remote Robot Control


The main objective of this project is to develop an O-RAN-enabled remote control testbed where a physical steering wheel interface commands the ROSOrin Pro robot through xApps. The system will explore how O-RAN control loops, edge intelligence, and ROS2-based robotic actuation can work together to support responsive, network-aware remote driving and autonomy experiments.

## Testbed Overview

<img src="https://www.hiwonder.com/cdn/shop/files/1_b22145a8-2098-496d-80f0-c5c310ef0bfa.jpg?v=1774351062" alt="Hiwonder ROSOrin Pro" width="420">

| Component | Specification |
| --- | --- |
| Mobile platform | Hiwonder ROSOrin Pro ROS2 smart car |
| Compute board | Jetson Orin NX Super 16GB |
| Robot software base | ROS2-focused platform |
| Mobility | Smart car chassis for autonomous driving, mapping, navigation, tracking, and obstacle avoidance experiments |
| Manipulation | Integrated 6DOF robotic arm with intelligent bus servos |
| 3D perception | 3D depth camera for object detection, tracking, pose-related perception, line following, and face tracking |
| Navigation sensing | COIN-D6 / TOF LiDAR for SLAM, obstacle avoidance, target following, and point navigation |
| Interaction | AI voice interaction module with online/offline voice capabilities |
| AI workflow | Supports multimodal AI model use, online APIs, local offline deployment, and OpenClaw agent integration |

## Robot Platform

The robot is the [Hiwonder ROSOrin Pro ROS2 Smart Car](https://www.hiwonder.com/products/rosorin-pro?variant=42638547583063), selected in the Jetson Orin NX Super 16GB configuration. Hiwonder describes ROSOrin Pro as an advanced ROS education and development platform that combines mobile autonomy, 3D vision, a 6DOF arm, LiDAR, voice interaction, and multimodal AI support.

Key platform capabilities:

- ROS2-based motion control and robotics development.
- SLAM mapping, path planning, fixed-point and multi-point navigation.
- Dynamic obstacle avoidance, tracking, and target following.
- 3D object recognition, object positioning, grasping, sorting, and transport.
- Voice and text interaction through the AI voice module and OpenClaw agent workflow.
- Online AI model access and local offline model deployment for embodied AI experiments.

## Compute Board

<img src="https://raw.githubusercontent.com/YahboomTechnology/Jetson-ORIN-NX-SUPER/main/NVIDIA_JETSON_ORIN_NX_SUPER.jpg" alt="Yahboom Jetson Orin NX Super" width="420">

The compute board is the [Yahboom Jetson Orin NX Super 16GB](https://www.yahboom.net/study/Orin-NX-SUPER). Yahboom's Jetson Orin NX Super developer kit is built around NVIDIA's Jetson Orin NX module and a Yahboom carrier board. The 16GB version is listed by Yahboom as reaching up to 157 TOPS, with the kit including a prepared 256GB M.2 SSD, Wi-Fi card/antenna, power supply, and supporting accessories.

Training and setup resources:

- [Yahboom Orin NX Super tutorials](https://www.yahboom.net/study/Orin-NX-SUPER)
- [Yahboom Jetson Orin NX Super GitHub repository](https://github.com/YahboomTechnology/Jetson-ORIN-NX-SUPER)
- Course areas include getting started, Jetson basics, networking, SSH, VNC, GPIO, I2C, serial communication, camera preview, OpenCV, PyTorch/TensorFlow, DeepStream, YOLO, Docker, ROS1, ROS2 Humble, offline AI models, online AI models, Isaac ROS, and OpenClaw advanced development.

## Facilities Testbed Visuals

<img src="https://www.hiwonder.com/cdn/shop/files/ai_ad26602f-008b-4d0f-a9c4-91d866976819.jpg?v=1774351074" alt="ROSOrin Pro AI capabilities" width="420">

These vendor images are included as visual references for the lab/facilities testbed documentation:

- Hiwonder ROSOrin Pro product image: platform with smart car chassis, sensor stack, and robotic arm.
- Hiwonder AI capability image: multimodal AI / OpenClaw-oriented testbed workflow.
- Yahboom Jetson Orin NX Super image: compute board used for edge AI and ROS development.

## Development Focus

This hardware stack supports summer work in:

- ROS2 Humble development and robot bring-up.
- Autonomous navigation and SLAM.
- Depth-camera perception and object-level reasoning.
- Mobile manipulation using the 6DOF arm.
- Edge AI inference on Jetson Orin NX Super.
- Multimodal interaction using voice, vision, text commands, and OpenClaw agent workflows.
- Offline and online large-model experiments for robotics.

## Source Links

- Robot: [Hiwonder ROSOrin Pro ROS2 Smart Car](https://www.hiwonder.com/products/rosorin-pro?variant=42638547583063)
- Jetson tutorials: [Yahboom Jetson Orin NX Super study page](https://www.yahboom.net/study/Orin-NX-SUPER)
- Jetson repository/specification reference: [YahboomTechnology/Jetson-ORIN-NX-SUPER](https://github.com/YahboomTechnology/Jetson-ORIN-NX-SUPER)
