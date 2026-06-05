# Docker Essentials

## Who This Is For

This guide is for high school students who have basic terminal experience and want to understand Docker at a beginner level.

Docker is often used in robotics, web apps, data science, and server projects.

---

## 1. What Problem Does Docker Solve?

Sometimes a program works on one computer but not another.

Reasons this can happen:

- different Python versions
- missing libraries
- different operating systems
- different settings
- installed software conflicts

Docker helps by packaging an app with the environment it needs.

Simple idea:

> Docker lets you run a program inside a predictable mini-environment.

---

## 2. Containers

A container is a lightweight environment for running an app.

It usually includes:

- the app
- libraries the app needs
- settings
- tools needed to run it

A container is not a full computer. It shares the host computer's operating system, which makes it faster and smaller than a virtual machine.

---

## 3. Images

An image is the recipe or template for a container.

If an image is like a class handout, a container is like one student using that handout.

| Concept | Meaning |
|---|---|
| Image | saved recipe/template |
| Container | running copy of an image |

Example:

```bash
docker run hello-world
```

This downloads a simple image and runs it as a container.

---

## 4. Dockerfile

A `Dockerfile` is a text file that tells Docker how to build an image.

Example:

```Dockerfile
FROM python:3.12
WORKDIR /app
COPY . .
CMD ["python", "main.py"]
```

What each line means:

| Line | Meaning |
|---|---|
| `FROM python:3.12` | start with a Python image |
| `WORKDIR /app` | use `/app` as the folder inside the container |
| `COPY . .` | copy project files into the container |
| `CMD ...` | command to run when the container starts |

---

## 5. Building An Image

To build an image from a Dockerfile:

```bash
docker build -t my-python-app .
```

Meaning:

| Part | Meaning |
|---|---|
| `docker build` | build an image |
| `-t my-python-app` | give the image a name |
| `.` | use the current folder |

---

## 6. Running A Container

To run a container:

```bash
docker run my-python-app
```

If the program prints output, you will see it in the terminal.

---

## 7. Listing Images And Containers

Useful commands:

```bash
docker images
```

Shows downloaded or built images.

```bash
docker ps
```

Shows currently running containers.

```bash
docker ps -a
```

Shows running and stopped containers.

---

## 8. Stopping Containers

If a container keeps running, you can stop it.

```bash
docker stop container_name_or_id
```

You can find the container ID with:

```bash
docker ps
```

---

## 9. Ports

Some containers run web apps. A web app needs a port.

A port is like a numbered doorway into a computer.

Example:

```bash
docker run -p 8080:80 nginx
```

Meaning:

| Part | Meaning |
|---|---|
| `8080` | port on your computer |
| `80` | port inside the container |
| `-p 8080:80` | connect them |

Then you may open:

```text
http://localhost:8080
```

---

## 10. Volumes

Containers are temporary. If you delete a container, files inside it may disappear.

A volume lets a container use a folder from your real computer.

Example:

```bash
docker run -v "$PWD":/app python:3.12
```

Simple idea:

> A volume connects a real folder to a folder inside the container.

---

## 11. Docker Compose

Docker Compose helps run multiple containers together.

For example, a website might need:

- one container for the web app
- one container for a database

Compose uses a file usually named:

```text
docker-compose.yml
```

or:

```text
compose.yml
```

Example:

```yaml
services:
  web:
    image: nginx
    ports:
      - "8080:80"
```

Then run:

```bash
docker compose up
```

---

## 12. Why Docker Matters

Docker is useful because it helps teams:

- run the same app on different computers
- avoid setup problems
- test code in a clean environment
- deploy apps to servers
- package robotics or AI tools

Docker does not replace learning Linux or programming. It helps organize and run software more reliably.

---

## 13. Common Docker Commands

| Command | Meaning |
|---|---|
| `docker --version` | check Docker version |
| `docker run IMAGE` | run an image as a container |
| `docker build -t NAME .` | build an image |
| `docker images` | list images |
| `docker ps` | list running containers |
| `docker ps -a` | list all containers |
| `docker stop ID` | stop a container |
| `docker compose up` | start Compose services |
| `docker compose down` | stop Compose services |

---

## Hands-On Labs

### Lab 1: Check Docker

Run:

```bash
docker --version
```

Then run:

```bash
docker ps
```

Observe whether Docker is installed and whether any containers are running.

### Lab 2: Run Hello World

Run:

```bash
docker run hello-world
```

Observe the message printed by the container.

Then check containers:

```bash
docker ps -a
```

### Lab 3: Create A Small Python App

Create a folder:

```bash
mkdir docker_python_lab
cd docker_python_lab
```

Create a file named `main.py`:

```python
print("Hello from inside Docker!")
```

### Lab 4: Create A Dockerfile

Create a file named `Dockerfile`:

```Dockerfile
FROM python:3.12
WORKDIR /app
COPY . .
CMD ["python", "main.py"]
```

Observe how each Dockerfile line describes one setup step.

### Lab 5: Build The Image

```bash
docker build -t robot-app .
```

Then list images:

```bash
docker images
```

Look for `robot-app`.

### Lab 6: Run The Container

```bash
docker run robot-app
```

Observe the Python message printed from inside the container.

### Lab 7: Try Port Mapping

Run a simple web server container:

```bash
docker run -p 8080:80 nginx
```

Open this in a browser:

```text
http://localhost:8080
```

Stop the container with `Ctrl+C`.

### Lab 8: Use Docker Compose

Create a file named `compose.yml`:

```yaml
services:
  web:
    image: nginx
    ports:
      - "8080:80"
```

Start it:

```bash
docker compose up
```

Open:

```text
http://localhost:8080
```

Stop it with `Ctrl+C`, then clean up:

```bash
docker compose down
```

### Lab 9: Dashboard Dockerfile

Create a file named `dashboard.py`:

```python
print("Robot dashboard starting...")
```

Update the Dockerfile:

```Dockerfile
FROM python:3.12
WORKDIR /app
COPY . .
CMD ["python", "dashboard.py"]
```

Build and run:

```bash
docker build -t robot-dashboard .
docker run robot-dashboard
```
