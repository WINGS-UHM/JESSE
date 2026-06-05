# Linux Basics Essentials

## Who This Is For

This guide is for high school students learning how to use a Linux terminal for robotics, programming, servers, or cybersecurity basics.

Linux may look different from Windows or macOS, but the main idea is simple:

> Linux is an operating system that lets you control files, programs, and hardware.

---

## 1. What Is Linux?

Linux is an operating system. An operating system is the main software that helps a computer run.

Examples of operating systems:

| Operating System | Common Use |
|---|---|
| Windows | laptops, desktops |
| macOS | Apple computers |
| Linux | servers, robots, Raspberry Pi, cloud systems |
| Android | phones and tablets |

Linux is popular because it is:

- free and open source
- powerful for programming
- common on servers
- common in robotics and embedded systems
- easy to control from a terminal

---

## 2. What Is A Terminal?

A terminal is a text-based way to control a computer.

Instead of clicking buttons, you type commands.

Example:

```bash
pwd
```

This command prints your current folder.

The terminal is useful because it is:

- fast
- precise
- easy to repeat
- common on servers where there is no normal desktop screen

---

## 3. Commands

A command is an instruction typed into the terminal.

Example:

```bash
ls
```

This lists files in the current folder.

A command can have extra options:

```bash
ls -l
```

The `-l` option means "long format", which shows more details.

---

## 4. Folders And Paths

A path tells Linux where a file or folder is.

Example:

```text
/home/student/projects
```

Linux uses `/` between folder names.

Important path symbols:

| Symbol | Meaning |
|---|---|
| `.` | current folder |
| `..` | parent folder |
| `~` | your home folder |
| `/` | root of the whole system |

Example:

```bash
cd ..
```

This moves up one folder.

---

## 5. Essential Navigation Commands

| Command | Meaning |
|---|---|
| `pwd` | print current folder |
| `ls` | list files |
| `cd folder_name` | move into a folder |
| `cd ..` | move up one folder |
| `cd ~` | move to your home folder |

Example:

```bash
pwd
ls
cd Documents
ls
```

---

## 6. Files And Folders

Useful file commands:

| Command | Meaning |
|---|---|
| `mkdir name` | make a folder |
| `touch file.txt` | create an empty file |
| `cat file.txt` | print a file |
| `cp old new` | copy |
| `mv old new` | move or rename |
| `rm file.txt` | remove a file |

Be careful with `rm`. Deleted files may not go to a trash bin.

Example:

```bash
mkdir practice
cd practice
touch notes.txt
ls
```

---

## 7. Reading Files

There are several ways to read text files.

| Command | Use |
|---|---|
| `cat file.txt` | print the whole file |
| `less file.txt` | view one screen at a time |
| `head file.txt` | show the first lines |
| `tail file.txt` | show the last lines |

Example:

```bash
cat notes.txt
```

---

## 8. Editing Files

Linux has many text editors.

Beginner-friendly examples:

```bash
nano notes.txt
```

or, if using VS Code:

```bash
code notes.txt
```

`nano` runs inside the terminal. It is useful when working on servers.

---

## 9. Permissions

Linux tracks who can read, write, or run a file.

The three common permissions are:

| Permission | Meaning |
|---|---|
| read | see the file contents |
| write | change the file |
| execute | run the file as a program |

You can see permissions with:

```bash
ls -l
```

Example output:

```text
-rw-r--r-- 1 student student 120 notes.txt
```

This looks strange at first, but the main idea is:

> Linux checks whether you are allowed to do something before it lets you do it.

---

## 10. `sudo`

`sudo` means "run this command with administrator power."

Example:

```bash
sudo apt update
```

Use `sudo` carefully. Administrator commands can change important parts of the system.

Rule for beginners:

> Do not use `sudo` unless your teacher or project instructions say to.

---

## 11. Processes

A process is a program that is currently running.

Useful commands:

| Command | Meaning |
|---|---|
| `ps` | show running processes |
| `top` | live view of running processes |
| `Ctrl+C` | stop a running terminal program |

Example:

```bash
top
```

Press `q` to quit `top`.

---

## 12. Package Managers

A package manager installs software.

On many Ubuntu or Debian systems, the package manager is `apt`.

Example:

```bash
sudo apt install python3
```

Think of a package manager like an app store for terminal software.

---

## 13. Network Essentials

Robots and servers often communicate over a network. A network lets computers send information to each other.

For this workshop, the local robot can be reached at:

```text
orin-nx.local
```

or:

```text
192.168.50.67
```

These point to the same robot computer.

The SSH login for the robot is:

```bash
ssh ubuntu@orin-nx.local
```

Meaning:

| Part | Meaning |
|---|---|
| `ssh` | start a secure remote terminal connection |
| `ubuntu` | username on the robot |
| `orin-nx.local` | robot hostname |

---

## 14. Checking Your IP Address

An IP address is a number that identifies a device on a network.

On Linux, check your network addresses with:

```bash
ip addr
```

Shorter version:

```bash
ip a
```

You may see network names like:

| Name | Common Meaning |
|---|---|
| `lo` | loopback, the computer talking to itself |
| `eth0` | wired Ethernet |
| `wlan0` | Wi-Fi |

Look for an address after `inet`.

Example:

```text
inet 192.168.50.20/24
```

This means the computer's IP address is:

```text
192.168.50.20
```

The `/24` is network information. Beginners can mostly focus on the IP address before the slash.

---

## 15. Hostnames And Name Resolution

A hostname is a human-friendly name for a computer.

Example:

```text
orin-nx.local
```

This is easier to remember than:

```text
192.168.50.67
```

Name resolution means:

> The computer turns a name like `orin-nx.local` into an IP address like `192.168.50.67`.

For `.local` names, many systems use a local network discovery system called mDNS.

Simple idea:

> `orin-nx.local` is the friendly name. `192.168.50.67` is the network address.

You can test whether the name resolves by using:

```bash
ping orin-nx.local
```

If it works, you should see replies from `192.168.50.67` or from the robot's current IP address.

---

## 16. `ping`

`ping` checks whether another device can be reached over the network.

Example:

```bash
ping orin-nx.local
```

or:

```bash
ping 192.168.50.67
```

If the robot is reachable, you will see replies.

Example output:

```text
64 bytes from 192.168.50.67: icmp_seq=1 ttl=64 time=2.1 ms
```

Important parts:

| Part | Meaning |
|---|---|
| `64 bytes` | size of the reply |
| `192.168.50.67` | who replied |
| `icmp_seq` | packet number |
| `ttl` | time-to-live network value |
| `time` | how long the reply took |

Press `Ctrl+C` to stop `ping`.

Useful `ping` options:

| Command | Meaning |
|---|---|
| `ping orin-nx.local` | ping until stopped |
| `ping -c 4 orin-nx.local` | send 4 pings, then stop |
| `ping -i 0.5 orin-nx.local` | ping every 0.5 seconds |
| `ping -s 100 orin-nx.local` | send 100-byte ping packets |
| `ping -W 2 orin-nx.local` | wait 2 seconds for each reply |

Good beginner test:

```bash
ping -c 4 orin-nx.local
```

If hostname lookup fails, try the IP address:

```bash
ping -c 4 192.168.50.67
```

If the IP works but the hostname does not, the network may be fine but name resolution may not be working.

---

## 17. Connecting To The Robot With SSH

Once the robot responds to `ping`, try SSH:

```bash
ssh ubuntu@orin-nx.local
```

If the hostname does not work, try the IP address:

```bash
ssh ubuntu@192.168.50.67
```

After connecting, commands run on the robot, not your laptop.

To exit:

```bash
exit
```

Remember:

> Always know whether your terminal is controlling your laptop or the robot.

---

## 18. Wireshark Basics

Wireshark is a program for watching network traffic.

Simple idea:

> Wireshark lets you see packets moving across a network.

A packet is a small piece of network data.

Wireshark can help you understand:

- whether your computer is sending pings
- whether the robot is replying
- what IP addresses are talking
- what protocols are being used

Wireshark is powerful, so use it responsibly. Only capture traffic on networks where your teacher or team has permission.

---

## 19. Installing Wireshark

On Ubuntu or Debian Linux:

```bash
sudo apt update
sudo apt install wireshark
```

During installation, you may be asked whether non-root users should be able to capture packets.

For a classroom machine, your teacher may choose:

```text
Yes
```

If permission is needed later, a teacher may add the user to the `wireshark` group:

```bash
sudo usermod -aG wireshark $USER
```

After that, log out and log back in.

Start Wireshark from the app menu or with:

```bash
wireshark
```

If your system uses a different package manager, ask your teacher for the correct install command.

---

## 20. Wireshark Filters

Wireshark can show a lot of traffic, so filters are important.

A display filter shows only packets that match your filter.

Useful filters:

| Filter | Meaning |
|---|---|
| `ip.addr == 192.168.50.67` | show traffic to or from the robot |
| `icmp` | show ping traffic |
| `ssh` | show SSH traffic |
| `tcp.port == 22` | show SSH port traffic |
| `mdns` | show `.local` hostname discovery traffic |
| `dns` | show DNS lookup traffic |

For this robot, useful filters are:

```text
ip.addr == 192.168.50.67
```

```text
icmp
```

```text
mdns
```

When you run:

```bash
ping -c 4 orin-nx.local
```

try the Wireshark filter:

```text
icmp
```

You should see ping request and reply packets.

When you connect with:

```bash
ssh ubuntu@orin-nx.local
```

try:

```text
tcp.port == 22
```

or:

```text
ssh
```

---

## 21. Why Linux Matters For Robotics

Linux is often used in robotics because it can:

- run Python programs
- connect to sensors
- control motors
- run on small computers like Raspberry Pi
- connect over SSH
- run Docker containers

If you learn the Linux terminal, you can control many real-world systems.

---

## Hands-On Labs

### Lab 1: Terminal Navigation

Run these commands in order:

```bash
pwd
ls
cd ..
pwd
```

Observe how the current folder changes after `cd ..`.

### Lab 2: Make A Project Folder

Create this folder structure:

```text
robot_project/
notes.txt
```

Commands to use:

```bash
mkdir robot_project
cd robot_project
touch notes.txt
ls
```

Add one line to the file:

```bash
nano notes.txt
```

Then print it:

```bash
cat notes.txt
```

### Lab 3: Work With Paths

Move to your home folder, then return to the project folder:

```bash
cd ~
pwd
cd robot_project
pwd
```

Use this path as a reference while watching the output:

```text
/home/student/robot_project/notes.txt
```

### Lab 4: Inspect Permissions

Run:

```bash
ls -l
```

Find `notes.txt` in the output. Look at:

- the file name
- who owns it
- the permission characters at the far left

### Lab 5: Try Safe Process Monitoring

Run:

```bash
top
```

Watch the live process list for a few seconds.

Press:

```text
q
```

to quit.

### Lab 6: Check Network Address

Run:

```bash
ip addr
```

Find one network interface that has an `inet` address. Record:

- interface name
- IP address
- whether it looks like Wi-Fi, Ethernet, or loopback

### Lab 7: Ping The Robot

Run:

```bash
ping -c 4 orin-nx.local
```

Then run:

```bash
ping -c 4 192.168.50.67
```

Observe:

- whether replies appear
- the IP address that replies
- the `time=` value on each reply
- whether the hostname and IP behave the same way

### Lab 8: Connect To The Robot With SSH

Connect to the robot:

```bash
ssh ubuntu@orin-nx.local
```

After login, run:

```bash
pwd
hostname
exit
```

If the hostname does not work, try:

```bash
ssh ubuntu@192.168.50.67
```

### Lab 9: Wireshark Ping Capture

With teacher permission:

1. Open Wireshark.
2. Start capturing on the active network interface.
3. Run:

```bash
ping -c 4 orin-nx.local
```

4. Use this display filter:

```text
icmp
```

Observe:

- ping request packets
- ping reply packets
- the robot IP address in the packet list

### Lab 10: Wireshark Robot Filter

In Wireshark, try this filter:

```text
ip.addr == 192.168.50.67
```

Then run:

```bash
ssh ubuntu@orin-nx.local
```

Then try these filters:

```text
tcp.port == 22
```

```text
ssh
```

Observe which filter shows the SSH connection most clearly.

---

## Cheat Sheet

| Command | Meaning |
|---|---|
| `pwd` | show current folder |
| `ls` | list files |
| `cd` | change folder |
| `mkdir` | make folder |
| `touch` | create file |
| `cat` | print file |
| `cp` | copy |
| `mv` | move or rename |
| `rm` | remove file |
| `ls -l` | show file details |
| `Ctrl+C` | stop a running program |
| `ip addr` | show network addresses |
| `ip a` | shorter version of `ip addr` |
| `ping -c 4 orin-nx.local` | send 4 pings to the robot hostname |
| `ping -c 4 192.168.50.67` | send 4 pings to the robot IP |
| `ssh ubuntu@orin-nx.local` | connect to the robot by hostname |
| `ssh ubuntu@192.168.50.67` | connect to the robot by IP address |
| `sudo apt install wireshark` | install Wireshark on Ubuntu/Debian |

## Wireshark Filter Cheat Sheet

| Filter | Meaning |
|---|---|
| `ip.addr == 192.168.50.67` | traffic to or from the robot |
| `icmp` | ping traffic |
| `ssh` | SSH traffic |
| `tcp.port == 22` | SSH port traffic |
| `mdns` | `.local` hostname discovery |
| `dns` | DNS lookup traffic |
