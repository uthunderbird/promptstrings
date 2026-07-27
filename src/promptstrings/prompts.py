"""The single-message prompt engine."""

from __future__ import annotations

import inspect
import time
from collections.abc import Callable, Mapping
from string.templatelib import Template
from typing import Any

from .errors import PromptRenderError, PromptUnusedParameterError
from .introspection import _annotated_markers, _get_param_type_hints, _response_schema_from_hints
from .observability import (
    Observer,
    RenderEndEvent,
    RenderErrorEvent,
    RenderStartEvent,
    _fire_observer,
)
from .resolution import _maybe_await, _resolve_dependencies
from .templates import (
    _MISSING,
    _compile_at_decoration,
    _placeholders_from_template,
    _render_dynamic,
    _render_static,
)
from .types import (
    AwaitPromptDepends,
    PromptContext,
    PromptDepends,
    PromptMessage,
    PromptSource,
    _PromptObject,
)


class _PromptString(_PromptObject):
    """Compiled promptstring backed by a function body or docstring template."""

    def __init__(
        self, fn: Callable[..., Any], *, strict: bool = True, observer: Observer | None = None
    ) -> None:
        """Initialize and eagerly compile the template when possible."""
        self._fn = fn
        self._strict = strict
        self._observer = observer
        self.__name__ = getattr(fn, "__name__", "promptstring")
        self.__doc__ = getattr(fn, "__doc__", None)
        # Eagerly compile template at decoration time (ADR 0001 Promises 7+8, ADR 0005).
        # _compiled is None for dynamic-source functions (Template/PromptSource annotation).
        self._compiled: Template | None = _compile_at_decoration(fn, self.__name__)
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
        """Name this object instead of showing a default address repr (ADR 0011 D5).

        The D3 guard raises when a prompt object is a parameter value, but it
        cannot see one nested inside a container: containers format elements
        with repr(). Self-describing here covers every container type and depth
        without enumerating any. getattr guards against repr ever raising.
        """
        return f"<unrendered promptstring {getattr(self, '__name__', '?')!r}>"

    @property
    def placeholders(self) -> frozenset[str]:
        """Placeholder names from the compiled Template (ADR 0005).

        Returns frozenset() for dynamic-source functions whose template is not
        known until render time (ADR 0001 non-promise 10).
        """
        if self._compiled is not None:
            return _placeholders_from_template(self._compiled)
        return frozenset()

    async def _resolve_source(self, resolved: dict[str, Any]) -> tuple[Template | PromptSource, bool]:
        """Call the decorated function and normalize its return value.

        Returns (template_or_source, is_static). When is_static is True,
        the eagerly-compiled Template can be reused with _render_static.
        When False, the returned value is either a Template (use _render_dynamic)
        or a PromptSource with str content (parse and render via _render_static
        with a freshly parsed Template).
        """
        source_candidate = await _maybe_await(self._fn(**resolved))
        # Guard: docstring functions must return None or ... (ADR 0006 D2).
        if self._compiled is not None and source_candidate is not None and source_candidate is not ...:
            raise PromptRenderError(
                f"Docstring-based promptstring {self.__name__!r} returned a non-None, non-Ellipsis value "
                f"at render time. Annotate with -> Template or -> PromptSource for dynamic sources."
            )
        if source_candidate is None or source_candidate is ...:
            # Docstring path — use the eagerly compiled static Template.
            return self._compiled or PromptSource(content=""), True
        if isinstance(source_candidate, Template):
            # T-string return — already resolved, use _render_dynamic.
            return source_candidate, False
        if isinstance(source_candidate, str):
            return PromptSource(content=source_candidate), False
        if isinstance(source_candidate, PromptSource):
            return source_candidate, False
        raise PromptRenderError(
            "Promptstring source selector must return None, ..., str, Template, or PromptSource, "
            f"got {type(source_candidate)!r}"
        )

    async def _render_messages_impl(
        self, ctx: PromptContext
    ) -> list[PromptMessage]:
        """Core rendering logic shared by render() and render_messages()."""
        resolved = await _resolve_dependencies(self._fn, ctx, hints=self._hints)
        source, is_static = await self._resolve_source(resolved)

        # Determine the Template and render strategy.
        if is_static:
            # Docstring-derived static Template: use expression→resolved lookup.
            assert isinstance(source, Template)
            tpl = source
            placeholders = _placeholders_from_template(tpl)
            if missing := sorted(name for name in placeholders if name not in resolved):
                raise PromptRenderError(f"Missing prompt values for placeholders: {', '.join(missing)}")
            if self._strict:
                unused_params = sorted(
                    name for name in resolved
                    if name not in placeholders and name not in self._dep_params
                )
                if unused_params:
                    names = ", ".join(f"'{n}'" for n in unused_params)
                    raise PromptUnusedParameterError(
                        f"Parameter(s) {names} were resolved but not referenced in the template. "
                        f"Add a {{{unused_params[0]}}} placeholder to the docstring, or pass strict=False "
                        f"to allow unused parameters.",
                        unused_parameters=tuple(unused_params),
                        resolved_keys=tuple(sorted(resolved.keys())),
                    )
            content = _render_static(tpl, resolved)
            provenance = None
        elif isinstance(source, Template):
            tpl = source
            placeholders = _placeholders_from_template(tpl)
            # Detect whether this Template came from parse_trusted_template (has _MISSING
            # sentinel values) or from a real t-string (values already resolved).
            is_parse_derived = any(
                i.value is _MISSING for i in tpl.interpolations
            )
            if is_parse_derived:
                # parse_trusted_template path: render via expression→resolved lookup.
                if missing := sorted(name for name in placeholders if name not in resolved):
                    raise PromptRenderError(
                        f"Missing prompt values for placeholders: {', '.join(missing)}"
                    )
                if self._strict:
                    unused_params = sorted(
                        name for name in resolved
                        if name not in placeholders and name not in self._dep_params
                    )
                    if unused_params:
                        names = ", ".join(f"'{n}'" for n in unused_params)
                        raise PromptUnusedParameterError(
                            f"Parameter(s) {names} were resolved but not referenced in the template. "
                            f"Add a {{{unused_params[0]}}} placeholder to the template string, or pass strict=False "
                            f"to allow unused parameters.",
                            unused_parameters=tuple(unused_params),
                            resolved_keys=tuple(sorted(resolved.keys())),
                        )
                content = _render_static(tpl, resolved)
            else:
                # T-string-derived dynamic Template: values already resolved.
                if self._strict:
                    unused_params = sorted(
                        name for name in resolved
                        if name not in placeholders and name not in self._dep_params
                    )
                    if unused_params:
                        names = ", ".join(f"'{n}'" for n in unused_params)
                        raise PromptUnusedParameterError(
                            f"Parameter(s) {names} were resolved but not referenced in the returned t-string. "
                            f"Include {{param}} in the t-string, or pass strict=False to allow unused parameters.",
                            unused_parameters=tuple(unused_params),
                            resolved_keys=tuple(sorted(resolved.keys())),
                        )
                content = _render_dynamic(tpl)
            provenance = None
        else:
            # PromptSource — literal passthrough (ADR 0006 D1).
            assert isinstance(source, PromptSource)
            content = source.content
            provenance = source.provenance

        return [PromptMessage(role="system", content=content, source=provenance)]

    async def render(self, context: PromptContext | None = None) -> str:
        """Render the prompt to a single string, firing Observer events."""
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
                provenance=messages[0].source if messages else None,
            ),
        )
        return "\n".join(m.content for m in messages)

    async def render_messages(self, context: PromptContext | None = None) -> list[PromptMessage]:
        """Render the prompt to a list of PromptMessage objects, firing Observer events."""
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
                provenance=messages[0].source if messages else None,
            ),
        )
        return messages
