"""Shared utilities for the skill-lab framework."""

from collections.abc import Callable
from typing import Generic, TypeVar

T = TypeVar("T")


class Registry(Generic[T]):
    """Generic registry for managing registered items.

    Provides a common implementation for registering and retrieving items
    by their identifier. Used by both CheckRegistry and TraceCheckRegistry.

    Type Parameters:
        T: The type of items stored in the registry.
    """

    def __init__(self, id_extractor: Callable[[type[T]], str]) -> None:
        """Initialize the registry.

        Args:
            id_extractor: Function to extract the ID from an item class.
        """
        self._items: dict[str, type[T]] = {}
        self._id_extractor = id_extractor

    def register(self, item_class: type[T]) -> type[T]:
        """Register an item class.

        Args:
            item_class: The item class to register.

        Returns:
            The item class (for use as decorator).

        Raises:
            ValueError: If an item with the same ID is already registered.
        """
        item_id = self._id_extractor(item_class)
        if item_id in self._items:
            raise ValueError(f"Item with ID '{item_id}' is already registered")
        self._items[item_id] = item_class
        return item_class

    def get(self, item_id: str) -> type[T] | None:
        """Get an item class by ID.

        Args:
            item_id: The item ID to look up.

        Returns:
            The item class or None if not found.
        """
        return self._items.get(item_id)

    def get_all(self) -> list[type[T]]:
        """Get all registered item classes.

        Returns:
            List of all registered item classes.
        """
        return list(self._items.values())

    def has(self, item_id: str) -> bool:
        """Check if an item is registered.

        Args:
            item_id: The item ID to check.

        Returns:
            True if the item is registered.
        """
        return item_id in self._items

    def list_ids(self) -> list[str]:
        """Get all registered item IDs.

        Returns:
            List of item IDs.
        """
        return list(self._items.keys())

    def clear(self) -> None:
        """Clear all registered items. Useful for testing."""
        self._items.clear()
