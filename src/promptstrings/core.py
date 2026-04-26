"""Core implementation of the promptstrings prompt-template library."""

from __future__ import annotations

import inspect
import sys
import textwrap
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass, field
from string import Formatter
from typing import Any, overload


class PromptRenderError(RuntimeError):
    """Base class for all prompt render-time failures."""

    pass


class PromptCompileError(PromptRenderError):
    """Raised at decoration time when a template cannot be compiled."""

    pass


class PromptStrictnessError(PromptRenderError):
    """Raised when a strict-mode check fails during rendering."""

    pass


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
            raise PromptRenderError(f"Missing prompt context value: {key}")
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
                f"Format specs are not supported in promptstrings (prompt: {prompt_name!r})"
            )
        if conversion:
            raise PromptCompileError(
                f"Conversions are not supported in promptstrings (prompt: {prompt_name!r})"
            )
        parts.append((literal, None))
        if field_name is None:
            continue
        if not field_name.isidentifier():
            raise PromptCompileError(
                f"Promptstring placeholders must use the minimal {{identifier}} grammar "
                f"(got {field_name!r}, prompt: {prompt_name!r})"
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
    optimize_note = (
        " (docstrings are stripped by python -OO; run without -OO)"
        if sys.flags.optimize >= 2
        else ""
    )
    raise PromptCompileError(
        f"Promptstring {prompt_name!r} has no docstring and its return annotation does not "
        f"prove a PromptSource is returned.{optimize_note}"
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
            raise PromptRenderError(f"Unable to resolve prompt parameter: {name}")
        resolved[name] = default
    return resolved, awaited_dependency_count


def _normalize_source(docstring: str | None) -> str:
    """Normalize a docstring into a trimmed prompt template string."""
    if not docstring:
        raise PromptCompileError(
            "Promptstring docstring is required when no string source is returned"
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
            return PromptSource(content=_normalize_source(self.__doc__)), True
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
                raise PromptStrictnessError(
                    "Resolved prompt parameters were not used by the selected source: "
                    + ", ".join(unused_params)
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
                raise PromptStrictnessError(
                    "Resolved prompt parameters were not used by the selected source: "
                    + ", ".join(unused_params)
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
                raise PromptStrictnessError(
                    "Resolved prompt parameters were not consumed on this generator render path: "
                    + ", ".join(unused_params)
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
