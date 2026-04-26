"""Core implementation of the promptstrings prompt-template library."""

from __future__ import annotations

import asyncio
import inspect
import logging
import sys
import textwrap
import time
from collections.abc import Awaitable, Callable, Iterable, Mapping
from dataclasses import dataclass, field
from string import Formatter
from string.templatelib import Interpolation, Template
from typing import Any, Literal, Protocol, overload, runtime_checkable

_strict_heuristic_logger = logging.getLogger("promptstrings.strict_heuristic")


class PromptRenderError(RuntimeError):
    """Base class for all prompt render-time failures (ADR 0003).

    Named attributes are JSON-safe and picklable. Use to_dict() for structured
    access from agents and tooling.
    """

    missing_key: str | None
    """Parameter name that could not be resolved; None for non-missing-key failures."""

    context_keys: tuple[str, ...] | None
    """Keys present in PromptContext.values at error time; None when context unavailable."""

    def __init__(
        self,
        message: str,
        *,
        missing_key: str | None = None,
        context_keys: tuple[str, ...] | None = None,
    ) -> None:
        """Initialise with optional structured fields."""
        super().__init__(message)
        self.missing_key = missing_key
        self.context_keys = context_keys

    def __reduce__(self) -> tuple[Any, ...]:
        """Support pickle round-trip for all named attributes."""
        return (
            self.__class__,
            (str(self),),
            {"missing_key": self.missing_key, "context_keys": self.context_keys},
        )

    def __setstate__(self, state: dict[str, Any] | None) -> None:
        """Restore named attributes after unpickling."""
        if state:
            for k, v in state.items():
                setattr(self, k, v)

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-safe dict representation (ADR 0003 rules R-A through R-E)."""
        return {
            "type": type(self).__name__,
            "message": str(self),
            "missing_key": self.missing_key,
            "context_keys": list(self.context_keys) if self.context_keys is not None else None,
        }


class PromptCompileError(PromptRenderError):
    """Raised at decoration time when a template cannot be compiled (ADR 0003).

    prompt_name, cause, placeholder, and optimize_mode_active identify the
    specific compile-time failure. missing_key and context_keys are always None.
    """

    prompt_name: str
    """__name__ of the decorated function; always set."""

    cause: Literal["missing_template", "format_spec", "conversion", "non_identifier_placeholder", "mixed_source_mode"]
    """Discriminator for which compile-time check failed."""

    placeholder: str | None
    """Offending placeholder text; None for cause='missing_template'."""

    optimize_mode_active: bool
    """True iff sys.flags.optimize >= 2 at decoration time."""

    def __init__(
        self,
        message: str,
        *,
        prompt_name: str = "<unknown>",
        cause: Literal[
            "missing_template", "format_spec", "conversion", "non_identifier_placeholder", "mixed_source_mode"
        ] = "missing_template",
        placeholder: str | None = None,
        optimize_mode_active: bool = False,
    ) -> None:
        """Initialise with compile-time error fields; missing_key/context_keys are always None."""
        super().__init__(message, missing_key=None, context_keys=None)
        self.prompt_name = prompt_name
        self.cause = cause
        self.placeholder = placeholder
        self.optimize_mode_active = optimize_mode_active

    def __reduce__(self) -> tuple[Any, ...]:
        """Support pickle round-trip for all named attributes."""
        return (
            self.__class__,
            (str(self),),
            {
                "prompt_name": self.prompt_name,
                "cause": self.cause,
                "placeholder": self.placeholder,
                "optimize_mode_active": self.optimize_mode_active,
            },
        )

    def __setstate__(self, state: dict[str, Any] | None) -> None:
        """Restore named attributes after unpickling."""
        # Parent fields default to None for compile errors.
        self.missing_key = None
        self.context_keys = None
        if state:
            for k, v in state.items():
                setattr(self, k, v)

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-safe dict representation (ADR 0003 rules R-A through R-E)."""
        return {
            "type": type(self).__name__,
            "message": str(self),
            "prompt_name": self.prompt_name,
            "cause": self.cause,
            "placeholder": self.placeholder,
            "optimize_mode_active": self.optimize_mode_active,
            "missing_key": None,
            "context_keys": None,
        }


class PromptStrictnessError(PromptRenderError):
    """Parent class for strict-mode failures; never raised directly by library code.

    Catch this class to handle both PromptUnusedParameterError (template path)
    and PromptUnreferencedParameterError (generator path) uniformly.
    to_dict() is inherited from PromptRenderError; leaf classes override it.
    """

    pass


class PromptUnusedParameterError(PromptStrictnessError):
    """Raised by @promptstring when a resolved parameter is not in the template (ADR 0001 P3).

    Fix: remove the parameter from the function signature, or add a {name} placeholder.
    """

    unused_parameters: tuple[str, ...]
    """Names of parameters that were resolved but not consumed by the template."""

    resolved_keys: tuple[str, ...]
    """All parameter names that were resolved at render time."""

    def __init__(
        self,
        message: str,
        *,
        unused_parameters: tuple[str, ...] = (),
        resolved_keys: tuple[str, ...] = (),
    ) -> None:
        """Initialise with the set of unused and all resolved parameter names."""
        super().__init__(message)
        self.unused_parameters = unused_parameters
        self.resolved_keys = resolved_keys

    def __reduce__(self) -> tuple[Any, ...]:
        """Support pickle round-trip."""
        return (
            self.__class__,
            (str(self),),
            {
                "unused_parameters": self.unused_parameters,
                "resolved_keys": self.resolved_keys,
            },
        )

    def __setstate__(self, state: dict[str, Any] | None) -> None:
        """Restore named attributes after unpickling."""
        self.missing_key = None
        self.context_keys = None
        if state:
            for k, v in state.items():
                setattr(self, k, v)

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-safe dict representation (ADR 0003 rules R-A through R-E)."""
        return {
            "type": type(self).__name__,
            "message": str(self),
            "unused_parameters": list(self.unused_parameters),
            "resolved_keys": list(self.resolved_keys),
            "missing_key": None,
            "context_keys": None,
        }


class PromptUnreferencedParameterError(PromptStrictnessError):
    """Raised by @promptstring_generator (strict=True) when a parameter value is not in output.

    Fix: yield a string containing the parameter's str() value, or remove the parameter.
    Note: the detection is best-effort (substring heuristic); see ADR 0004.
    """

    unreferenced_parameters: tuple[str, ...]
    """Names of parameters whose str() value was not found in the rendered output."""

    resolved_keys: tuple[str, ...]
    """All parameter names that were resolved at render time."""

    def __init__(
        self,
        message: str,
        *,
        unreferenced_parameters: tuple[str, ...] = (),
        resolved_keys: tuple[str, ...] = (),
    ) -> None:
        """Initialise with the set of unreferenced and all resolved parameter names."""
        super().__init__(message)
        self.unreferenced_parameters = unreferenced_parameters
        self.resolved_keys = resolved_keys

    def __reduce__(self) -> tuple[Any, ...]:
        """Support pickle round-trip."""
        return (
            self.__class__,
            (str(self),),
            {
                "unreferenced_parameters": self.unreferenced_parameters,
                "resolved_keys": self.resolved_keys,
            },
        )

    def __setstate__(self, state: dict[str, Any] | None) -> None:
        """Restore named attributes after unpickling."""
        self.missing_key = None
        self.context_keys = None
        if state:
            for k, v in state.items():
                setattr(self, k, v)

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-safe dict representation (ADR 0003 rules R-A through R-E)."""
        return {
            "type": type(self).__name__,
            "message": str(self),
            "unreferenced_parameters": list(self.unreferenced_parameters),
            "resolved_keys": list(self.resolved_keys),
            "missing_key": None,
            "context_keys": None,
        }


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


@runtime_checkable
class Promptstring(Protocol):
    """Runtime-checkable Protocol for all promptstring objects (ADR 0001 Promise 2).

    The long-term extension surface for the library. User code should type against
    this Protocol rather than against concrete classes. Append-only in 1.x.
    """

    placeholders: frozenset[str]
    """Placeholder names declared in the template. Empty for dynamic-source functions."""

    declared_parameters: Mapping[str, inspect.Parameter]
    """Declared parameters of the underlying function, keyed by name."""

    async def render(self, context: PromptContext | None = None) -> str:
        """Render the prompt to a single string."""
        ...

    async def render_messages(self, context: PromptContext | None = None) -> list[PromptMessage]:
        """Render the prompt to a list of PromptMessage objects."""
        ...


@dataclass(frozen=True)
class PromptMessage:
    """A single rendered prompt message with role, content, and optional provenance."""

    role: str
    content: str
    source: PromptSourceProvenance | None = None


@dataclass(frozen=True)
class Role:
    """A role marker yielded by a promptstring_generator to switch the current role."""

    name: str


@dataclass(frozen=True)
class PromptSourceProvenance:
    """User-supplied provenance metadata for a prompt source."""

    source_id: str | None = None
    version: str | None = None
    hash: str | None = None
    provider_name: str | None = None

    def as_metadata(self) -> dict[str, str]:
        """Return a dict of non-None provenance fields."""
        metadata: dict[str, str] = {}
        if self.source_id is not None:
            metadata["source_id"] = self.source_id
        if self.version is not None:
            metadata["version"] = self.version
        if self.hash is not None:
            metadata["hash"] = self.hash
        if self.provider_name is not None:
            metadata["provider_name"] = self.provider_name
        return metadata


@dataclass(frozen=True)
class PromptSource:
    """A prompt source with optional provenance metadata."""

    content: str
    provenance: PromptSourceProvenance | None = None


@dataclass(frozen=True)
class PromptContext:
    """Immutable container for values and framework handles used during rendering.

    values: user-supplied parameter values for dependency resolution.
    extras: framework-supplied handles (DI containers, tracers, etc.); not read
            by the library. Convention: use leading-underscore keys for framework state.
    """

    values: dict[str, Any] = field(default_factory=dict)
    extras: Mapping[str, Any] = field(default_factory=dict)

    def get(self, key: str, default: Any = None) -> Any:
        """Return the value for key from values, or default if absent."""
        return self.values.get(key, default)

    def require(self, key: str) -> Any:
        """Return the value for key from values, raising PromptRenderError if absent."""
        if key not in self.values:
            raise PromptRenderError(
                f"Missing prompt context value: {key}",
                missing_key=key,
                context_keys=tuple(self.values.keys()),
            )
        return self.values[key]


Resolver = Callable[[PromptContext], Any] | Callable[[PromptContext], Awaitable[Any]]


@dataclass(frozen=True)
class PromptDepends:
    """Sync dependency-injection marker; resolver is called with the PromptContext."""

    resolver: Resolver


@dataclass(frozen=True)
class AwaitPromptDepends:
    """Async dependency-injection marker; resolver is awaited with the PromptContext."""

    resolver: Resolver


_MISSING: object = object()
"""Sentinel value used in docstring-derived Interpolation objects before render time."""


async def _maybe_await(value: Any) -> Any:
    """Await value if it is awaitable; otherwise return it directly."""
    if inspect.isawaitable(value):
        return await value
    return value


def _parse_docstring(source: str, *, prompt_name: str = "<unknown>") -> Template:
    """Parse a docstring template string into a stdlib Template (ADR 0005).

    Uses string.Formatter to parse the docstring, applies all grammar guards
    (no format specs, no conversions, identifier-only placeholders), then
    constructs a Template with _MISSING sentinels as Interpolation values.

    Raises PromptCompileError for unsupported grammar.
    """
    formatter = Formatter()
    args: list[str | Interpolation] = []
    for literal, field_name, format_spec, conversion in formatter.parse(source):
        if literal:
            args.append(literal)
        if field_name is None:
            continue
        if format_spec:
            raise PromptCompileError(
                f"Format specs are not supported in promptstrings (prompt: {prompt_name!r})",
                prompt_name=prompt_name,
                cause="format_spec",
                placeholder=field_name,
                optimize_mode_active=sys.flags.optimize >= 2,
            )
        if conversion:
            raise PromptCompileError(
                f"Conversions are not supported in promptstrings (prompt: {prompt_name!r})",
                prompt_name=prompt_name,
                cause="conversion",
                placeholder=field_name,
                optimize_mode_active=sys.flags.optimize >= 2,
            )
        if not field_name.isidentifier():
            raise PromptCompileError(
                f"Promptstring placeholders must use the minimal {{identifier}} grammar "
                f"(got {field_name!r}, prompt: {prompt_name!r})",
                prompt_name=prompt_name,
                cause="non_identifier_placeholder",
                placeholder=field_name,
                optimize_mode_active=sys.flags.optimize >= 2,
            )
        args.append(Interpolation(_MISSING, field_name))
    return Template(*args) if args else Template("")


def _placeholders_from_template(tpl: Template) -> frozenset[str]:
    """Extract placeholder names from a docstring-derived Template."""
    return frozenset(i.expression for i in tpl.interpolations)


def _render_static(tpl: Template, resolved: dict[str, Any]) -> str:
    """Render a docstring-derived Template using expression→resolved lookup."""
    parts: list[str] = []
    for item in tpl:
        if isinstance(item, str):
            parts.append(item)
        else:
            try:
                parts.append(str(resolved[item.expression]))
            except KeyError:
                raise PromptRenderError(
                    f"Template expression {item.expression!r} has no matching resolved parameter",
                    missing_key=item.expression,
                )
    return "".join(parts)


def parse_docstring_template(source: str, *, prompt_name: str = "<unknown>") -> Template:
    """Parse a template string into a stdlib Template for use in @promptstring functions.

    Applies the same grammar guards as docstring templates: identifier-only
    placeholders, no format specs, no conversions.

    Use this when loading prompt templates from external sources (database, config
    system) that need placeholder substitution at render time. Return the resulting
    Template from a function annotated ``-> Template``.

    .. warning::
        Do not pass user-controlled strings to this function. The caller is
        responsible for ensuring *source* is trusted content. Placeholder
        expressions in the returned Template are substituted at render time from
        resolved parameters — user-controlled input containing ``{param_name}``
        syntax will be substituted silently.
    """
    return _parse_docstring(source, prompt_name=prompt_name)


def _render_dynamic(tpl: Template) -> str:
    """Render a t-string-derived Template using already-resolved Interpolation values."""
    return "".join(
        item if isinstance(item, str) else str(item.value)
        for item in tpl
    )


def _has_dynamic_return_annotation(fn: Callable[..., Any]) -> bool:
    """Return True if fn's return annotation proves it returns PromptSource or Template dynamically."""
    try:
        hints = fn.__annotations__
    except AttributeError:
        return False
    return_hint = hints.get("return")
    if return_hint is None:
        return False
    return (
        return_hint is PromptSource
        or return_hint == "PromptSource"
        or return_hint is Template
        or return_hint == "Template"
    )


def _compile_at_decoration(
    fn: Callable[..., Any],
    prompt_name: str,
) -> Template | None:
    """Attempt to compile a template at decoration time (ADR 0005).

    Returns a Template when the function has a docstring-based template.
    Returns None when the function is dynamic-source (PromptSource or Template annotation).
    Raises PromptCompileError immediately when neither condition holds.
    """
    docstring = getattr(fn, "__doc__", None)
    if docstring:
        # Guard: docstring + dynamic return annotation = mixed source mode (ADR 0006 D2).
        if _has_dynamic_return_annotation(fn):
            raise PromptCompileError(
                f"Promptstring {prompt_name!r} has both a docstring template and a dynamic "
                f"return annotation; use one or the other.",
                prompt_name=prompt_name,
                cause="mixed_source_mode",
                placeholder=None,
                optimize_mode_active=sys.flags.optimize >= 2,
            )
        normalized = textwrap.dedent(docstring).strip()
        return _parse_docstring(normalized, prompt_name=prompt_name)

    # No docstring — check if the function proves it returns a dynamic source.
    if _has_dynamic_return_annotation(fn):
        # Dynamic source: placeholders cannot be known until render time.
        return None

    # Neither docstring nor dynamic annotation: fail immediately.
    optimize_active = sys.flags.optimize >= 2
    optimize_note = " (docstrings are stripped by python -OO; run without -OO)" if optimize_active else ""
    raise PromptCompileError(
        f"Promptstring {prompt_name!r} has no docstring and its return annotation does not "
        f"prove a PromptSource or Template is returned.{optimize_note}",
        prompt_name=prompt_name,
        cause="missing_template",
        placeholder=None,
        optimize_mode_active=optimize_active,
    )


async def _resolve_dependencies(
    fn: Callable[..., Any],
    context: PromptContext,
) -> dict[str, Any]:
    """Resolve all declared parameters for fn using the given context.

    Sync PromptDepends run sequentially in declaration order.
    AwaitPromptDepends run concurrently via asyncio.gather; the first exception
    cancels the rest (ADR 0001 Promise 9). No limit on async dep count.
    """
    signature = inspect.signature(fn)
    resolved: dict[str, Any] = {}
    async_names: list[str] = []
    async_coros: list[Any] = []

    for name, parameter in signature.parameters.items():
        default = parameter.default
        if isinstance(default, AwaitPromptDepends):
            # Collect coroutines; run all concurrently after sync deps.
            async_names.append(name)
            async_coros.append(default.resolver(context))
            continue
        if isinstance(default, PromptDepends):
            resolved[name] = await _maybe_await(default.resolver(context))
            continue
        if name in context.values:
            resolved[name] = context.values[name]
            continue
        if default is inspect.Parameter.empty:
            raise PromptRenderError(
                f"Unable to resolve prompt parameter: {name}",
                missing_key=name,
                context_keys=tuple(context.values.keys()),
            )
        resolved[name] = default

    if async_coros:
        # Run all AwaitPromptDepends concurrently; first exception cancels rest.
        results = await asyncio.gather(*async_coros)
        for name, result in zip(async_names, results):
            resolved[name] = result

    return resolved



class _PromptString:
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
        # Guard: docstring functions must return None (ADR 0006 D2).
        if self._compiled is not None and source_candidate is not None:
            raise PromptRenderError(
                f"Docstring-based promptstring {self.__name__!r} returned a non-None value "
                f"at render time. Annotate with -> Template or -> PromptSource for dynamic sources."
            )
        if source_candidate is None:
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
            "Promptstring source selector must return None, str, Template, or PromptSource, "
            f"got {type(source_candidate)!r}"
        )

    async def _render_messages_impl(
        self, ctx: PromptContext
    ) -> list[PromptMessage]:
        """Core rendering logic shared by render() and render_messages()."""
        resolved = await _resolve_dependencies(self._fn, ctx)
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
                unused_params = sorted(name for name in resolved if name not in placeholders)
                if unused_params:
                    raise PromptUnusedParameterError(
                        "Resolved prompt parameters were not used by the selected source: "
                        + ", ".join(unused_params),
                        unused_parameters=tuple(unused_params),
                        resolved_keys=tuple(sorted(resolved.keys())),
                    )
            content = _render_static(tpl, resolved)
            provenance = None
        elif isinstance(source, Template):
            tpl = source
            placeholders = _placeholders_from_template(tpl)
            # Detect whether this Template came from parse_docstring_template (has _MISSING
            # sentinel values) or from a real t-string (values already resolved).
            is_parse_derived = any(
                i.value is _MISSING for i in tpl.interpolations
            )
            if is_parse_derived:
                # parse_docstring_template path: render via expression→resolved lookup.
                if missing := sorted(name for name in placeholders if name not in resolved):
                    raise PromptRenderError(
                        f"Missing prompt values for placeholders: {', '.join(missing)}"
                    )
                if self._strict:
                    unused_params = sorted(name for name in resolved if name not in placeholders)
                    if unused_params:
                        raise PromptUnusedParameterError(
                            "Resolved prompt parameters were not used by the selected source: "
                            + ", ".join(unused_params),
                            unused_parameters=tuple(unused_params),
                            resolved_keys=tuple(sorted(resolved.keys())),
                        )
                content = _render_static(tpl, resolved)
            else:
                # T-string-derived dynamic Template: values already resolved.
                if self._strict:
                    unused_params = sorted(name for name in resolved if name not in placeholders)
                    if unused_params:
                        raise PromptUnusedParameterError(
                            "Resolved prompt parameters were not used by the selected source: "
                            + ", ".join(unused_params),
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


class _PromptStringGenerator:
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

    @property
    def placeholders(self) -> frozenset[str]:
        """Always empty for generator promptstrings (no static template to parse)."""
        return frozenset()

    async def _render_messages_impl(self, ctx: PromptContext) -> list[PromptMessage]:
        """Core rendering logic shared by render() and render_messages()."""
        resolved = await _resolve_dependencies(self._fn, ctx)
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
            unused_params = sorted(name for name in resolved if name not in used)
            if unused_params:
                raise PromptUnreferencedParameterError(
                    "Resolved prompt parameters were not consumed on this generator render path: "
                    + ", ".join(unused_params),
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


# Default singleton — module-level decorators are stable bindings to its methods.
_default = Promptstrings()
promptstring = _default.promptstring
promptstring_generator = _default.promptstring_generator
