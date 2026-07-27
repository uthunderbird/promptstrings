"""Public data types, the Promptstring Protocol, and the private _PromptObject marker."""

from __future__ import annotations

import hashlib
import inspect
import os
import pathlib
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from .errors import PromptRenderError


class _PromptObject:
    """Private marker: an object this library produced that has no rendered form.

    Not public API; do not subclass outside this package. The D3 guard of
    ADR 0011 must fire for this library's own prompt objects and must NOT
    fire for third-party implementations of the `Promptstring` Protocol, so
    the check has to be nominal. This base is the minimal nominal marker,
    and it lets the guard live in `templates` without importing the engines
    (ADR 0012 D8).
    """

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

    response_schema: Any
    """Return annotation of the underlying function, or None for internal types (ADR 0009).

    Pass to LLM framework structured-output arguments (e.g. instructor's
    response_model, OpenAI's response_format). None when the prompt has no
    user-defined return type (-> None, -> ..., -> Template, -> PromptSource).
    """

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


def provenance_from_file(
    path: str | os.PathLike[str],
    *,
    source_id: str | None = None,
    version: str | None = None,
    provider_name: str | None = None,
) -> PromptSourceProvenance:
    """Derive provenance from a template file on disk (ADR 0012 D4).

    Provenance is carried only by prompts that return a ``PromptSource`` — the
    path taken when an external engine renders the text. That is also the path
    where the template lives in a file, so without this helper every such prompt
    needs a hand-written ``PromptSourceProvenance`` and most lose provenance
    instead.

    ``source_id`` defaults to the given path in POSIX form, **not** resolved to
    an absolute path. ``str(path)`` would yield backslash separators on Windows,
    so the same template in the same repository would carry different provenance
    on different machines, defeating the only property this helper provides.

    That default only works if the caller passes a stable, relative path. Code
    that locates its templates from ``__file__`` necessarily has an absolute
    path, which is equally machine-specific — so pass ``source_id`` explicitly
    to record a repository-relative identity while reading from wherever the
    file actually is::

        provenance_from_file(
            HERE / "prompts" / "system.jinja2",
            source_id="prompts/system.jinja2",
        )

    ``hash`` is ``sha256`` over the file's raw bytes, with no newline
    normalisation: normalising would hide a real difference in what was sent to
    the model. A repository checked out with ``core.autocrlf=true`` therefore
    hashes differently from the same commit on Linux.

    ``version`` is yours — the library assigns none. Pass a git SHA, a registry
    version, a date, or nothing.

    The path is caller-supplied and caller-trusted: this function does not
    validate it, reads the file whole in order to hash it, and follows symlinks.
    Call it at decoration or start-up time, not per render.
    """
    digest = hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()
    return PromptSourceProvenance(
        source_id=source_id if source_id is not None else pathlib.PurePath(path).as_posix(),
        version=version,
        hash=f"sha256:{digest}",
        provider_name=provider_name,
    )


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
