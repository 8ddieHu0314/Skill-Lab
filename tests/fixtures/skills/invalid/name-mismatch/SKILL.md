---
name: completely-different-name
description: Use when you need to test a skill whose name does not match its directory.
---

The `name:` field says `completely-different-name` but this directory is called
`name-mismatch`. The spec requires them to be identical.

Expected failure: naming.matches-directory [high]
