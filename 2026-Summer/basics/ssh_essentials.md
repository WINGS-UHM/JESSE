# SSH Essentials

## Who This Is For

This guide is for high school students learning how to connect to another computer from the terminal.

SSH is common in robotics, Raspberry Pi projects, servers, cloud systems, and remote development.

---

## 1. What Is SSH?

SSH stands for Secure Shell.

SSH lets you control another computer through a secure terminal connection.

Simple idea:

> SSH lets you log in to a remote computer and type commands as if you were sitting in front of it.

Example:

```bash
ssh student@192.168.1.20
```

This means:

> Connect as user `student` to the computer at `192.168.1.20`.

---

## 2. Why Use SSH?

SSH is useful when:

- a robot has no keyboard or screen
- a Raspberry Pi is mounted inside a project
- a server is in another room or building
- a cloud computer is far away
- you need to control a computer over a network

For robotics, SSH is very useful because you can program or restart a robot without plugging in a monitor.

---

## 3. Client And Server

SSH has two sides:

| Side | Meaning |
|---|---|
| SSH client | the computer you are typing from |
| SSH server | the computer you are connecting to |

Example:

If your laptop connects to a Raspberry Pi:

- your laptop is the SSH client
- the Raspberry Pi is the SSH server

---

## 4. Usernames And Hosts

An SSH command usually looks like this:

```bash
ssh username@host
```

Example:

```bash
ssh pi@192.168.1.42
```

Parts:

| Part | Meaning |
|---|---|
| `ssh` | start an SSH connection |
| `pi` | username |
| `192.168.1.42` | host address |
| `@` | separates username and host |

The host can be:

- an IP address
- a computer name
- a domain name

---

## 5. IP Addresses

An IP address is a number that identifies a device on a network.

Example:

```text
192.168.1.42
```

On a local network, devices often have addresses that start with:

```text
192.168.
10.
172.16.
```

If you do not know the remote computer's IP address, you cannot SSH into it yet.

---

## 6. Password Login

The simplest SSH login uses a password.

Example:

```bash
ssh student@192.168.1.20
```

Then SSH may ask:

```text
student@192.168.1.20's password:
```

When typing a password in the terminal, it may look like nothing is happening. That is normal. The terminal hides password characters for security.

---

## 7. SSH Keys

SSH keys are a more secure way to log in.

An SSH key pair has two parts:

| Key | Meaning |
|---|---|
| private key | stays on your computer |
| public key | can be copied to the remote computer |

Simple idea:

> The public key is like a lock. The private key is like the matching key that opens it.

Never share your private key.

---

## 8. Creating An SSH Key

A common command is:

```bash
ssh-keygen
```

This creates key files, often in:

```text
~/.ssh/
```

Common files:

| File | Meaning |
|---|---|
| `id_rsa` or `id_ed25519` | private key |
| `id_rsa.pub` or `id_ed25519.pub` | public key |

Again:

> Do not share the private key.

---

## 9. First Connection Warning

The first time you connect, SSH may show a message like:

```text
Are you sure you want to continue connecting?
```

This happens because your computer has not seen that remote computer before.

If your teacher confirms the address is correct, type:

```text
yes
```

SSH saves the remote computer in a file called `known_hosts`.

---

## 10. Running Commands Remotely

After connecting with SSH, commands run on the remote computer.

Example:

```bash
pwd
ls
python3 robot.py
```

If you are SSH'd into a Raspberry Pi, those commands run on the Raspberry Pi, not your laptop.

This is one of the most important ideas:

> Always know which computer your terminal is controlling.

---

## 11. Exiting SSH

To leave an SSH session:

```bash
exit
```

or press:

```text
Ctrl+D
```

Then your terminal returns to your local computer.

---

## 12. Copying Files With SCP

`scp` copies files over SSH.

Copy a file from your computer to a remote computer:

```bash
scp program.py student@192.168.1.20:/home/student/
```

Copy a file from remote computer to your computer:

```bash
scp student@192.168.1.20:/home/student/log.txt .
```

The `.` at the end means "copy here, into the current folder."

---

## 13. SSH Config

Typing a full SSH command can get annoying.

SSH can use a config file:

```text
~/.ssh/config
```

Example:

```text
Host robot
    HostName 192.168.1.20
    User student
```

Then you can connect with:

```bash
ssh robot
```

This is easier to remember.

---

## 14. Safety Rules

SSH gives remote access to a computer, so use it carefully.

Rules:

- Do not share passwords.
- Do not share private keys.
- Check the IP address before connecting.
- Use `exit` when finished.
- Do not run commands you do not understand.
- Be careful with `sudo` on a remote machine.

---

## 15. Common SSH Commands

| Command | Meaning |
|---|---|
| `ssh user@host` | connect to remote computer |
| `exit` | leave SSH session |
| `ssh-keygen` | create SSH keys |
| `scp file user@host:/path` | copy file to remote computer |
| `scp user@host:/path/file .` | copy file from remote computer |

---

## Hands-On Labs

### Lab 1: Check SSH Client

Run:

```bash
ssh -V
```

Observe the installed SSH version.

### Lab 2: Connect To A Robot Or Remote Computer

Use the connection information your teacher provides.

Example:

```bash
ssh student@192.168.1.20
```

After connecting, run:

```bash
pwd
hostname
whoami
exit
```

Observe how the terminal changes when you enter and leave the SSH session.

### Lab 3: Run A Remote Python Command

You SSH into a robot and run:

```bash
python3 robot.py
```

Watch the output on the SSH terminal. The command runs on the remote computer.

### Lab 4: Copy A File To A Remote Computer

Create a local file:

```bash
echo "hello remote computer" > main.py
```

Copy it to the remote computer:

```bash
scp main.py student@192.168.1.50:/home/student/
```

SSH in and check that the file arrived:

```bash
ssh student@192.168.1.50
ls /home/student/
exit
```

### Lab 5: Copy A File Back

Copy a remote file back to the current local folder:

```bash
scp student@192.168.1.50:/home/student/main.py .
```

Run:

```bash
ls
cat main.py
```

### Lab 6: Create An SSH Shortcut

Create or edit:

```bash
nano ~/.ssh/config
```

Add:

```text
Host robot
    HostName 192.168.0.25
    User robot
```

Connect using the shortcut:

```bash
ssh robot
```

Then run:

```bash
cd /home/robot/project
ls
exit
```
