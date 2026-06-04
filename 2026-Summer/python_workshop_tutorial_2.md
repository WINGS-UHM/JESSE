# Wheel Logger Follow-Up Tutorial

## Why This Tutorial Exists

The first Python tutorial covered beginner basics: variables, lists, loops, `if` statements, and functions.

The wheel logger introduces a few new ideas that are common in real programs. This tutorial explains those new ideas in simple language before students edit the code.

You are not expected to memorize every detail. Focus on what each part does and why it exists.

---

## New Concepts In This File

The wheel logger introduces:

- importing modules
- using an outside library called `pygame`
- constants written in capital letters
- docstrings
- ANSI terminal color codes
- helper functions
- polling input in a loop
- logging only when values change
- ignoring tiny controller changes
- `try`, `except`, and `finally`
- cleanup with `pygame.quit()`
- the `if __name__ == "__main__"` pattern

---

## 1. Imports And Modules

A module is a file or library that gives Python extra tools.

The wheel logger starts with:

```python
import time
import pygame
```

`time` is a built-in Python module. The code uses it to wait between readings:

```python
time.sleep(POLL_SECONDS)
```

`pygame` is an outside library. The code uses it to talk to the steering wheel:

```python
pygame.joystick.init()
```

Think of `import` as saying:

> I want to use tools from this other module.

---

## 2. Constants

The logger has settings near the top:

```python
POLL_SECONDS = 0.05
AXIS_PRECISION = 3
AXIS_CHANGE_LOG_THRESHOLD = 0.02
```

These are normal variables, but they are written in capital letters because they are meant to act like constants.

A constant is a value the program depends on but does not usually change while running.

Examples:

| Constant                    | Meaning                                      |
| --------------------------- | -------------------------------------------- |
| `POLL_SECONDS`              | how long to wait between checks              |
| `AXIS_PRECISION`            | how many decimal places to keep              |
| `AXIS_CHANGE_LOG_THRESHOLD` | how much an axis must change before printing |

This makes the program easier to adjust. Instead of hunting through the whole file, you change the setting once near the top.

---

## 3. Docstrings

A docstring is a description inside triple quotes.

Example:

```python
def read_state(joystick):
    """
    Read the current controller values.
    """
```

A comment starts with `#`. A docstring uses triple quotes and usually describes a function, file, or class.

Use docstrings to answer:

- What does this function do?
- What does it return?
- Why does it exist?

---

## 4. ANSI Terminal Colors

The logger uses color codes like this:

```python
RED = "\033[31m"
GREEN = "\033[32m"
RESET = "\033[0m"
```

These are ANSI escape codes. They are special text codes that many terminals understand.

For example:

```python
print(GREEN + "hello" + RESET)
```

The terminal sees:

1. Start green text.
2. Print `hello`.
3. Reset back to normal.

The helper function makes this easier:

```python
def paint(text, color):
    return color + text + RESET
```

Then the code can write:

```python
print(paint("AXES", BLUE))
```

Important: the color code itself is not visible text. It is an instruction to the terminal.

---

## 5. Helper Functions

A helper function does one small job so the main program is easier to read.

Examples from the logger:

```python
def label(text, color):
    label_text = text + ":"
    return paint(f"{label_text:<10}", color)
```

```python
def format_axes(axes):
    ...
```

Instead of writing formatting code again and again, the program gives that work a name.

Good helper functions usually:

- have a clear name
- do one job
- return a useful result or print one clear message

---

## 6. The Axes List

The wheel gives Python a list of numbers.

For this activity, the list is expected to mean:

```python
[S, A, B, C]
```

Meaning:

| Name | Meaning                |
| ---- | ---------------------- |
| `S`  | steering               |
| `A`  | accelerate pedal       |
| `B`  | brake or reverse pedal |
| `C`  | extra pedal or control |

Python list positions start at `0`:

```python
axes[0]  # S
axes[1]  # A
axes[2]  # B
axes[3]  # C
```

This is why list indexes matter in robotics code. A wrong index can make the robot respond to the wrong control.

---

## 7. Polling

Polling means checking something again and again.

The logger uses a loop:

```python
while True:
    pygame.event.pump()
    axes, buttons, hats = read_state(joystick)
    time.sleep(POLL_SECONDS)
```

This loop keeps asking:

> What are the controller values right now?

The `time.sleep(...)` call slows the loop down so the computer is not checking too aggressively.

---

## 8. Change-Only Logging

If the program printed every poll, the terminal would fill up very quickly.

Instead, the basic logger only prints when something changes:

```python
if axes_changed_enough(axes, last_axes):
    print(label("AXES", BLUE), format_axes(axes))
    last_axes = axes
```

`last_axes` stores the previous reading. The new `axes` list is compared to the old one.

This is a common programming pattern:

1. Store the previous value.
2. Read the current value.
3. Compare them.
4. Print or act only when the value changed.

---

## 9. Ignoring Tiny Changes

Controllers can report tiny changes even when nobody is touching them.

Example:

```text
0.000
0.006
-0.004
0.003
```

Those tiny changes are noise. The logger ignores small changes with this setting:

```python
AXIS_CHANGE_LOG_THRESHOLD = 0.02
```

The helper function checks whether the change is big enough:

```python
change = abs(current_axes[index] - last_axes[index])

if change > AXIS_CHANGE_LOG_THRESHOLD:
    return True
```

`abs()` gives the distance from zero. For example:

```python
abs(-0.25)  # 0.25
```

---

## 10. `try`, `except`, And `finally`

The logger runs forever until the user presses `Ctrl+C`.

Pressing `Ctrl+C` causes a `KeyboardInterrupt`. The program handles it with:

```python
try:
    while True:
        ...
except KeyboardInterrupt:
    print("Stopped.")
finally:
    pygame.quit()
```

What each part means:

| Part                       | Meaning                               |
| -------------------------- | ------------------------------------- |
| `try`                      | run this code                         |
| `except KeyboardInterrupt` | if the user presses `Ctrl+C`, do this |
| `finally`                  | always do this at the end             |

The `finally` block is important because it runs even when the program is interrupted.

---

## 11. Cleanup With `pygame.quit()`

The logger starts pygame:

```python
pygame.init()
pygame.joystick.init()
```

At the end, it should clean up:

```python
pygame.quit()
```

Cleanup means:

> Release resources the program was using.

For hardware and libraries, cleanup is a good habit. It helps the program exit cleanly.

---

## 12. `if __name__ == "__main__"`

In the finished `logiwheel.py`, the program ends with:

```python
if __name__ == "__main__":
    raise SystemExit(main())
```

This is a common Python pattern.

Simple meaning:

> Only run `main()` when this file is started directly.

Why this matters:

- If you run `python logiwheel.py`, `main()` runs.
- If another file imports `logiwheel.py`, `main()` does not automatically run.

This makes code easier to reuse later.

The student file currently uses the simpler beginner style:

```python
main()
```

That is easier to read first. The `if __name__ == "__main__"` version is the more professional pattern.

---

## 13. `raise SystemExit(main())`

This line:

```python
raise SystemExit(main())
```

runs `main()` and uses its return value as the program exit code.

For example:

```python
return 0
```

usually means the program finished successfully.

```python
return 1
```

usually means something went wrong, such as no joystick being detected.

For beginners, it is okay to remember:

> `raise SystemExit(main())` is a clean way to end a full Python program.

---

## 14. Basic Logger Vs Advanced Logger

The file is organized like two programs:

| Version         | What It Does                          |
| --------------- | ------------------------------------- |
| Basic logger    | prints only axes and button changes   |
| Advanced logger | adds held input and robot status text |

The basic logger is active first because it is easier to understand.

The advanced logger is commented out because it introduces more logic:

- held input logging
- pedal detection
- steering direction
- status strings
- color-coded statuses

---

## 15. Advanced Status Logic

The advanced version builds one string like:

```text
idle
accelerating
reversing
accelerating left
reversing right
```

It uses a list, then joins the words:

```python
status_parts = []
status_parts.append("accelerating")
status_parts.append("right")

return " ".join(status_parts)
```

This is useful because one robot command can have more than one idea:

```text
accelerating right
```

means:

- move forward
- turn right

---

## Student Exercises

### Exercise 1: Explain An Import

In your own words, explain what this line does:

```python
import pygame
```

### Exercise 2: Change A Constant

Find:

```python
AXIS_CHANGE_LOG_THRESHOLD = 0.02
```

Try changing it to:

```python
AXIS_CHANGE_LOG_THRESHOLD = 0.05
```

What changes when you move the wheel slightly?

### Exercise 3: Read A Function

Explain what this function returns:

```python
def axes_changed_enough(current_axes, last_axes):
    ...
```

### Exercise 4: Try / Except / Finally

Find the `try`, `except`, and `finally` section.

Answer:

- Which part runs during the normal loop?
- Which part runs when `Ctrl+C` is pressed?
- Which part always runs at the end?

### Exercise 5: Main Guard

In `logiwheel.py`, find:

```python
if __name__ == "__main__":
    raise SystemExit(main())
```

Explain why this is different from simply writing:

```python
main()
```

---

## Advanced Challenge

After the basic logger makes sense, uncomment the advanced logger section.

Then complete the TODO-style logic so the program can print:

```text
STATUS: accelerating right
STATUS: reversing left
STATUS: idle
```

Later, that status string can become a robot command:

| Status Contains | Robot Command  |
| --------------- | -------------- |
| `idle`          | stop           |
| `accelerating`  | drive forward  |
| `reversing`     | drive backward |
| `left`          | turn left      |
| `right`         | turn right     |

This is the bridge between reading a controller and controlling a robot car.
