"""Shared utilities for the skill-lab framework."""

from collections.abc import Callable
from dataclasses import fields, is_dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Generic, TypeVar

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

    def register_with_key(self, key: str, item_class: type[T]) -> None:
        """Register an item class with an explicit key.

        Args:
            key: The key to register the item under.
            item_class: The item class to register.

        Raises:
            ValueError: If the key is already registered.
        """
        if key in self._items:
            raise ValueError(f"Item with key '{key}' is already registered")
        self._items[key] = item_class

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

    def get_all_dict(self) -> dict[str, type[T]]:
        """Get all registered items as a dictionary.

        Returns:
            Dictionary mapping IDs to item classes.
        """
        return dict(self._items)

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


def serialize_value(value: Any) -> Any:
    """Serialize a value for JSON output.

    Handles common types like Enum, Path, dataclasses, and nested structures.

    Args:
        value: The value to serialize.

    Returns:
        JSON-serializable value.
    """
    if value is None:
        return None
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (list, tuple)):
        return [serialize_value(item) for item in value]
    if isinstance(value, dict):
        return {k: serialize_value(v) for k, v in value.items()}
    if is_dataclass(value) and not isinstance(value, type):
        # Recursively serialize dataclass
        if hasattr(value, "to_dict"):
            return value.to_dict()
        return {f.name: serialize_value(getattr(value, f.name)) for f in fields(value)}
    return value
