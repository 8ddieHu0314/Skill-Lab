---
name: interactive-scripts
description: Use when you need to test a skill whose scripts use interactive input.
---

This skill's scripts call `input()` and `getpass`, which block because agents
run scripts in non-interactive shells — there is no terminal to read from.

See `scripts/setup.py` for the violations.

Expected failures:
- structure.scripts-no-interactive [moderate]
