"""Tests for the promptstrings library.

Covers ADR 0001–0004 promises and DX rubric R1–R16.
"""

from __future__ import annotations

import asyncio

import pytest

from promptstrings import (
    AwaitPromptDepends,
    PromptCompileError,
    PromptContext,
    PromptDepends,
    PromptMessage,
    PromptRenderError,
    PromptSource,
    PromptSourceProvenance,
    PromptStrictnessError,
    Promptstring,
    Role,
    promptstring,
    promptstring_generator,
)

# ---------------------------------------------------------------------------
# Basic rendering
# ---------------------------------------------------------------------------


def test_promptstring_uses_docstring_when_function_returns_none() -> None:
    """Docstring is used as the template when the function returns None."""

    @promptstring
    def prompt(name=PromptDepends(lambda ctx: ctx.require("name"))):
        """Hello, {name}!"""

    rendered = asyncio.run(prompt.render(PromptContext({"name": "Ada"})))
    assert rendered == "Hello, Ada!"


def test_promptstring_uses_returned_string_when_function_returns_str() -> None:
    """A returned string overrides the docstring template."""

    @promptstring
    def prompt(name=PromptDepends(lambda ctx: ctx.require("name"))):
        """ignored {name}"""
        return "Override says hi to {name}."

    rendered = asyncio.run(prompt.render(PromptContext({"name": "Ada"})))
    assert rendered == "Override says hi to Ada."


def test_promptstring_supports_prompt_source_provenance_on_messages() -> None:
    """PromptSourceProvenance flows through to each PromptMessage unchanged."""
    provenance = PromptSourceProvenance(
        source_id="langfuse.session.system",
        version="2026-03-20",
        hash="sha256:abc123",
        provider_name="langfuse",
    )

    @promptstring
    def prompt(name=PromptDepends(lambda ctx: ctx.require("name"))) -> PromptSource:
        return PromptSource(
            content="External source says hi to {name}.",
            provenance=provenance,
        )

    messages = asyncio.run(prompt.render_messages(PromptContext({"name": "Ada"})))
    assert messages == [
        PromptMessage(
            role="system",
            content="External source says hi to Ada.",
            source=provenance,
        )
    ]
    assert messages[0].source is not None
    assert messages[0].source.as_metadata() == {
        "source_id": "langfuse.session.system",
        "version": "2026-03-20",
        "hash": "sha256:abc123",
        "provider_name": "langfuse",
    }


def test_promptstring_strict_mode_rejects_unused_resolved_params() -> None:
    """Strict mode raises PromptStrictnessError for resolved but unused parameters."""

    @promptstring
    def prompt(
        name=PromptDepends(lambda ctx: ctx.require("name")),
        unused=PromptDepends(lambda ctx: "x"),
    ):
        """Hello, {name}!"""

    with pytest.raises(PromptStrictnessError):
        asyncio.run(prompt.render(PromptContext({"name": "Ada"})))


def test_promptstring_rejects_non_string_non_none_source_override() -> None:
    """Returning an unexpected type from the decorated function raises PromptRenderError."""

    @promptstring
    def prompt(name=PromptDepends(lambda ctx: ctx.require("name"))):
        """Hello, {name}!"""
        return 123

    with pytest.raises(PromptRenderError):
        asyncio.run(prompt.render(PromptContext({"name": "Ada"})))


# ---------------------------------------------------------------------------
# Compilation and decoration-time checks (ADR 0001 Promises 7 and 8 / R8)
# ---------------------------------------------------------------------------


def test_promptstring_rejects_non_minimal_placeholder_grammar_at_decoration_time() -> None:
    """Non-identifier placeholders raise PromptCompileError at decoration time (not render time).

    This is R8: errors surface at module import, not buried inside render handlers.
    """
    with pytest.raises(PromptCompileError):

        @promptstring(strict=False)
        def prompt(name=PromptDepends(lambda ctx: ctx.require("name"))):
            """Hello, {user.name}!"""


def test_promptstring_raises_at_decoration_time_when_no_docstring_and_no_source_annotation() -> None:
    """Decorating a function with no docstring and no PromptSource annotation raises immediately.

    This is R8: the error is caught at decoration time, before any render call.
    """
    with pytest.raises(PromptCompileError):

        @promptstring
        def prompt():  # type: ignore[empty-body]
            pass


def test_promptstring_accepts_no_docstring_when_return_annotation_is_prompt_source() -> None:
    """Decorating a function annotated to return PromptSource succeeds even without a docstring.

    placeholders is frozenset() until render time (ADR 0001 non-promise 10).
    """

    @promptstring
    def prompt(name=PromptDepends(lambda ctx: ctx.require("name"))) -> PromptSource:
        return PromptSource(content="Hello, {name}!")

    # placeholders is empty because the template is only known at render time.
    assert prompt.placeholders == frozenset()
    rendered = asyncio.run(prompt.render(PromptContext({"name": "Ada"})))
    assert rendered == "Hello, Ada!"


def test_promptstring_placeholders_available_immediately_after_decoration() -> None:
    """placeholders is populated at decoration time for docstring-based templates (ADR 0001 P7)."""

    @promptstring
    def prompt(name: str, topic: str) -> None:
        """Tell me about {topic} from the perspective of {name}."""

    assert prompt.placeholders == frozenset({"topic", "name"})


# ---------------------------------------------------------------------------
# Promptstring Protocol (ADR 0001 Promise 2 / R3 / R9)
# ---------------------------------------------------------------------------


def test_promptstring_protocol_is_runtime_checkable() -> None:
    """Promptstring is @runtime_checkable, enabling isinstance checks (R9)."""

    @promptstring
    def ps(name: str) -> None:
        """Hello, {name}."""

    assert isinstance(ps, Promptstring)


def test_promptstring_generator_satisfies_protocol() -> None:
    """_PromptStringGenerator also satisfies the Promptstring Protocol (R9)."""

    @promptstring_generator
    def psg(topic: str):
        yield f"Tell me about {topic}."

    assert isinstance(psg, Promptstring)


def test_promptstring_placeholders_and_declared_parameters_require_no_await() -> None:
    """placeholders and declared_parameters are accessible without rendering (R3)."""

    @promptstring
    def ps(name: str, topic: str) -> None:
        """Tell me about {topic}, {name}."""

    # Both attributes are synchronously accessible.
    assert ps.placeholders == frozenset({"topic", "name"})
    assert set(ps.declared_parameters.keys()) == {"name", "topic"}


def test_promptstring_generator_declared_parameters_accessible_without_rendering() -> None:
    """declared_parameters is available immediately after decoration for generators (R3)."""
    import inspect

    @promptstring_generator
    def psg(user: str, topic: str):
        yield Role("system")
        yield f"You are an assistant discussing {topic}."
        yield Role("user")
        yield f"Hi, I am {user}."

    params = psg.declared_parameters
    assert set(params.keys()) == {"user", "topic"}
    # Values are inspect.Parameter objects (ADR 0001 Promise 2).
    assert all(isinstance(p, inspect.Parameter) for p in params.values())


# ---------------------------------------------------------------------------
# Generator form
# ---------------------------------------------------------------------------


def test_promptstring_generator_normalizes_roles_and_messages() -> None:
    """Generator yields are assembled into role-segmented PromptMessage objects."""

    @promptstring_generator
    def prompt(name=PromptDepends(lambda ctx: ctx.require("name"))):
        yield "First line"
        yield Role("user")
        yield f"Hi {name}"
        yield PromptMessage(role="assistant", content="Done")

    messages = asyncio.run(prompt.render_messages(PromptContext({"name": "Ada"})))
    assert messages == [
        PromptMessage(role="system", content="First line"),
        PromptMessage(role="user", content="Hi Ada"),
        PromptMessage(role="assistant", content="Done"),
    ]


# ---------------------------------------------------------------------------
# Async dependency injection
# ---------------------------------------------------------------------------


def test_promptstring_allows_single_awaited_dependency() -> None:
    """A single AwaitPromptDepends resolver is awaited and its value injected."""

    async def load_name(_ctx: PromptContext) -> str:
        return "Ada"

    @promptstring
    def prompt(name=AwaitPromptDepends(load_name)):
        """Hello, {name}!"""

    rendered = asyncio.run(prompt.render())
    assert rendered == "Hello, Ada!"


def test_promptstring_rejects_multiple_awaited_dependencies() -> None:
    """Multiple AwaitPromptDepends currently raises (at-most-one guard still in place)."""

    async def load_name(_ctx: PromptContext) -> str:
        return "Ada"

    @promptstring
    def prompt(
        first=AwaitPromptDepends(load_name),
        second=AwaitPromptDepends(load_name),
    ):
        """Hello, {first} and {second}!"""

    with pytest.raises(PromptRenderError):
        asyncio.run(prompt.render())
