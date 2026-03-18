---
name: no-examples
description: Use when you need to test a skill that has no code examples in its body.
---

This skill explains how to do something but never shows a concrete example.

Skills should include at least one code block or example so the agent
understands the expected input/output format and can execute the task correctly.
Without examples, agents often hallucinate the wrong syntax.

There is plenty of text here to pass the minimum body length check, but no
fenced code blocks, no indented code, and no example tags anywhere.

Expected failure: content.has-examples [minor]
