"""Registry for trace check handlers."""

from collections.abc import Callable
from typing import TYPE_CHECKING, TypeVar

from skill_lab.core.utils import Registry

if TYPE_CHECKING:
    from skill_lab.tracechecks.handlers.base import TraceCheckHandler

T = TypeVar("T", bound="TraceCheckHandler")


class TraceCheckRegistry(Registry["TraceCheckHandler"]):
    """Registry for trace check handlers.

    Extends the generic Registry with check-type-based registration.
    Handlers register via the @register_trace_handler decorator which
    sets check_type on the class before registering.
    """

    def __init__(self) -> None:
        """Initialize the trace check registry."""
        super().__init__(id_extractor=lambda cls: cls.check_type)


# Global registry instance
trace_registry = TraceCheckRegistry()


def register_trace_handler(check_type: str) -> Callable[[type[T]], type[T]]:
    """Decorator to register a trace check handler.

    Sets the check_type class attribute on the handler and registers it
    with the global trace_registry.

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
        cls.check_type = check_type
        trace_registry.register(cls)
        return cls

    return decorator
