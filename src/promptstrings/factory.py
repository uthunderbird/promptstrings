"""The Promptstrings configuration carrier and the module-level decorator bindings."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any, overload

from .generators import _PromptStringGenerator
from .observability import Observer
from .prompts import _PromptString


class Promptstrings:
    """Configuration carrier for cross-cutting concerns (ADR 0002 Promise I-1).

    Module-level @promptstring and @promptstring_generator delegate to a default
    singleton instance. Construct your own instance when you need a custom observer
    or future extension hooks.

    All __init__ parameters are keyword-only. New parameters are added additively in
    minor releases with defaults that preserve current behavior.
    """

    def __init__(self, *, observer: Observer | None = None) -> None:
        """Create a Promptstrings instance with an optional observer."""
        self._observer = observer

    @overload
    def promptstring(
        self,
        fn: Callable[..., Any],
        *,
        strict: bool = True,
    ) -> _PromptString: ...

    @overload
    def promptstring(
        self,
        fn: None = None,
        *,
        strict: bool = True,
    ) -> Callable[[Callable[..., Any]], _PromptString]: ...

    def promptstring(
        self,
        fn: Callable[..., Any] | None = None,
        *,
        strict: bool = True,
    ) -> _PromptString | Callable[[Callable[..., Any]], _PromptString]:
        """Decorator that creates a _PromptString bound to this instance's observer."""
        if fn is None:
            return lambda wrapped: _PromptString(wrapped, strict=strict, observer=self._observer)
        return _PromptString(fn, strict=strict, observer=self._observer)

    @overload
    def promptstring_generator(
        self,
        fn: Callable[..., Iterable[Any]],
        *,
        strict: bool = False,
    ) -> _PromptStringGenerator: ...

    @overload
    def promptstring_generator(
        self,
        fn: None = None,
        *,
        strict: bool = False,
    ) -> Callable[[Callable[..., Iterable[Any]]], _PromptStringGenerator]: ...

    def promptstring_generator(
        self,
        fn: Callable[..., Iterable[Any]] | None = None,
        *,
        strict: bool = False,
    ) -> _PromptStringGenerator | Callable[[Callable[..., Iterable[Any]]], _PromptStringGenerator]:
        """Decorator that creates a _PromptStringGenerator bound to this instance's observer."""
        if fn is None:
            return lambda wrapped: _PromptStringGenerator(wrapped, strict=strict, observer=self._observer)
        return _PromptStringGenerator(fn, strict=strict, observer=self._observer)

_default = Promptstrings()

promptstring = _default.promptstring

promptstring_generator = _default.promptstring_generator
