"""Core implementation of the promptstrings prompt-template library."""

from __future__ import annotations

import inspect
import sys
import textwrap
from collections.abc import Awaitable, Callable, Iterable, Mapping
from dataclasses import dataclass, field
from string import Formatter
from typing import Any, Literal, Protocol, overload, runtime_checkable


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

    cause: Literal["missing_template", "format_spec", "conversion", "non_identifier_placeholder"]
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
            "missing_template", "format_spec", "conversion", "non_identifier_placeholder"
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
        unused_parameters: tuple[str, ...],
        resolved_keys: tuple[str, ...],
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
        unreferenced_parameters: tuple[str, ...],
        resolved_keys: tuple[str, ...],
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
    """Immutable container for values used to resolve prompt parameters."""

    values: dict[str, Any] = field(default_factory=dict)

    def get(self, key: str, default: Any = None) -> Any:
        """Return the value for key, or default if absent."""
        return self.values.get(key, default)

    def require(self, key: str) -> Any:
        """Return the value for key, raising PromptRenderError if absent."""
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


@dataclass(frozen=True)
class _CompiledTemplate:
    """Parsed, immutable representation of a prompt template."""

    parts: tuple[tuple[str, str | None], ...]
    placeholders: frozenset[str]

    def render(self, values: dict[str, Any]) -> str:
        """Substitute values into the template and return the rendered string."""
        chunks: list[str] = []
        for literal, field_name in self.parts:
            chunks.append(literal)
            if field_name is not None:
                chunks.append(str(values[field_name]))
        return "".join(chunks)


async def _maybe_await(value: Any) -> Any:
    """Await value if it is awaitable; otherwise return it directly."""
    if inspect.isawaitable(value):
        return await value
    return value


def _compile_template(source: str, *, prompt_name: str = "<unknown>") -> _CompiledTemplate:
    """Parse a prompt template string into a _CompiledTemplate.

    Raises PromptCompileError for unsupported grammar (format specs, conversions,
    non-identifier placeholder names).
    """
    formatter = Formatter()
    parts: list[tuple[str, str | None]] = []
    placeholders: set[str] = set()
    for literal, field_name, format_spec, conversion in formatter.parse(source):
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
        parts.append((literal, None))
        if field_name is None:
            continue
        if not field_name.isidentifier():
            raise PromptCompileError(
                f"Promptstring placeholders must use the minimal {{identifier}} grammar "
                f"(got {field_name!r}, prompt: {prompt_name!r})",
                prompt_name=prompt_name,
                cause="non_identifier_placeholder",
                placeholder=field_name,
                optimize_mode_active=sys.flags.optimize >= 2,
            )
        placeholders.add(field_name)
        parts.append(("", field_name))
    return _CompiledTemplate(parts=tuple(parts), placeholders=frozenset(placeholders))


def _has_prompt_source_return_annotation(fn: Callable[..., Any]) -> bool:
    """Return True if fn's return annotation proves it returns a PromptSource."""
    try:
        hints = fn.__annotations__
    except AttributeError:
        return False
    return_hint = hints.get("return")
    if return_hint is None:
        return False
    # Accept the class object itself or the string 'PromptSource'
    return return_hint is PromptSource or return_hint == "PromptSource"


def _compile_at_decoration(
    fn: Callable[..., Any],
    prompt_name: str,
) -> _CompiledTemplate | None:
    """Attempt to compile a template at decoration time.

    Returns a _CompiledTemplate when the function has a docstring-based template.
    Returns None when the function is dynamic-source (PromptSource return annotation).
    Raises PromptCompileError immediately when neither condition holds.
    """
    docstring = getattr(fn, "__doc__", None)
    if docstring:
        normalized = textwrap.dedent(docstring).strip()
        return _compile_template(normalized, prompt_name=prompt_name)

    # No docstring — check if the function proves it returns a PromptSource dynamically.
    if _has_prompt_source_return_annotation(fn):
        # Dynamic source: placeholders cannot be known until render time.
        return None

    # Neither docstring nor PromptSource annotation: fail immediately.
    optimize_active = sys.flags.optimize >= 2
    optimize_note = " (docstrings are stripped by python -OO; run without -OO)" if optimize_active else ""
    raise PromptCompileError(
        f"Promptstring {prompt_name!r} has no docstring and its return annotation does not "
        f"prove a PromptSource is returned.{optimize_note}",
        prompt_name=prompt_name,
        cause="missing_template",
        placeholder=None,
        optimize_mode_active=optimize_active,
    )


async def _resolve_dependencies(
    fn: Callable[..., Any],
    context: PromptContext,
) -> tuple[dict[str, Any], int]:
    """Resolve all declared parameters for fn using the given context.

    Returns (resolved_values, awaited_dependency_count).
    """
    signature = inspect.signature(fn)
    resolved: dict[str, Any] = {}
    awaited_dependency_count = 0
    for name, parameter in signature.parameters.items():
        default = parameter.default
        if isinstance(default, (PromptDepends, AwaitPromptDepends)):
            resolved[name] = await _maybe_await(default.resolver(context))
            if isinstance(default, AwaitPromptDepends):
                awaited_dependency_count += 1
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
    return resolved, awaited_dependency_count


def _normalize_source(docstring: str | None, *, prompt_name: str = "<unknown>") -> str:
    """Normalize a docstring into a trimmed prompt template string."""
    if not docstring:
        raise PromptCompileError(
            f"Promptstring {prompt_name!r} docstring is required when no string source is returned",
            prompt_name=prompt_name,
            cause="missing_template",
            optimize_mode_active=sys.flags.optimize >= 2,
        )
    return textwrap.dedent(docstring).strip()


class _PromptString:
    """Compiled promptstring backed by a function body or docstring template."""

    def __init__(self, fn: Callable[..., Any], *, strict: bool = True) -> None:
        """Initialize and eagerly compile the template when possible."""
        self._fn = fn
        self._strict = strict
        self.__name__ = getattr(fn, "__name__", "promptstring")
        self.__doc__ = getattr(fn, "__doc__", None)
        # Eagerly compile template at decoration time (ADR 0001 Promise 7 and 8).
        # _compiled is None for dynamic-source functions (PromptSource annotation).
        self._compiled: _CompiledTemplate | None = _compile_at_decoration(fn, self.__name__)
        # declared_parameters: immutable at decoration time (ADR 0001 Promise 2).
        self.declared_parameters: Mapping[str, inspect.Parameter] = dict(
            inspect.signature(fn).parameters
        )

    @property
    def placeholders(self) -> frozenset[str]:
        """Placeholder names declared in the docstring template.

        Returns frozenset() for dynamic-source functions whose template is not
        known until render time (ADR 0001 non-promise 10).
        """
        if self._compiled is not None:
            return self._compiled.placeholders
        return frozenset()

    async def _resolve_source(self, resolved: dict[str, Any]) -> tuple[PromptSource, bool]:
        """Call the decorated function and normalize its return value to a PromptSource.

        Returns (source, is_docstring_derived). When is_docstring_derived is True,
        the eagerly-compiled template can be reused; otherwise the source content
        must be compiled at render time.
        """
        source_candidate = await _maybe_await(self._fn(**resolved))
        if source_candidate is None:
            return PromptSource(content=_normalize_source(self.__doc__, prompt_name=self.__name__)), True
        if isinstance(source_candidate, str):
            return PromptSource(content=source_candidate), False
        if isinstance(source_candidate, PromptSource):
            return source_candidate, False
        raise PromptRenderError(
            "Promptstring source selector must return None, str, or PromptSource, "
            f"got {type(source_candidate)!r}"
        )

    def _get_compiled(self, source: PromptSource, *, is_docstring_derived: bool) -> _CompiledTemplate:
        """Return the cached compiled template for docstring sources, or compile dynamically."""
        if is_docstring_derived and self._compiled is not None:
            return self._compiled
        # Dynamic source (returned string or PromptSource): compile at render time.
        return _compile_template(source.content, prompt_name=self.__name__)

    async def render(self, context: PromptContext | None = None) -> str:
        """Render the prompt to a single string."""
        ctx = context or PromptContext()
        resolved, awaited_dependency_count = await _resolve_dependencies(self._fn, ctx)
        if awaited_dependency_count > 1:
            raise PromptRenderError(
                "Promptstring render currently allows at most one AwaitPromptDepends dependency"
            )
        source, is_docstring_derived = await self._resolve_source(resolved)
        compiled = self._get_compiled(source, is_docstring_derived=is_docstring_derived)
        if missing := sorted(name for name in compiled.placeholders if name not in resolved):
            raise PromptRenderError(f"Missing prompt values for placeholders: {', '.join(missing)}")
        if self._strict:
            unused_params = sorted(name for name in resolved if name not in compiled.placeholders)
            if unused_params:
                raise PromptUnusedParameterError(
                    "Resolved prompt parameters were not used by the selected source: "
                    + ", ".join(unused_params),
                    unused_parameters=tuple(unused_params),
                    resolved_keys=tuple(sorted(resolved.keys())),
                )
        return compiled.render(resolved)

    async def render_messages(self, context: PromptContext | None = None) -> list[PromptMessage]:
        """Render the prompt to a list of PromptMessage objects."""
        ctx = context or PromptContext()
        resolved, awaited_dependency_count = await _resolve_dependencies(self._fn, ctx)
        if awaited_dependency_count > 1:
            raise PromptRenderError(
                "Promptstring render currently allows at most one AwaitPromptDepends dependency"
            )
        source, is_docstring_derived = await self._resolve_source(resolved)
        compiled = self._get_compiled(source, is_docstring_derived=is_docstring_derived)
        if missing := sorted(name for name in compiled.placeholders if name not in resolved):
            raise PromptRenderError(f"Missing prompt values for placeholders: {', '.join(missing)}")
        if self._strict:
            unused_params = sorted(name for name in resolved if name not in compiled.placeholders)
            if unused_params:
                raise PromptUnusedParameterError(
                    "Resolved prompt parameters were not used by the selected source: "
                    + ", ".join(unused_params),
                    unused_parameters=tuple(unused_params),
                    resolved_keys=tuple(sorted(resolved.keys())),
                )
        return [
            PromptMessage(
                role="system",
                content=compiled.render(resolved),
                source=source.provenance,
            )
        ]


class _PromptStringGenerator:
    """Generator-based promptstring for multi-message prompts."""

    def __init__(self, fn: Callable[..., Any], *, strict: bool = False) -> None:
        """Initialize the generator promptstring."""
        self._fn = fn
        self._strict = strict
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

    async def render_messages(self, context: PromptContext | None = None) -> list[PromptMessage]:
        """Render the generator to a list of PromptMessage objects."""
        ctx = context or PromptContext()
        resolved, awaited_dependency_count = await _resolve_dependencies(self._fn, ctx)
        if awaited_dependency_count > 1:
            raise PromptRenderError(
                "Promptstring render currently allows at most one AwaitPromptDepends dependency"
            )
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
            raise PromptRenderError(
                f"Unsupported promptstring generator yield type: {type(item)!r}"
            )

        flush()

        if self._strict:
            used = {
                name
                for name, value in resolved.items()
                if str(value) in "\n".join(m.content for m in messages)
            }
            unused_params = sorted(name for name in resolved if name not in used)
            if unused_params:
                raise PromptUnreferencedParameterError(
                    "Resolved prompt parameters were not consumed on this generator render path: "
                    + ", ".join(unused_params),
                    unreferenced_parameters=tuple(unused_params),
                    resolved_keys=tuple(sorted(resolved.keys())),
                )
        return messages

    async def render(self, context: PromptContext | None = None) -> str:
        """Render the generator to a single joined string."""
        messages = await self.render_messages(context)
        return "\n\n".join(message.content for message in messages)


@overload
def promptstring(
    fn: Callable[..., Any],
    *,
    strict: bool = True,
) -> _PromptString: ...


@overload
def promptstring(
    fn: None = None,
    *,
    strict: bool = True,
) -> Callable[[Callable[..., Any]], _PromptString]: ...


def promptstring(
    fn: Callable[..., Any] | None = None,
    *,
    strict: bool = True,
) -> _PromptString | Callable[[Callable[..., Any]], _PromptString]:
    """Decorator that creates a PromptString from a function with a docstring template."""
    if fn is None:
        return lambda wrapped: _PromptString(wrapped, strict=strict)
    return _PromptString(fn, strict=strict)


@overload
def promptstring_generator(
    fn: Callable[..., Iterable[Any]],
    *,
    strict: bool = False,
) -> _PromptStringGenerator: ...


@overload
def promptstring_generator(
    fn: None = None,
    *,
    strict: bool = False,
) -> Callable[[Callable[..., Iterable[Any]]], _PromptStringGenerator]: ...


def promptstring_generator(
    fn: Callable[..., Iterable[Any]] | None = None,
    *,
    strict: bool = False,
) -> _PromptStringGenerator | Callable[[Callable[..., Iterable[Any]]], _PromptStringGenerator]:
    """Decorator that creates a PromptStringGenerator from a generator function."""
    if fn is None:
        return lambda wrapped: _PromptStringGenerator(wrapped, strict=strict)
    return _PromptStringGenerator(fn, strict=strict)
