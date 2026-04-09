"""Minimal event bus stub for QuantBot.

Paper mode only - no real trading.
"""

from typing import Any, Callable


class EventBus:
    """Lightweight event dispatch hub."""

    def __init__(self) -> None:
        self._handlers: dict[str, list[Callable[[Any], None]]] = {}

    def subscribe(self, topic: str, handler: Callable[[Any], None]) -> None:
        """Register a handler for a topic."""
        if topic not in self._handlers:
            self._handlers[topic] = []
        self._handlers[topic].append(handler)

    def publish(self, topic: str, payload: Any) -> None:
        """Dispatch payload to all handlers of topic."""
        for handler in self._handlers.get(topic, []):
            handler(payload)

    def clear(self) -> None:
        """Remove all handlers."""
        self._handlers.clear()
