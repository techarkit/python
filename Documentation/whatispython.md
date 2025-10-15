# Python features, Identifiers, and Variable Rules
## What is a Python?
- Python is a programming language
- *Guido Van Rossum* developed it in 1989
- Public - 1991
- Current version: 3.14 

## Features of Python
- **Simple and easy to learn**  – Python syntax is clean and readable, making it beginner-friendly.
- **Freeware & Open Source**  – Python is freely available for use and modification.
- **High-level programming language**  – It abstracts complex details from hardware.
- **Platform independent**  – Python runs on Windows, Linux, and macOS without modification.
- **Portable**  – Code written in one OS can be executed on another without changes.
- **Dynamically typed programming**  – No need to declare variable types explicitly.
- **Supports both procedure-oriented and object-oriented programming.** 
- **Interpreted**  – Code is executed line by line, simplifying debugging.
- **Extensible**  – Can integrate with other languages like C/C++.
- **Embeddable**  – Python code can be embedded within C/C++ programs.
- **Extensive libraries** – Provides a wide range of built-in and third-party modules.

## Limitations of Python
- Not suitable for mobile application development.
- Performance is slower compared to compiled languages, as Python is interpreted.

## Identifiers
- A name in the Python program is called an identifier
- It can be a class name, a function name, a module name, or a variable name
```
Example:
		a = 10
		def f()
		class Test:
```
Rules to define identifiers in Python
- Identifiers can include letters (a-z, A-Z), digits (0-9), and underscore (_) only.
- Underscore symbol(_). Identifiers cannot include symbols like $, @, or #.
```
Example:
	cash = 100(valid)
	cas$sh = 100(invalid)
```
- Identifiers should not start with a digit
```
Example:
	123total = 100(invalid)
	Total123 = 100(valid)
```
- They are case-sensitive (e.g., ‘Name’ and ‘name’ are different).
- There is no fixed length limit, but overly long identifiers are discouraged.
- Identifiers starting with a single underscore (_) are treated as protected.
- Identifiers starting with double underscores (__) are private.
![Identifiers](Images/private_public_protected_var.png)

- Identifiers starting and ending with double underscores are known as magic methods
  ```
  e.g., Magic Methods
  __init__
  __add__
  __mul__
  __sub__
  ```
  ## Reserved words
- Reserved words are predefined in Python and cannot be used as identifiers

```
import keyword
keyword.kwlist
['False', 'None', 'True', 'and', 'as', 'assert', 'async', 'await', 'break', 'class', 'continue', 'def', 'del', 'elif', 'else', 'except', 'finally', 'for', 'from', 'global', 'if', 'import', 'in', 'is', 'lambda', 'nonlocal', 'not', 'or', 'pass', 'raise', 'return', 'try', 'while', 'with', 'yield']
```
- Except 3-Keywords all contains lower case alphabets 
```
True, False, and None
```
