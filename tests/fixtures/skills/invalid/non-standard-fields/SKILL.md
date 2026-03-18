---
name: non-standard-fields
description: Use when you need to test a skill with non-spec frontmatter fields.
argument-hint: "[topic]"
context: fork
disable-model-invocation: true
---

This skill uses frontmatter fields that are not in the Agent Skills spec.
Custom data should live inside the `metadata:` map, not at the top level.

Expected failure: structure.standard-frontmatter-fields [moderate]
