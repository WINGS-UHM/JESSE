# Python Basics Workshop 3

## Why This Tutorial Exists

The first two Python tutorials covered core syntax, data types, collections,
conditionals, loops, functions, imports, constants, docstrings, polling,
exceptions, cleanup, and the `main()` pattern.

This tutorial adds concepts that show up in xApp and robot-control code:

- `None`
- default function values
- keyword arguments
- nested dictionaries
- safe dictionary access with `.get()`
- JSON
- reading files
- type hints
- returning status and payload together
- callbacks
- classes and objects
- small debugging habits

---

# 1. `None`

## What is it?

`None` means "no value here." It is different from `0`, `False`, or an empty
string.

Programs use `None` when a value is optional or has not been set yet.

## Example

```python
last_command = None

if last_command is None:
    print("No command has arrived yet.")
```

## Try It Yourself

> **Exercise 1:** Create a variable named `robot_status` and set it to `None`.
> Print `"Waiting"` if it is still `None`.

## Solution

```python
robot_status = None

if robot_status is None:
    print("Waiting")
```

---

# 2. Default Function Values

## What is it?

A function parameter can have a default value. If the caller does not provide
that argument, Python uses the default.

## Example

```python
def make_message(text, label="INFO"):
    return f"{label}: {text}"

print(make_message("Server started"))
print(make_message("Bad request", "ERROR"))
```

Output:

```text
INFO: Server started
ERROR: Bad request
```

## Try It Yourself

> **Exercise 2:** Write a function named `drive_command` with a default speed of
> `0.0`.

## Solution

```python
def drive_command(speed=0.0):
    return f"speed={speed}"

print(drive_command())
print(drive_command(0.5))
```

---

# 3. Keyword Arguments

## What is it?

Keyword arguments name the value being passed into a function. This makes
function calls easier to read when there are several settings.

## Example

```python
def connect(host, port):
    print(f"Connecting to {host}:{port}")

connect(host="127.0.0.1", port=8080)
```

## Try It Yourself

> **Exercise 3:** Call this function using keyword arguments:

```python
def report_status(name, ready):
    print(f"{name} ready: {ready}")
```

## Solution

```python
report_status(name="steering-xapp", ready=True)
```

---

# 4. Nested Dictionaries

## What is it?

A dictionary can contain another dictionary. This is called nesting. Nested
dictionaries are common in configuration files and JSON data.

## Example

```python
config = {
    "name": "steering-wheel-command-xapp",
    "controls": {
        "restHost": "0.0.0.0",
        "restPort": 8080
    }
}

controls = config["controls"]
print(controls["restPort"])
```

## Try It Yourself

> **Exercise 4:** Create a dictionary named `robot` with a nested dictionary
> named `limits`. Put `max_speed` inside `limits` and print it.

## Solution

```python
robot = {
    "name": "test robot",
    "limits": {
        "max_speed": 0.6
    }
}

print(robot["limits"]["max_speed"])
```

---

# 5. Safe Dictionary Access With `.get()`

## What is it?

Using square brackets requires the key to exist:

```python
config["controls"]
```

If the key is missing, Python raises an error.

`.get()` is safer when a value is optional:

```python
controls = config.get("controls", {})
```

The second value is the default. If `"controls"` is missing, Python returns
`{}` instead.

## Example

```python
controls = {
    "restPort": 8080
}

host = controls.get("restHost", "0.0.0.0")
port = controls.get("restPort", 8080)

print(host)
print(port)
```

## Try It Yourself

> **Exercise 5:** Use `.get()` to read `"color"` from a dictionary. Use
> `"blue"` as the default.

## Solution

```python
settings = {}

color = settings.get("color", "blue")
print(color)
```

---

# 6. JSON

## What is it?

JSON is a text format for structured data. It looks a lot like Python
dictionaries and lists.

Python uses the `json` module to convert between JSON text and Python data.

## Example

```python
import json

text = '{"seq": 1, "steering": 0.25, "enable": true}'
command = json.loads(text)

print(command["seq"])
print(command["steering"])
print(command["enable"])
```

Important difference:

| JSON | Python |
|---|---|
| `true` | `True` |
| `false` | `False` |
| `null` | `None` |

## Try It Yourself

> **Exercise 6:** Convert this JSON text into Python data and print the
> `"throttle"` value.

```python
text = '{"throttle": 0.4, "brake": 0.0}'
```

## Solution

```python
import json

text = '{"throttle": 0.4, "brake": 0.0}'
data = json.loads(text)

print(data["throttle"])
```

---

# 7. Turning Python Data Into JSON Text

## What is it?

`json.loads(...)` reads JSON text.

`json.dumps(...)` creates JSON text from Python data.

## Example

```python
import json

payload = {
    "alive": True,
    "name": "steering-wheel-command-xapp"
}

text = json.dumps(payload)
print(text)
```

Output:

```json
{"alive": true, "name": "steering-wheel-command-xapp"}
```

## Try It Yourself

> **Exercise 7:** Create a dictionary with `"ready": True`, then convert it to
> JSON text.

## Solution

```python
import json

payload = {
    "ready": True
}

print(json.dumps(payload))
```

---

# 8. Reading A File

## What is it?

Programs often read settings from files. Python's `open()` function opens a
file, and `with` makes sure the file is closed afterward.

## Example

```python
with open("config.json", "r", encoding="utf-8") as config_file:
    text = config_file.read()

print(text)
```

The `"r"` means read mode.

## Try It Yourself

> **Exercise 8:** Read a file named `message.txt` and print its contents.

## Solution

```python
with open("message.txt", "r", encoding="utf-8") as message_file:
    message = message_file.read()

print(message)
```

---

# 9. Type Hints

## What is it?

Type hints describe what kind of values a function expects and returns. Python
can run without type hints, but hints make code easier to understand.

## Example

```python
def add_scores(first: int, second: int) -> int:
    return first + second
```

Meaning:

- `first` should be an integer
- `second` should be an integer
- the function returns an integer

## Common Type Hints

| Hint | Meaning |
|---|---|
| `str` | text |
| `int` | whole number |
| `float` | decimal number |
| `bool` | true or false |
| `dict` | dictionary |
| `list` | list |

## Try It Yourself

> **Exercise 9:** Add type hints to a function that takes a name and returns a
> greeting.

## Solution

```python
def greet(name: str) -> str:
    return f"Hello, {name}"
```

---

# 10. Returning Two Values Together

## What is it?

A function can return two values together by returning a tuple.

This is useful for REST-style code where a function may return:

- a status code
- a payload dictionary

## Example

```python
def check_ready():
    ready = True
    payload = {"ready": ready}
    return 200, payload

status, body = check_ready()

print(status)
print(body)
```

## Try It Yourself

> **Exercise 10:** Write a function named `reject_command` that returns status
> `400` and payload `{"error": "bad command"}`.

## Solution

```python
def reject_command():
    return 400, {"error": "bad command"}

status, payload = reject_command()

print(status)
print(payload)
```

---

# 11. HTTP Request And Response Shape

## What is it?

HTTP is a common way for programs to talk over a network.

A request asks for something. A response answers.

Common request methods:

| Method | Common Use |
|---|---|
| `GET` | read information |
| `POST` | send information or ask for an action |

## Example: GET

```text
GET /ric/v1/health/alive
```

Possible response body:

```json
{
  "alive": true,
  "name": "steering-wheel-command-xapp"
}
```

## Example: POST

```text
POST /ric/v1/steering/command
```

Possible request body:

```json
{
  "seq": 1,
  "timestamp_ms": 1717800000000,
  "steering": 0.1,
  "throttle": 0.2,
  "brake": 0.0,
  "enable": true
}
```

Possible response body:

```json
{
  "accepted": true
}
```

## Try It Yourself

> **Exercise 11:** Decide whether each route should probably be GET or POST:
>
> - read current steering state
> - send a stop command
> - check whether the app is alive

## Solution

```text
read current steering state -> GET
send a stop command -> POST
check whether the app is alive -> GET
```

---

# 12. Callback Functions

## What is it?

A callback is a function that is handed to another part of the program so it can
be called later.

REST servers use this idea. You register a handler function for a route. Later,
when a request arrives, the server calls that handler.

## Example

```python
def say_alive():
    return {"alive": True}

route_handler = say_alive

print(route_handler())
```

The variable `route_handler` stores the function itself. The parentheses call
the function later.

## Try It Yourself

> **Exercise 12:** Store a function in a variable, then call it through that
> variable.

## Solution

```python
def make_status():
    return {"ready": True}

handler = make_status

print(handler())
```

---

# 13. Nested Handler Functions

## What is it?

Sometimes a function creates and returns another function.

This pattern is useful when the inner function needs access to a value from the
outer function.

## Example

```python
def make_alive_handler(app_name):
    def handler():
        return {
            "alive": True,
            "name": app_name
        }

    return handler

alive_handler = make_alive_handler("steering-wheel-command-xapp")
print(alive_handler())
```

The inner `handler()` remembers `app_name` from the outer function.

## Try It Yourself

> **Exercise 13:** Write an outer function that accepts a color and returns an
> inner function that reports that color.

## Solution

```python
def make_color_handler(color):
    def handler():
        return {"color": color}

    return handler

handler = make_color_handler("green")
print(handler())
```

---

# 14. Classes And Objects

## What is it?

A class is a blueprint. An object is something created from that blueprint.

Classes are useful when data and functions belong together.

## Example

```python
class Counter:
    def __init__(self):
        self.count = 0

    def add_one(self):
        self.count = self.count + 1

counter = Counter()
counter.add_one()
counter.add_one()

print(counter.count)
```

Important parts:

| Part | Meaning |
|---|---|
| `class Counter:` | creates the blueprint |
| `__init__` | runs when the object is created |
| `self.count` | data stored on this object |
| `counter.add_one()` | calls a method on the object |

## Try It Yourself

> **Exercise 14:** Create a `RobotState` class with a `stopped` value that starts
> as `True`.

## Solution

```python
class RobotState:
    def __init__(self):
        self.stopped = True

state = RobotState()
print(state.stopped)
```

---

# 15. Reading Error Messages

## What is it?

An error message tells you what Python could not do. The last line is often the
most useful starting point.

## Example

```python
command = {"steering": 0.1}
print(command["throttle"])
```

Possible error:

```text
KeyError: 'throttle'
```

Meaning:

> Python looked for the key `"throttle"`, but that key was not in the
> dictionary.

One possible fix:

```python
throttle = command.get("throttle", 0.0)
print(throttle)
```

## Try It Yourself

> **Exercise 15:** What key is missing in this code?

```python
settings = {"restPort": 8080}
print(settings["restHost"])
```

## Solution

```text
restHost
```

---

# Practice Round

## Mini Challenge 1

Create a command dictionary, convert it to JSON text, then convert it back to
Python data.

### Solution

```python
import json

command = {
    "seq": 1,
    "steering": 0.25,
    "throttle": 0.4,
    "brake": 0.0,
    "enable": True
}

text = json.dumps(command)
parsed = json.loads(text)

print(text)
print(parsed["steering"])
```

## Mini Challenge 2

Write a function that reads `restHost` and `restPort` from a nested config
dictionary. Use default values if they are missing.

### Solution

```python
def read_rest_settings(config):
    controls = config.get("controls", {})
    host = controls.get("restHost", "0.0.0.0")
    port = controls.get("restPort", 8080)
    return host, port

config = {
    "controls": {
        "restPort": 9090
    }
}

host, port = read_rest_settings(config)

print(host)
print(port)
```

## Mini Challenge 3

Create a nested handler function for a fake health route.

### Solution

```python
def rest_health_alive(app_name):
    def handler():
        return {
            "alive": True,
            "name": app_name
        }

    return handler

handler = rest_health_alive("demo-xapp")
print(handler())
```

---

# Quick Review

| Concept | Remember |
|---|---|
| `None` | means no value |
| default value | used when an argument is not provided |
| keyword argument | names the value being passed |
| nested dictionary | dictionary inside another dictionary |
| `.get()` | safely reads a dictionary value with a default |
| JSON | text format for structured data |
| `json.loads()` | JSON text to Python data |
| `json.dumps()` | Python data to JSON text |
| type hints | notes about expected value types |
| callback | function saved and called later |
| class | blueprint for objects |
| object | created from a class |
