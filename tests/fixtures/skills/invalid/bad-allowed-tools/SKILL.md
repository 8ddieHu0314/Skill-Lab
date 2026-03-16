---
name: bad-allowed-tools
description: Use when you need to test a skill with allowed-tools as a YAML list.
allowed-tools:
  - Read
  - Write
  - Bash
---

The `allowed-tools` field must be a space-delimited string, not a YAML list.

Correct format:  `allowed-tools: "Read Write Bash"`
Wrong format:    the YAML list above

Expected failure: frontmatter.allowed-tools-format [moderate]
