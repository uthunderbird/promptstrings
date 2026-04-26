from __future__ import annotations

import asyncio

import pytest

from promptstrings import (
    AwaitPromptDepends,
    PromptContext,
    PromptDepends,
    PromptMessage,
    PromptRenderError,
    PromptSource,
    PromptSourceProvenance,
    PromptStrictnessError,
    Role,
    promptstring,
    promptstring_generator,
)


def test_promptstring_uses_docstring_when_function_returns_none() -> None:
    @promptstring
    def prompt(name=PromptDepends(lambda ctx: ctx.require("name"))):
        """
        Hello, {name}!
        """

    rendered = asyncio.run(prompt.render(PromptContext({"name": "Ada"})))
    assert rendered == "Hello, Ada!"


def test_promptstring_uses_returned_string_when_function_returns_str() -> None:
    @promptstring
    def prompt(name=PromptDepends(lambda ctx: ctx.require("name"))):
        """
        ignored {name}
        """
        return "Override says hi to {name}."

    rendered = asyncio.run(prompt.render(PromptContext({"name": "Ada"})))
    assert rendered == "Override says hi to Ada."


def test_promptstring_supports_prompt_source_provenance_on_messages() -> None:
    provenance = PromptSourceProvenance(
        source_id="langfuse.session.system",
        version="2026-03-20",
        hash="sha256:abc123",
        provider_name="langfuse",
    )

    @promptstring
    def prompt(name=PromptDepends(lambda ctx: ctx.require("name"))):
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
    @promptstring
    def prompt(
        name=PromptDepends(lambda ctx: ctx.require("name")), unused=PromptDepends(lambda ctx: "x")
    ):
        """
        Hello, {name}!
        """

    with pytest.raises(PromptStrictnessError):
        asyncio.run(prompt.render(PromptContext({"name": "Ada"})))


def test_promptstring_rejects_non_string_non_none_source_override() -> None:
    @promptstring
    def prompt(name=PromptDepends(lambda ctx: ctx.require("name"))):
        """
        Hello, {name}!
        """
        return 123

    with pytest.raises(PromptRenderError):
        asyncio.run(prompt.render(PromptContext({"name": "Ada"})))


def test_promptstring_rejects_non_minimal_placeholder_grammar() -> None:
    @promptstring(strict=False)
    def prompt(name=PromptDepends(lambda ctx: ctx.require("name"))):
        """
        Hello, {user.name}!
        """

    with pytest.raises(PromptRenderError):
        asyncio.run(prompt.render(PromptContext({"name": "Ada"})))


def test_promptstring_generator_normalizes_roles_and_messages() -> None:
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


def test_promptstring_allows_single_awaited_dependency() -> None:
    async def load_name(_ctx: PromptContext) -> str:
        return "Ada"

    @promptstring
    def prompt(name=AwaitPromptDepends(load_name)):
        """
        Hello, {name}!
        """

    rendered = asyncio.run(prompt.render())
    assert rendered == "Hello, Ada!"


def test_promptstring_rejects_multiple_awaited_dependencies() -> None:
    async def load_name(_ctx: PromptContext) -> str:
        return "Ada"

    @promptstring
    def prompt(
        first=AwaitPromptDepends(load_name),
        second=AwaitPromptDepends(load_name),
    ):
        """
        Hello, {first} and {second}!
        """

    with pytest.raises(PromptRenderError):
        asyncio.run(prompt.render())
