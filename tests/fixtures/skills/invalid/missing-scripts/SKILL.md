---
name: missing-scripts
description: Use when you need to test a skill that references scripts that do not exist on disk.
---

This skill body references scripts that were never created.

Run `scripts/deploy.sh` to deploy the application.
Use `scripts/validate.py` to check your configuration first.

Expected failure: content.script-paths-exist [moderate]
