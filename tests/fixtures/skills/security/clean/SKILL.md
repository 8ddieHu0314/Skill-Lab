---
name: clean
description: Use when you need to convert a CSV file to JSON format.
---

# CSV to JSON Converter

Read the input CSV file and convert it to a JSON array of objects.

```python
import csv, json, sys

with open(sys.argv[1]) as f:
    rows = list(csv.DictReader(f))

print(json.dumps(rows, indent=2))
```

Pass the path to your CSV as the first argument. Each row becomes a JSON object
with the header row as keys. Output goes to stdout so you can pipe or redirect it.
