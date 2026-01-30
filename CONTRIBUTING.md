# Contributing to Skill-Lab

Thank you for your interest in contributing to sklab! This document provides guidelines and instructions for contributing.

## Development Setup

### Prerequisites
- Python 3.10 or higher
- Git

### Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/8ddieHu0314/Skill-Lab.git
   cd Skill-Lab
   ```

2. **Create a virtual environment**
   ```bash
   python -m venv venv

   # Windows
   venv\Scripts\activate

   # macOS/Linux
   source venv/bin/activate
   ```

3. **Install in editable mode with dev dependencies**
   ```bash
   pip install -e ".[dev]"
   ```

4. **Verify installation**
   ```bash
   sklab --help
   pytest tests/ -v
   ```

## Development Workflow

### Running Tests
```bash
# Run all tests
pytest tests/ -v

# Run with coverage
pytest tests/ --cov=skill_lab --cov-report=html

# Run specific test file
pytest tests/test_checks.py -v
```

### Code Quality

Before submitting a PR, ensure your code passes all checks:

```bash
# Type checking
mypy src/

# Linting
ruff check src/

# Format check
ruff format --check src/

# Auto-format
ruff format src/
```

### Adding a New Check

1. Create your check in `src/skill_lab/checks/static/`
2. Use the `@register_check` decorator
3. Inherit from `StaticCheck` base class
4. Add tests in `tests/test_checks.py`
5. Update `docs/CHECKS.md` with the new check

Example:
```python
from skill_lab.checks.base import StaticCheck
from skill_lab.core.registry import register_check

@register_check
class MyNewCheck(StaticCheck):
    check_id = "category.my-check"
    check_name = "My Check"
    description = "Description of what this check does"
    severity = Severity.WARNING
    dimension = EvalDimension.CONTENT

    def run(self, skill: Skill) -> CheckResult:
        # Implementation
        pass
```

## Pull Request Process

1. **Create a branch**
   ```bash
   git checkout -b feature/my-feature
   ```

2. **Make your changes**
   - Follow the existing code style
   - Add tests for new functionality
   - Update documentation as needed

3. **Run checks locally**
   ```bash
   pytest tests/ -v
   mypy src/
   ruff check src/
   ```

4. **Commit your changes**
   ```bash
   git add .
   git commit -m "Add feature: description"
   ```

5. **Push and create PR**
   ```bash
   git push origin feature/my-feature
   ```
   Then create a Pull Request on GitHub.

## Code Style

- Use type hints for all function parameters and return values
- Follow PEP 8 naming conventions
- Keep functions focused and small
- Add docstrings for public functions and classes
- Maximum line length: 100 characters

## Reporting Issues

- Use the issue templates provided
- Include reproduction steps
- Include your environment details (OS, Python version, sklab version)

## Questions?

Feel free to open an issue for questions or discussions.
