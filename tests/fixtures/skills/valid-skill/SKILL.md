---
name: creating-reports
description: Creates detailed reports from data when the user asks for report generation or data summaries.
---

# Creating Reports Skill

This skill helps generate comprehensive reports from various data sources.

## Usage

This skill is triggered when users request:
- Report generation
- Data summaries
- Analytics exports

## Examples

```python
# Example: Generate a sales report
def generate_report(data):
    return {
        "total": sum(data),
        "average": sum(data) / len(data),
    }
```

## Best Practices

- Always validate input data before processing
- Include timestamps in reports
- Provide both summary and detailed views
