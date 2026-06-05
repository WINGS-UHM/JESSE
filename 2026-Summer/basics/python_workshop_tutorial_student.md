# Python Basics Workshop

## A 90-120 Minute Beginner Tutorial for High School Students

Welcome to your first Python workshop. By the end, you will be able to read and write small Python programs, use variables, make decisions, repeat actions, and store groups of information.

> **Tip:** You do not need to memorize everything. Programmers look things up all the time. Focus on trying code, reading errors calmly, and making small changes.

---

## Workshop Plan

| Section                        |   Time |
| ------------------------------ | -----: |
| Intro + Setup                  | 10 min |
| Variables, Data Types, Strings | 25 min |
| Collections                    | 20 min |
| Conditionals                   | 10 min |
| Loops                          | 15 min |
| Functions                      | 10 min |
| Practice + Quiz                | 20 min |

---

# 1. Python Introduction

## What is it?

Python is a programming language. A programming language lets you give instructions to a computer. Python is popular because it is readable, beginner-friendly, and used for websites, games, apps, data, robots, and AI.

## Example

```python
print("Hello, Python!")
```

## Try It Yourself

> **Exercise 1:** Print your own welcome message.

---

# 2. Getting Started

## What is it?

To write Python, you need a place to type and run code. A Python file usually ends with `.py`, like `hello.py`.

## Example

Create a file named `hello.py` and add:

```python
print("This file is running!")
```

## Try It Yourself

> **Exercise 2:** Create a file named `about_me.py`. Print your name and one thing you like.

> **Tip:** If your name or hobby is different, use your own words.

---

# 3. Python Syntax

## What is it?

Syntax means the rules for writing code so Python understands it. Python cares about spelling, parentheses, quotation marks, and spacing. If the rules are broken, Python shows an error message.

## Example

```python
print("Python syntax matters!")
```

## Try It Yourself

> **Exercise 3:** Fix this broken code:

```python
print("I can fix syntax errors!"
```

---

# 4. Output With `print`

## What is it?

Output is information your program shows to the user. In Python, `print()` displays text, numbers, or other values. It is one of the first tools beginners use to check what their code is doing.

## Example

```python
print("Score:")
print(95)
```

## Try It Yourself

> **Exercise 4:** Print three lines: your favorite food, favorite song, and favorite class.

---

# 5. Comments

## What is it?

Comments are notes inside your code. Python ignores comments when the program runs. Use comments to explain important ideas or leave reminders for yourself.

## Example

```python
# This prints a message to the screen
print("Comments help humans read code.")
```

## Try It Yourself

> **Exercise 5:** Write one comment, then print one sentence.

---

# 6. Variables

## What is it?

A variable is a name that stores a value. Think of it like a labeled box. You can put information in the box and use it later.

## Example

```python
name = "Jordan"
age = 16

print(name)
print(age)
```

## Try It Yourself

> **Exercise 6:** Create variables for your name, age, and favorite color. Print all three.

> **Tip:** Variable names should be clear. `favorite_color` is easier to understand than `fc`.

---

# 7. Data Types

## What is it?

A data type tells Python what kind of value something is. Text, numbers, and true-or-false values are different types. Python uses the type to decide what actions make sense.

Common data types:

| Type    | Meaning        | Example   |
| ------- | -------------- | --------- |
| `str`   | Text           | `"hello"` |
| `int`   | Whole number   | `12`      |
| `float` | Decimal number | `12.5`    |
| `bool`  | True or false  | `True`    |

## Example

```python
name = "Sam"
score = 88
height = 5.7
is_student = True

print(type(name))
print(type(score))
print(type(height))
print(type(is_student))
```

## Try It Yourself

> **Exercise 7:** Create one variable for each type: string, integer, float, and Boolean.

---

# 8. Numbers

## What is it?

Python can work with numbers like a calculator. Whole numbers are called integers. Decimal numbers are called floats.

## Example

```python
points = 10
bonus = 2.5
total = points + bonus

print(total)
```

## Try It Yourself

> **Exercise 8:** Store two test scores in variables. Print their total.

---

# 9. Type Casting

## What is it?

Type casting changes a value from one type to another. This is useful when user input starts as text but you need a number. Common casting tools are `int()`, `float()`, and `str()`.

## Example

```python
age_text = "16"
age_number = int(age_text)

print(age_number + 1)
```

## Try It Yourself

> **Exercise 9:** Convert the string `"45"` into a number and add `5`.

---

# 10. Strings

## What is it?

A string is text. Strings go inside quotes. You can join strings, store names, create messages, and use them in formatted sentences.

## Example

```python
first_name = "Taylor"
last_name = "Lee"

full_name = first_name + " " + last_name
print(full_name)
```

## Formatted Strings

Formatted strings, also called f-strings, make it easy to place variables inside text.

```python
name = "Taylor"
score = 92

print(f"{name} scored {score} points.")
```

## Try It Yourself

> **Exercise 10:** Create a name and hobby variable. Print a sentence using both.

---

# 11. Booleans

## What is it?

A Boolean is either `True` or `False`. Booleans are useful for yes-or-no questions. Programs use them to make decisions.

## Example

```python
has_homework = True
is_weekend = False

print(has_homework)
print(is_weekend)
```

## Try It Yourself

> **Exercise 11:** Create a Boolean variable named `passed` and set it to `True`.

---

# 12. Operators

## What is it?

Operators are symbols that do work. Some operators do math, some compare values, and some combine conditions. They help your program calculate and decide.

## Common Operators

| Operator | Meaning                  | Example                        |
| -------- | ------------------------ | ------------------------------ |
| `+`      | Add                      | `3 + 2`                        |
| `-`      | Subtract                 | `3 - 2`                        |
| `*`      | Multiply                 | `3 * 2`                        |
| `/`      | Divide                   | `3 / 2`                        |
| `==`     | Equal to                 | `score == 100`                 |
| `!=`     | Not equal to             | `name != "Ava"`                |
| `>`      | Greater than             | `age > 16`                     |
| `<`      | Less than                | `age < 18`                     |
| `>=`     | Greater than or equal to | `score >= 60`                  |
| `<=`     | Less than or equal to    | `score <= 100`                 |
| `and`    | Both must be true        | `age >= 13 and age <= 19`      |
| `or`     | One can be true          | `day == "Sat" or day == "Sun"` |
| `not`    | Opposite                 | `not is_absent`                |

## Example

```python
score = 85

print(score >= 60)
print(score == 100)
```

## Try It Yourself

> **Exercise 12:** Create a score variable. Print whether the score is at least 70.

---

# 13. Lists

## What is it?

A list stores multiple values in one variable. Lists are useful when the order matters or when values may change. You can add, remove, and access items.

## Example

```python
snacks = ["chips", "apple", "pretzels"]

print(snacks[0])
snacks.append("granola bar")
print(snacks)
```

> **Tip:** Python starts counting positions at `0`, so the first item is at index `0`.

## Try It Yourself

> **Exercise 13:** Make a list of three movies. Print the second movie.

---

# 14. Tuples

## What is it?

A tuple stores multiple values, like a list, but it is usually not changed after it is created. Tuples are useful for information that should stay fixed. Use parentheses to create a tuple.

## Example

```python
location = ("Honolulu", "Hawaii")

print(location[0])
print(location[1])
```

## Try It Yourself

> **Exercise 14:** Create a tuple for a birthday month and day. Print both values.

---

# 15. Sets

## What is it?

A set stores unique values. If you add the same item more than once, the set keeps only one copy. Sets are useful for tracking things without duplicates.

## Example

```python
clubs = {"art", "music", "art", "robotics"}

print(clubs)
clubs.add("drama")
print(clubs)
```

## Try It Yourself

> **Exercise 15:** Create a set of three sports. Add one more sport.

> **Tip:** Sets do not always print in the same order. That is normal.

---

# 16. Dictionaries

## What is it?

A dictionary stores pairs of keys and values. Think of it like a contact card: a label points to a piece of information. Dictionaries are great for organized data.

## Example

```python
student = {
    "name": "Kai",
    "grade": 10,
    "club": "robotics"
}

print(student["name"])
print(student["club"])
```

## Try It Yourself

> **Exercise 16:** Create a dictionary for a pet with name, animal type, and age.

---

# 17. If / Else

## What is it?

An `if` statement lets your program make a choice. If a condition is true, one block of code runs. Otherwise, another block can run.

## Example

```python
score = 72

if score >= 60:
    print("You passed!")
else:
    print("Try again.")
```

## Try It Yourself

> **Exercise 17:** Write code that checks if someone is old enough to drive at age 16.

> **Tip:** The spaces before `print()` are called indentation. In Python, indentation shows which code belongs inside the `if` or `else`.

---

# 18. Match

## What is it?

`match` is a way to compare one value against several choices. It can be cleaner than many `if` statements when you are checking exact options. This is a simple introduction, so use it for clear choices like menu commands or letter grades.

## Example

```python
day = "Saturday"

match day:
    case "Saturday":
        print("Weekend!")
    case "Sunday":
        print("Weekend!")
    case _:
        print("School day or weekday.")
```

## Try It Yourself

> **Exercise 18:** Use `match` to print a message for `"A"`, `"B"`, or anything else.

> **Tip:** `case _:` means "anything else."

---

# 19. While Loops

## What is it?

A `while` loop repeats code while a condition is true. It is useful when you do not know exactly how many times something should repeat. Be careful to update something inside the loop, or it may run forever.

## Example

```python
count = 1

while count <= 5:
    print(count)
    count = count + 1
```

## Try It Yourself

> **Exercise 19:** Use a `while` loop to print numbers from 1 to 3.

---

# 20. For Loops

## What is it?

A `for` loop repeats code for each item in a group. It is great for lists, strings, and ranges of numbers. Use it when you know what you want to loop through.

## Example

```python
names = ["Ava", "Noah", "Mia"]

for name in names:
    print(f"Hello, {name}!")
```

## Using `range()`

```python
for number in range(1, 6):
    print(number)
```

This prints numbers from 1 through 5. The ending number, 6, is not included.

## Try It Yourself

> **Exercise 20:** Make a list of three foods. Use a `for` loop to print each food.

---

# 21. Functions

## What is it?

A function is a reusable block of code. You give it a name, then call it when you want to use it. Functions help keep programs organized.

## Example

```python
def greet(name):
    print(f"Hello, {name}!")

greet("Leilani")
greet("Chris")
```

## Returning a Value

Some functions send a value back using `return`.

```python
def add_numbers(a, b):
    return a + b

total = add_numbers(4, 6)
print(total)
```

## Try It Yourself

> **Exercise 21:** Write a function named `double` that returns a number multiplied by 2.

---

# Quick Practice Round

Try these before moving to the quiz.

## Mini Challenge 1

Create a list of three friends and print a sentence greeting each friend.

## Mini Challenge 2

Ask for a user's favorite number, convert it to an integer, add 10, and print the result.

## Mini Challenge 3

Create a dictionary for a game character with a name, level, and health. Print a short character report.

---

# Quiz: 10 Multiple-Choice Questions

Write down your answers. 

## 1. What does `print()` do?

A. Stores a value  
B. Shows output on the screen  
C. Creates a loop  
D. Deletes code

## 2. Which one is a string?

A. `42`  
B. `3.14`  
C. `"hello"`  
D. `True`

## 3. Which symbol is used for comments in Python?

A. `//`  
B. `#`  
C. `<!-- -->`  
D. `**`

## 4. What is the value of `2 + 3 * 4`?

A. `20`  
B. `24`  
C. `14`  
D. `9`

## 5. Which collection uses key-value pairs?

A. List  
B. Tuple  
C. Set  
D. Dictionary

## 6. What does this condition mean?

```python
score >= 60
```

A. Score is less than 60  
B. Score is exactly 60 only  
C. Score is 60 or higher  
D. Score is not a number

## 7. Which loop is best for going through every item in a list?

A. `for` loop  
B. `if` statement  
C. comment  
D. variable

## 8. What does `int("12")` do?

A. Makes the text uppercase  
B. Converts text `"12"` into number `12`  
C. Creates a list  
D. Prints `"12"`

## 9. Which value is a Boolean?

A. `"False"`  
B. `False`  
C. `0.5`  
D. `"yes"`

## 10. What keyword creates a function?

A. `make`  
B. `function`  
C. `def`  
D. `return`

---

# One-Page Python Cheat Sheet

## Output

```python
print("Hello")
print(42)
```

## Comments

```python
# This is a comment
```

## Variables

```python
name = "Ava"
age = 16
```

## Data Types

```python
text = "hello"       # str
whole = 10          # int
decimal = 3.5       # float
is_ready = True     # bool
```

## Type Casting

```python
age = int("16")
price = float("9.99")
message = str(100)
```

## Strings

```python
name = "Kai"
print(f"Hello, {name}!")
```

## Operators

```python
total = 5 + 3
passed = score >= 60
ready = has_pencil and has_paper
```

## Lists

```python
colors = ["red", "blue", "green"]
print(colors[0])
colors.append("yellow")
```

## Tuples

```python
point = (4, 7)
print(point[0])
```

## Sets

```python
clubs = {"art", "music", "art"}
clubs.add("drama")
```

## Dictionaries

```python
student = {"name": "Mia", "grade": 10}
print(student["name"])
```

## If / Else

```python
if score >= 60:
    print("Pass")
else:
    print("Try again")
```

## Match

```python
match grade:
    case "A":
        print("Excellent")
    case _:
        print("Keep going")
```

## While Loop

```python
count = 1

while count <= 3:
    print(count)
    count = count + 1
```

## For Loop

```python
for name in ["Ava", "Noah", "Mia"]:
    print(name)
```

## Functions

```python
def add(a, b):
    return a + b

print(add(2, 3))
```

## Input

```python
name = input("Enter your name: ")
age = int(input("Enter your age: "))
```

---

# Closing

You now know the core building blocks of beginner Python: output, variables, data types, strings, Booleans, operators, collections, conditionals, loops, and functions. The best next step is to keep changing the examples. Small experiments are how programming starts to feel comfortable.
