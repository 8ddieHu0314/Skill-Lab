"""Registry for trace check handlers."""

from collections.abc import Callable
from typing import TYPE_CHECKING, TypeVar

if TYPE_CHECKING:
    from skill_lab.tracechecks.handlers.base import TraceCheckHandler

T = TypeVar("T", bound="TraceCheckHandler")


class TraceCheckRegistry:
    """Registry for trace check handlers.

    Handlers register themselves using the @register_trace_handler decorator
    with a check type name. The evaluator looks up handlers by type to
    execute the appropriate check logic.

    Note: This uses composition with Registry rather than inheritance
    because handlers are registered by check_type string, not by class attribute.
    """

    def __init__(self) -> None:
        """Initialize an empty registry."""
        self._handlers: dict[str, type[TraceCheckHandler]] = {}

    def register(self, check_type: str, handler_class: type["TraceCheckHandler"]) -> None:
        """Register a handler class for a check type.

        Args:
            check_type: The check type name (e.g., "command_presence").
            handler_class: The handler class to register.

        Raises:
            ValueError: If the check type is already registered.
        """
        if check_type in self._handlers:
            raise ValueError(f"Handler for check type '{check_type}' already registered")
        self._handlers[check_type] = handler_class

    def get(self, check_type: str) -> type["TraceCheckHandler"] | None:
        """Get the handler class for a check type.

        Args:
            check_type: The check type name.

        Returns:
            The handler class, or None if not found.
        """
        return self._handlers.get(check_type)

    def get_all(self) -> dict[str, type["TraceCheckHandler"]]:
        """Get all registered handlers.

        Returns:
            Dictionary mapping check types to handler classes.
        """
        return dict(self._handlers)

    def has(self, check_type: str) -> bool:
        """Check if a handler is registered for a check type.

        Args:
            check_type: The check type name.

        Returns:
            True if a handler is registered.
        """
        return check_type in self._handlers

    def list_types(self) -> list[str]:
        """Get all registered check types.

        Returns:
            List of check type names.
        """
        return list(self._handlers.keys())

    def clear(self) -> None:
        """Clear all registered handlers. Useful for testing."""
        self._handlers.clear()


# Global registry instance
trace_registry = TraceCheckRegistry()


def register_trace_handler(check_type: str) -> Callable[[type[T]], type[T]]:
    """Decorator to register a trace check handler.

    Args:
        check_type: The check type this handler implements.

    Returns:
        Decorator function that registers the handler class.

    Example:
        @register_trace_handler("command_presence")
        class CommandPresenceHandler(TraceCheckHandler):
            ...
    """

    def decorator(cls: type[T]) -> type[T]:
        trace_registry.register(check_type, cls)
        return cls

    return decorator
