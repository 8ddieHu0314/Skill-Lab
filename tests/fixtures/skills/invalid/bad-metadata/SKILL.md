---
name: bad-metadata
description: Use when you need to test a skill with non-string values in the metadata map.
metadata:
  author: janedoe
  version: 2
  reviewed: true
---

The `metadata:` map must be string-to-string only. This skill has `version: 2`
(integer) and `reviewed: true` (boolean), both of which violate that rule.

Expected failure: frontmatter.metadata-format [high]
