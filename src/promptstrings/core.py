from __future__ import annotations

import inspect
import textwrap
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass, field
from string import Formatter
from typing import Any, overload


class PromptRenderError(RuntimeError):
    pass


class PromptCompileError(PromptRenderError):
    pass


class PromptStrictnessError(PromptRenderError):
    pass


@dataclass(frozen=True)
class PromptMessage:
    role: str
    content: str
    source: PromptSourceProvenance | None = None


@dataclass(frozen=True)
class Role:
    name: str


@dataclass(frozen=True)
class PromptSourceProvenance:
    source_id: str | None = None
    version: str | None = None
    hash: str | None = None
    provider_name: str | None = None

    def as_metadata(self) -> dict[str, str]:
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
    content: str
    provenance: PromptSourceProvenance | None = None


@dataclass(frozen=True)
class PromptContext:
    values: dict[str, Any] = field(default_factory=dict)

    def get(self, key: str, default: Any = None) -> Any:
        return self.values.get(key, default)

    def require(self, key: str) -> Any:
        if key not in self.values:
            raise PromptRenderError(f"Missing prompt context value: {key}")
        return self.values[key]


Resolver = Callable[[PromptContext], Any] | Callable[[PromptContext], Awaitable[Any]]


@dataclass(frozen=True)
class PromptDepends:
    resolver: Resolver


@dataclass(frozen=True)
class AwaitPromptDepends:
    resolver: Resolver


@dataclass(frozen=True)
class _CompiledTemplate:
    parts: tuple[tuple[str, str | None], ...]
    placeholders: frozenset[str]

    def render(self, values: dict[str, Any]) -> str:
        chunks: list[str] = []
        for literal, field_name in self.parts:
            chunks.append(literal)
            if field_name is not None:
                chunks.append(str(values[field_name]))
        return "".join(chunks)


async def _maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


def _compile_template(source: str) -> _CompiledTemplate:
    formatter = Formatter()
    parts: list[tuple[str, str | None]] = []
    placeholders: set[str] = set()
    for literal, field_name, format_spec, conversion in formatter.parse(source):
        if format_spec:
            raise PromptCompileError("Format specs are not supported in promptstrings")
        if conversion:
            raise PromptCompileError("Conversions are not supported in promptstrings")
        parts.append((literal, None))
        if field_name is None:
            continue
        if not field_name.isidentifier():
            raise PromptCompileError(
                "Promptstring placeholders must use the minimal `{identifier}` grammar"
            )
        placeholders.add(field_name)
        parts.append(("", field_name))
    return _CompiledTemplate(parts=tuple(parts), placeholders=frozenset(placeholders))


async def _resolve_dependencies(
    fn: Callable[..., Any],
    context: PromptContext,
) -> tuple[dict[str, Any], int]:
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
        if default is inspect._empty:
            raise PromptRenderError(f"Unable to resolve prompt parameter: {name}")
        resolved[name] = default
    return resolved, awaited_dependency_count


def _normalize_source(docstring: str | None) -> str:
    if not docstring:
        raise PromptCompileError(
            "Promptstring docstring is required when no string source is returned"
        )
    return textwrap.dedent(docstring).strip()


class _PromptString:
    def __init__(self, fn: Callable[..., Any], *, strict: bool = True) -> None:
        self._fn = fn
        self._strict = strict
        self.__name__ = getattr(fn, "__name__", "promptstring")
        self.__doc__ = getattr(fn, "__doc__", None)

    async def _resolve_source(self, resolved: dict[str, Any]) -> PromptSource:
        source_candidate = await _maybe_await(self._fn(**resolved))
        if source_candidate is None:
            return PromptSource(content=_normalize_source(self.__doc__))
        if isinstance(source_candidate, str):
            return PromptSource(content=source_candidate)
        if isinstance(source_candidate, PromptSource):
            return source_candidate
        raise PromptRenderError(
            "Promptstring source selector must return None, str, or PromptSource, "
            f"got {type(source_candidate)!r}"
        )

    async def render(self, context: PromptContext | None = None) -> str:
        ctx = context or PromptContext()
        resolved, awaited_dependency_count = await _resolve_dependencies(self._fn, ctx)
        if awaited_dependency_count > 1:
            raise PromptRenderError(
                "Promptstring render currently allows at most one AwaitPromptDepends dependency"
            )
        source = await self._resolve_source(resolved)
        compiled = _compile_template(source.content)
        if missing := sorted(name for name in compiled.placeholders if name not in resolved):
            raise PromptRenderError(f"Missing prompt values for placeholders: {', '.join(missing)}")
        if self._strict:
            extras = sorted(name for name in resolved if name not in compiled.placeholders)
            if extras:
                raise PromptStrictnessError(
                    "Resolved prompt parameters were not used by the selected source: "
                    + ", ".join(extras)
                )
        return compiled.render(resolved)

    async def render_messages(self, context: PromptContext | None = None) -> list[PromptMessage]:
        ctx = context or PromptContext()
        resolved, awaited_dependency_count = await _resolve_dependencies(self._fn, ctx)
        if awaited_dependency_count > 1:
            raise PromptRenderError(
                "Promptstring render currently allows at most one AwaitPromptDepends dependency"
            )
        source = await self._resolve_source(resolved)
        compiled = _compile_template(source.content)
        if missing := sorted(name for name in compiled.placeholders if name not in resolved):
            raise PromptRenderError(f"Missing prompt values for placeholders: {', '.join(missing)}")
        if self._strict:
            extras = sorted(name for name in resolved if name not in compiled.placeholders)
            if extras:
                raise PromptStrictnessError(
                    "Resolved prompt parameters were not used by the selected source: "
                    + ", ".join(extras)
                )
        return [
            PromptMessage(
                role="system",
                content=compiled.render(resolved),
                source=source.provenance,
            )
        ]


class _PromptStringGenerator:
    def __init__(self, fn: Callable[..., Any], *, strict: bool = False) -> None:
        self._fn = fn
        self._strict = strict
        self.__name__ = getattr(fn, "__name__", "promptstring_generator")
        self.__doc__ = getattr(fn, "__doc__", None)

    async def render_messages(self, context: PromptContext | None = None) -> list[PromptMessage]:
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
            extras = sorted(name for name in resolved if name not in used)
            if extras:
                raise PromptStrictnessError(
                    "Resolved prompt parameters were not consumed on this generator render path: "
                    + ", ".join(extras)
                )
        return messages

    async def render(self, context: PromptContext | None = None) -> str:
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
    if fn is None:
        return lambda wrapped: _PromptStringGenerator(wrapped, strict=strict)
    return _PromptStringGenerator(fn, strict=strict)
