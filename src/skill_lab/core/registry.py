"""Check registration system for managing available checks."""

from typing import TYPE_CHECKING

from skill_lab.core.utils import Registry

if TYPE_CHECKING:
    from skill_lab.checks.base import StaticCheck


class CheckRegistry(Registry["StaticCheck"]):
    """Registry for managing and discovering available static checks.

    Extends the generic Registry with check-specific functionality like
    filtering by dimension and spec requirements.
    """

    def __init__(self) -> None:
        """Initialize the check registry."""
        super().__init__(id_extractor=lambda cls: cls.check_id)

    def get_by_dimension(self, dimension: str) -> list[type["StaticCheck"]]:
        """Get all checks for a specific dimension.

        Args:
            dimension: The dimension to filter by.

        Returns:
            List of check classes for the dimension.
        """
        return [c for c in self.get_all() if c.dimension.value == dimension]

    def get_spec_required(self) -> list[type["StaticCheck"]]:
        """Get all checks that are required by the Agent Skills spec.

        Returns:
            List of spec-required check classes.
        """
        return [c for c in self.get_all() if c.spec_required]

    def get_quality_suggestions(self) -> list[type["StaticCheck"]]:
        """Get all checks that are quality suggestions (not spec-required).

        Returns:
            List of quality suggestion check classes.
        """
        return [c for c in self.get_all() if not c.spec_required]


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
