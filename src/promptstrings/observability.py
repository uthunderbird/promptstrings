"""The Observer Protocol, its three events, the no-op default, and exception-swallowing dispatch."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from .types import PromptSourceProvenance


@dataclass(frozen=True)
class RenderStartEvent:
    """Emitted exactly once at the start of each render call (ADR 0002 Promise I-2)."""

    prompt_name: str
    """Name of the decorated function being rendered."""

    placeholders: frozenset[str]
    """Placeholder set at decoration time."""

    started_at_ns: int
    """Monotonic timestamp in nanoseconds (time.monotonic_ns())."""

@dataclass(frozen=True)
class RenderEndEvent:
    """Emitted exactly once at the successful end of each render call (ADR 0002 Promise I-2)."""

    prompt_name: str
    """Name of the decorated function that completed rendering."""

    elapsed_ns: int
    """Elapsed nanoseconds from start to end of this render call."""

    message_count: int
    """Number of PromptMessage objects in the render result."""

    provenance: PromptSourceProvenance | None
    """Provenance from the rendered source; None if no provenance was supplied."""

@dataclass(frozen=True)
class RenderErrorEvent:
    """Emitted exactly once when a render call raises (ADR 0002 Promise I-2)."""

    prompt_name: str
    """Name of the decorated function that raised."""

    elapsed_ns: int
    """Elapsed nanoseconds from start to the point the error was raised."""

    error: BaseException
    """The exception that caused the render to fail."""

@runtime_checkable
class Observer(Protocol):
    """Sync structured-event sink for render lifecycle (ADR 0002 Promise I-2).

    Implementations must be synchronous. Any async work must be scheduled internally.
    Exceptions raised from observer methods are caught, logged at WARNING via
    promptstrings.observer, and discarded — render outcome is unaffected.
    """

    def on_render_start(self, event: RenderStartEvent) -> None:
        """Called exactly once before any resolver runs."""
        ...

    def on_render_end(self, event: RenderEndEvent) -> None:
        """Called exactly once on successful render completion."""
        ...

    def on_render_error(self, event: RenderErrorEvent) -> None:
        """Called exactly once when a render call raises, before the exception propagates."""
        ...

_observer_logger = logging.getLogger("promptstrings.observer")

class _NoOpObserver:
    """Default no-op implementation of Observer; used by the default Promptstrings singleton."""

    def on_render_start(self, event: RenderStartEvent) -> None:
        """No-op."""

    def on_render_end(self, event: RenderEndEvent) -> None:
        """No-op."""

    def on_render_error(self, event: RenderErrorEvent) -> None:
        """No-op."""

def _fire_observer(observer: Observer | None, event: Any) -> None:
    """Call the appropriate observer method for event, swallowing and logging exceptions."""
    if observer is None:
        return
    try:
        if isinstance(event, RenderStartEvent):
            observer.on_render_start(event)
        elif isinstance(event, RenderEndEvent):
            observer.on_render_end(event)
        elif isinstance(event, RenderErrorEvent):
            observer.on_render_error(event)
    except Exception:
        _observer_logger.warning(
            "Observer %r raised during %s; exception discarded.",
            observer,
            type(event).__name__,
            exc_info=True,
        )
