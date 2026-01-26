---
name: generating-documentation
description: Generates comprehensive documentation for code projects when users request docs, README files, or API documentation.
---

# Generating Documentation Skill

This skill helps create and maintain documentation for software projects.

## When to Use

This skill activates when users:
- Request documentation generation
- Ask for README creation
- Need API docs
- Want inline code comments

## Capabilities

- Markdown documentation
- API reference generation
- README templates
- Inline code documentation

## Examples

### Generate a README

```python
def generate_readme(project_name, description):
    """Generate a basic README structure."""
    return f"""# {project_name}

{description}

## Installation

```bash
pip install {project_name}
```

## Usage

```python
import {project_name}
# Your code here
```

## License

MIT
"""
```

### Generate API Documentation

```python
def document_function(func):
    """Extract documentation from a function."""
    return {
        "name": func.__name__,
        "docstring": func.__doc__,
        "signature": str(inspect.signature(func)),
    }
```

## Best Practices

- Keep documentation up to date with code changes
- Include examples for all public APIs
- Use consistent formatting
- Link related documentation sections
