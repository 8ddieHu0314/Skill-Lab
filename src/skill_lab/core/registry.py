"""Check registration system for managing available checks."""

from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from skill_lab.checks.base import StaticCheck


class CheckRegistry:
    """Registry for managing and discovering available checks."""

    def __init__(self) -> None:
        self._checks: dict[str, type["StaticCheck"]] = {}

    def register(
        self, check_class: type["StaticCheck"]
    ) -> type["StaticCheck"]:
        """Register a check class.

        Args:
            check_class: The check class to register.

        Returns:
            The check class (for use as decorator).
        """
        check_id = check_class.check_id
        if check_id in self._checks:
            raise ValueError(f"Check with ID '{check_id}' is already registered")
        self._checks[check_id] = check_class
        return check_class

    def get(self, check_id: str) -> type["StaticCheck"] | None:
        """Get a check class by ID.

        Args:
            check_id: The check ID to look up.

        Returns:
            The check class or None if not found.
        """
        return self._checks.get(check_id)

    def get_all(self) -> list[type["StaticCheck"]]:
        """Get all registered check classes.

        Returns:
            List of all registered check classes.
        """
        return list(self._checks.values())

    def get_by_dimension(self, dimension: str) -> list[type["StaticCheck"]]:
        """Get all checks for a specific dimension.

        Args:
            dimension: The dimension to filter by.

        Returns:
            List of check classes for the dimension.
        """
        return [c for c in self._checks.values() if c.dimension.value == dimension]

    def list_ids(self) -> list[str]:
        """Get all registered check IDs.

        Returns:
            List of check IDs.
        """
        return list(self._checks.keys())

    def clear(self) -> None:
        """Clear all registered checks. Useful for testing."""
        self._checks.clear()


# Global registry instance
registry = CheckRegistry()


def register_check(check_class: type["StaticCheck"]) -> type["StaticCheck"]:
    """Decorator to register a check class with the global registry.

    Args:
        check_class: The check class to register.

    Returns:
        The check class.
    """
    return registry.register(check_class)
