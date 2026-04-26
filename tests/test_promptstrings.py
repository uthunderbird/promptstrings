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
    PromptUnreferencedParameterError,
    PromptUnusedParameterError,
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
    """Strict mode raises PromptUnusedParameterError with structured fields (R1, R4).

    The leaf class is PromptUnusedParameterError (template path), carrying
    exc.unused_parameters and exc.resolved_keys as tuples of strings.
    """

    @promptstring
    def prompt(
        name=PromptDepends(lambda ctx: ctx.require("name")),
        unused=PromptDepends(lambda ctx: "x"),
    ):
        """Hello, {name}!"""

    with pytest.raises(PromptUnusedParameterError) as exc_info:
        asyncio.run(prompt.render(PromptContext({"name": "Ada"})))
    exc = exc_info.value
    # R1: named attributes are tuples of strings.
    assert isinstance(exc.unused_parameters, tuple)
    assert isinstance(exc.resolved_keys, tuple)
    assert "unused" in exc.unused_parameters
    assert "name" in exc.resolved_keys
    # R4: template path raises the correct leaf, NOT the generator leaf.
    assert not isinstance(exc, PromptUnreferencedParameterError)
    # Still catchable via parent (PromptStrictnessError and PromptRenderError).
    assert isinstance(exc, PromptStrictnessError)
    assert isinstance(exc, PromptRenderError)


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
# Exception attributes and to_dict() (ADR 0003 / R6)
# ---------------------------------------------------------------------------


def test_prompt_render_error_to_dict_has_stable_shape() -> None:
    """PromptRenderError.to_dict() has all documented keys (R-A, R-C) and is JSON-safe (R6)."""
    import json

    exc = PromptRenderError("oops", missing_key="user", context_keys=("a", "b"))
    d = exc.to_dict()
    assert set(d.keys()) == {"type", "message", "missing_key", "context_keys"}
    assert d["type"] == "PromptRenderError"
    assert d["missing_key"] == "user"
    assert d["context_keys"] == ["a", "b"]
    assert json.dumps(d)  # R6: JSON round-trip


def test_prompt_render_error_to_dict_none_fields_present_not_omitted() -> None:
    """None-valued fields appear as JSON null rather than being omitted (R-C)."""
    import json

    exc = PromptRenderError("oops")
    d = exc.to_dict()
    assert "missing_key" in d
    assert d["missing_key"] is None
    assert "context_keys" in d
    assert d["context_keys"] is None
    assert json.dumps(d)


def test_prompt_compile_error_to_dict_has_stable_shape() -> None:
    """PromptCompileError.to_dict() includes all documented keys for each cause value (R6)."""
    import json

    for cause, placeholder in [
        ("missing_template", None),
        ("format_spec", "name"),
        ("conversion", "name"),
        ("non_identifier_placeholder", "user.name"),
    ]:
        exc = PromptCompileError(
            "failed",
            prompt_name="my_prompt",
            cause=cause,  # type: ignore[arg-type]
            placeholder=placeholder,
            optimize_mode_active=False,
        )
        d = exc.to_dict()
        expected_keys = {
            "type", "message", "prompt_name", "cause", "placeholder",
            "optimize_mode_active", "missing_key", "context_keys",
        }
        assert set(d.keys()) == expected_keys, f"Missing keys for cause={cause!r}"
        assert d["type"] == "PromptCompileError"
        assert d["cause"] == cause
        assert d["missing_key"] is None
        assert d["context_keys"] is None
        assert json.dumps(d)  # R6: JSON round-trip


def test_prompt_render_error_raised_from_context_require_has_structured_fields() -> None:
    """PromptRenderError from PromptContext.require() carries missing_key and context_keys."""
    ctx = PromptContext({"a": 1, "b": 2})
    exc: PromptRenderError | None = None
    try:
        ctx.require("missing")
    except PromptRenderError as e:
        exc = e
    assert exc is not None
    assert exc.missing_key == "missing"
    assert set(exc.context_keys or ()) == {"a", "b"}


def test_exception_hierarchy_pickle_round_trip() -> None:
    """All public exception classes survive pickle round-trip with named attributes intact."""
    import pickle

    # PromptRenderError
    exc1 = PromptRenderError("render fail", missing_key="k", context_keys=("a", "b"))
    r1 = pickle.loads(pickle.dumps(exc1))
    assert str(r1) == "render fail"
    assert r1.missing_key == "k"
    assert r1.context_keys == ("a", "b")

    # PromptCompileError
    exc2 = PromptCompileError(
        "compile fail",
        prompt_name="p",
        cause="format_spec",
        placeholder="x",
        optimize_mode_active=True,
    )
    r2 = pickle.loads(pickle.dumps(exc2))
    assert str(r2) == "compile fail"
    assert r2.prompt_name == "p"
    assert r2.cause == "format_spec"
    assert r2.placeholder == "x"
    assert r2.optimize_mode_active is True


def test_prompt_unused_parameter_error_to_dict_shape() -> None:
    """PromptUnusedParameterError.to_dict() has all ADR 0003 documented keys (R6)."""
    import json

    exc = PromptUnusedParameterError(
        "unused: x",
        unused_parameters=("x",),
        resolved_keys=("x", "y"),
    )
    d = exc.to_dict()
    assert set(d.keys()) == {"type", "message", "unused_parameters", "resolved_keys", "missing_key", "context_keys"}
    assert d["type"] == "PromptUnusedParameterError"
    assert d["unused_parameters"] == ["x"]
    assert d["resolved_keys"] == ["x", "y"]
    assert d["missing_key"] is None
    assert d["context_keys"] is None
    assert json.dumps(d)


def test_prompt_unreferenced_parameter_error_to_dict_shape() -> None:
    """PromptUnreferencedParameterError.to_dict() has all ADR 0003 documented keys (R6)."""
    import json

    exc = PromptUnreferencedParameterError(
        "unreferenced: z",
        unreferenced_parameters=("z",),
        resolved_keys=("z", "w"),
    )
    d = exc.to_dict()
    assert set(d.keys()) == {"type", "message", "unreferenced_parameters", "resolved_keys", "missing_key", "context_keys"}
    assert d["type"] == "PromptUnreferencedParameterError"
    assert json.dumps(d)


def test_generator_strict_mode_raises_unreferenced_not_unused() -> None:
    """Generator strict path raises PromptUnreferencedParameterError, not PromptUnusedParameterError (R4)."""

    @promptstring_generator(strict=True)
    def prompt(topic: str, unused: str = "dropped"):
        yield f"Tell me about {topic}."

    with pytest.raises(PromptUnreferencedParameterError) as exc_info:
        asyncio.run(prompt.render_messages(PromptContext({"topic": "Python", "unused": "dropped"})))
    exc = exc_info.value
    assert "unused" in exc.unreferenced_parameters
    assert isinstance(exc.resolved_keys, tuple)
    # Must NOT be the template-path leaf.
    assert not isinstance(exc, PromptUnusedParameterError)
    assert isinstance(exc, PromptStrictnessError)


def test_prompt_compile_error_at_decoration_time_has_cause_and_optimize_flag() -> None:
    """PromptCompileError raised at decoration time carries cause and optimize_mode_active (R8)."""
    exc: PromptCompileError | None = None
    try:
        @promptstring
        def bad_prompt():  # type: ignore[empty-body]
            pass
    except PromptCompileError as e:
        exc = e
    assert exc is not None
    assert exc.cause == "missing_template"
    assert exc.prompt_name == "bad_prompt"
    assert isinstance(exc.optimize_mode_active, bool)


# ---------------------------------------------------------------------------
# ADR 0004: generator strict-mode heuristic warning (non-contract)
# ---------------------------------------------------------------------------


def test_generator_strict_mode_warns_for_empty_string_parameter(caplog: pytest.LogCaptureFixture) -> None:
    """Empty-string parameters in generator strict mode emit a WARNING (ADR 0004, non-contract).

    The logger name promptstrings.strict_heuristic is implementation-defined;
    this test verifies the informational behavior without asserting it is contractual.
    """
    import logging

    @promptstring_generator(strict=True)
    def prompt(user: str, empty_tag: str = ""):
        yield f"Hello {user}."

    with caplog.at_level(logging.WARNING, logger="promptstrings.strict_heuristic"):
        asyncio.run(prompt.render_messages(PromptContext({"user": "Ada", "empty_tag": ""})))

    # At least one WARNING about the empty-string parameter.
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert any("empty_tag" in r.message for r in warnings), (
        "Expected a WARNING about 'empty_tag' from the strict_heuristic logger"
    )


def test_generator_strict_mode_warns_for_single_char_parameter(caplog: pytest.LogCaptureFixture) -> None:
    """Single-character str() values emit a WARNING in generator strict mode (ADR 0004, non-contract)."""
    import logging

    @promptstring_generator(strict=True)
    def prompt(user: str, flag: str = "Y"):
        yield f"Hello {user}, flag is {flag}."

    with caplog.at_level(logging.WARNING, logger="promptstrings.strict_heuristic"):
        asyncio.run(prompt.render_messages(PromptContext({"user": "Ada", "flag": "Y"})))

    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert any("flag" in r.message for r in warnings)


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


def test_promptstring_resolves_multiple_awaited_dependencies_concurrently() -> None:
    """Multiple AwaitPromptDepends run concurrently via asyncio.gather (ADR 0001 Promise 9).

    The old at-most-one guard is removed in 1.0 — this is a one-way door.
    Resolvers must be cancellation-safe and must not depend on sibling side effects.
    """
    resolution_order: list[str] = []

    async def load_first(_ctx: PromptContext) -> str:
        resolution_order.append("first")
        return "Ada"

    async def load_second(_ctx: PromptContext) -> str:
        resolution_order.append("second")
        return "Bob"

    @promptstring
    def prompt(
        first=AwaitPromptDepends(load_first),
        second=AwaitPromptDepends(load_second),
    ):
        """Hello, {first} and {second}!"""

    rendered = asyncio.run(prompt.render())
    assert rendered == "Hello, Ada and Bob!"
    # Both resolvers ran (order not promised per ADR 0001 non-promise 2).
    assert set(resolution_order) == {"first", "second"}
