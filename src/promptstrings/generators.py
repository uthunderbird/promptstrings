"""The multi-message generator engine."""

from __future__ import annotations

import inspect
import logging
import time
from collections.abc import Callable, Mapping
from string.templatelib import Template
from typing import Any

from .errors import PromptRenderError, PromptUnreferencedParameterError
from .introspection import _annotated_markers, _get_param_type_hints, _response_schema_from_hints
from .observability import (
    Observer,
    RenderEndEvent,
    RenderErrorEvent,
    RenderStartEvent,
    _fire_observer,
)
from .resolution import _resolve_dependencies
from .templates import _render_dynamic
from .types import (
    AwaitPromptDepends,
    PromptContext,
    PromptDepends,
    PromptMessage,
    Role,
    _PromptObject,
)

_strict_heuristic_logger = logging.getLogger("promptstrings.strict_heuristic")

class _PromptStringGenerator(_PromptObject):
    """Generator-based promptstring for multi-message prompts."""

    def __init__(
        self, fn: Callable[..., Any], *, strict: bool = False, observer: Observer | None = None
    ) -> None:
        """Initialize the generator promptstring."""
        self._fn = fn
        self._strict = strict
        self._observer = observer
        self.__name__ = getattr(fn, "__name__", "promptstring_generator")
        self.__doc__ = getattr(fn, "__doc__", None)
        # declared_parameters: immutable at decoration time (ADR 0001 Promise 2).
        self.declared_parameters: Mapping[str, inspect.Parameter] = dict(
            inspect.signature(fn).parameters
        )
        # Cache type hints at decoration time (ADR 0007 D1). Fall back to {} if
        # a return annotation references a name not resolvable in fn's module globals.
        self._hints: dict[str, Any] = _get_param_type_hints(fn)
        # Params with PromptDepends/AwaitPromptDepends are exempt from unused checks —
        # detected in both default slot (silent deprecated) and Annotated metadata (primary).
        self._dep_params: frozenset[str] = frozenset(
            name
            for name, param in self.declared_parameters.items()
            if (
                isinstance(param.default, (PromptDepends, AwaitPromptDepends))
                or any(
                    isinstance(m, (PromptDepends, AwaitPromptDepends))
                    for m in _annotated_markers(self._hints.get(name))
                )
            )
        )
        self.response_schema: Any = _response_schema_from_hints(self._hints)

    def __repr__(self) -> str:
        """Name this object instead of showing a default address repr (ADR 0011 D5)."""
        return f"<unrendered promptstring {getattr(self, '__name__', '?')!r}>"

    @property
    def placeholders(self) -> frozenset[str]:
        """Always empty for generator promptstrings (no static template to parse)."""
        return frozenset()

    async def _render_messages_impl(self, ctx: PromptContext) -> list[PromptMessage]:
        """Core rendering logic shared by render() and render_messages()."""
        resolved = await _resolve_dependencies(self._fn, ctx, hints=self._hints)
        generator = self._fn(**resolved)
        if inspect.isasyncgen(generator):
            items = [item async for item in generator]
        else:
            items = list(generator)

        messages: list[PromptMessage] = []
        role = "system"
        buffer: list[str] = []

        def flush() -> None:
            """Flush the current buffer into a PromptMessage."""
            if not buffer:
                return
            messages.append(PromptMessage(role=role, content="\n".join(buffer)))
            buffer.clear()

        template_yields: list[Template] = []

        for item in items:
            if isinstance(item, Role):
                flush()
                role = item.name
                continue
            if isinstance(item, PromptMessage):
                flush()
                messages.append(item)
                continue
            if isinstance(item, str):
                buffer.append(item)
                continue
            if isinstance(item, Template):
                template_yields.append(item)
                buffer.append(_render_dynamic(item))
                continue
            raise PromptRenderError(
                f"Unsupported promptstring generator yield type: {type(item)!r}"
            )

        flush()

        if self._strict:
            str_yields = [item for item in items if isinstance(item, str)]
            all_structured = (
                bool(template_yields)
                and not str_yields
                and all(
                    i.expression.isidentifier() and i.expression in resolved
                    for tpl in template_yields
                    for i in tpl.interpolations
                )
            )
            used: frozenset[str]
            if all_structured:
                # Structural strict-mode: exact expression check (ADR 0005).
                used = frozenset(
                    i.expression
                    for tpl in template_yields
                    for i in tpl.interpolations
                )
            else:
                # Substring heuristic (ADR 0004) — for str and mixed yields.
                for name, value in resolved.items():
                    str_val = str(value)
                    if str_val == "":
                        _strict_heuristic_logger.warning(
                            "Parameter %r has an empty str() value; the substring-occurrence "
                            "check will always report it as used (false negative).",
                            name,
                        )
                    elif len(str_val) <= 1:
                        _strict_heuristic_logger.warning(
                            "Parameter %r has a single-character str() value %r; the "
                            "substring-occurrence check has elevated false-positive risk.",
                            name,
                            str_val,
                        )
                used = frozenset(
                    name
                    for name, value in resolved.items()
                    if str(value) in "\n".join(m.content for m in messages)
                )
            unused_params = sorted(
                name for name in resolved
                if name not in used and name not in self._dep_params
            )
            if unused_params:
                names = ", ".join(f"'{n}'" for n in unused_params)
                raise PromptUnreferencedParameterError(
                    f"Parameter(s) {names} were resolved but not found in any yielded output. "
                    f"Include the value of '{unused_params[0]}' in a yield statement, "
                    f"or pass strict=False to allow unreferenced parameters.",
                    unreferenced_parameters=tuple(unused_params),
                    resolved_keys=tuple(sorted(resolved.keys())),
                )
        return messages

    async def render_messages(self, context: PromptContext | None = None) -> list[PromptMessage]:
        """Render the generator to a list of PromptMessage objects, firing Observer events."""
        ctx = context or PromptContext()
        started_at = time.monotonic_ns()
        _fire_observer(
            self._observer,
            RenderStartEvent(
                prompt_name=self.__name__,
                placeholders=self.placeholders,
                started_at_ns=started_at,
            ),
        )
        try:
            messages = await self._render_messages_impl(ctx)
        except BaseException as exc:
            _fire_observer(
                self._observer,
                RenderErrorEvent(
                    prompt_name=self.__name__,
                    elapsed_ns=time.monotonic_ns() - started_at,
                    error=exc,
                ),
            )
            raise
        _fire_observer(
            self._observer,
            RenderEndEvent(
                prompt_name=self.__name__,
                elapsed_ns=time.monotonic_ns() - started_at,
                message_count=len(messages),
                provenance=None,
            ),
        )
        return messages

    async def render(self, context: PromptContext | None = None) -> str:
        """Render the generator to a single joined string, firing Observer events."""
        ctx = context or PromptContext()
        started_at = time.monotonic_ns()
        _fire_observer(
            self._observer,
            RenderStartEvent(
                prompt_name=self.__name__,
                placeholders=self.placeholders,
                started_at_ns=started_at,
            ),
        )
        try:
            messages = await self._render_messages_impl(ctx)
        except BaseException as exc:
            _fire_observer(
                self._observer,
                RenderErrorEvent(
                    prompt_name=self.__name__,
                    elapsed_ns=time.monotonic_ns() - started_at,
                    error=exc,
                ),
            )
            raise
        _fire_observer(
            self._observer,
            RenderEndEvent(
                prompt_name=self.__name__,
                elapsed_ns=time.monotonic_ns() - started_at,
                message_count=len(messages),
                provenance=None,
            ),
        )
        return "\n\n".join(message.content for message in messages)
