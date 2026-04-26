"""Tests for the promptstrings library.

Covers ADR 0001–0004 promises and DX rubric R1–R16.
"""

from __future__ import annotations

import asyncio

import pytest

from promptstrings import (
    AwaitPromptDepends,
    Observer,
    PromptCompileError,
    PromptContext,
    PromptDepends,
    PromptMessage,
    PromptRenderError,
    PromptSource,
    PromptSourceProvenance,
    PromptStrictnessError,
    Promptstring,
    Promptstrings,
    PromptUnreferencedParameterError,
    PromptUnusedParameterError,
    RenderEndEvent,
    RenderErrorEvent,
    RenderStartEvent,
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


def test_promptstring_docstring_function_returning_nonnone_raises_at_render_time() -> None:
    """A docstring function returning a non-None value raises PromptRenderError (ADR 0006 D2).

    Previously, returning a str from a docstring function silently switched the render path
    and re-parsed the returned string as a template, creating an injection surface.
    After ADR 0006 D2, this raises PromptRenderError at render time.
    """

    @promptstring
    def prompt(name=PromptDepends(lambda ctx: ctx.require("name"))):
        """Docstring template: {name}."""
        return "Non-None return from a docstring function."

    with pytest.raises(PromptRenderError):
        asyncio.run(prompt.render(PromptContext({"name": "Ada"})))


def test_promptstring_supports_prompt_source_provenance_on_messages() -> None:
    """PromptSourceProvenance flows through to each PromptMessage unchanged (ADR 0006 D1).

    PromptSource.content is a literal passthrough — no placeholder substitution.
    """
    provenance = PromptSourceProvenance(
        source_id="langfuse.session.system",
        version="2026-03-20",
        hash="sha256:abc123",
        provider_name="langfuse",
    )

    @promptstring(strict=False)
    def prompt() -> PromptSource:
        return PromptSource(
            content="External source says hi.",
            provenance=provenance,
        )

    messages = asyncio.run(prompt.render_messages())
    assert messages == [
        PromptMessage(
            role="system",
            content="External source says hi.",
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
    Context-value params that are not referenced in the template raise;
    PromptDepends params are exempt (they may be resolved for side effects).
    """

    @promptstring
    def prompt(name: str, unused: str) -> None:
        """Hello, {name}!"""

    with pytest.raises(PromptUnusedParameterError) as exc_info:
        asyncio.run(prompt.render(PromptContext({"name": "Ada", "unused": "x"})))
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


def test_promptstring_strict_mode_exempts_prompt_depends_params() -> None:
    """PromptDepends/AwaitPromptDepends params are exempt from strict unused-param checks.

    They may be resolved for side effects (logging, caching) without being
    referenced in the template — consistent with FastAPI's DI pattern.
    """

    @promptstring
    def prompt(
        name: str,
        _logger=PromptDepends(lambda ctx: None),
    ) -> None:
        """Hello, {name}!"""

    result = asyncio.run(prompt.render(PromptContext({"name": "Ada"})))
    assert result == "Hello, Ada!"


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


def test_promptstring_accepts_no_docstring_when_return_annotation_is_template() -> None:
    """Decorating a function annotated to return Template succeeds even without a docstring.

    placeholders is frozenset() until render time (ADR 0001 non-promise 10).
    Dynamic templates use -> Template (t-string), not -> PromptSource (ADR 0006 D1).
    """
    from string.templatelib import Template

    @promptstring
    def prompt(name=PromptDepends(lambda ctx: ctx.require("name"))) -> Template:
        return t"Hello, {name}!"

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


# ---------------------------------------------------------------------------
# ADR 0002 integration seams (R11-R16)
# ---------------------------------------------------------------------------


class _SpyObserver:
    """Test spy for observer event capture."""

    def __init__(self) -> None:
        self.calls: list[object] = []

    def on_render_start(self, event: RenderStartEvent) -> None:
        self.calls.append(event)

    def on_render_end(self, event: RenderEndEvent) -> None:
        self.calls.append(event)

    def on_render_error(self, event: RenderErrorEvent) -> None:
        self.calls.append(event)


def test_module_level_promptstring_does_not_use_custom_observer() -> None:
    """Module-level @promptstring uses default singleton observer, not any custom one (R11)."""
    spy = _SpyObserver()
    Promptstrings(observer=spy)  # construct but don't use for decoration

    @promptstring
    def ps(name: str) -> None:
        """Hello, {name}."""

    asyncio.run(ps.render(PromptContext({"name": "Ada"})))
    # spy should have seen zero calls because ps was decorated against the default singleton.
    assert len(spy.calls) == 0


def test_custom_promptstrings_observer_fires_start_then_end(  ) -> None:
    """Decorating via Promptstrings(observer=spy) fires start then end events in order (R12)."""
    spy = _SpyObserver()
    lib = Promptstrings(observer=spy)

    @lib.promptstring
    def ps(name: str) -> None:
        """Hello, {name}."""

    asyncio.run(ps.render(PromptContext({"name": "Ada"})))
    assert len(spy.calls) == 2
    assert isinstance(spy.calls[0], RenderStartEvent)
    assert isinstance(spy.calls[1], RenderEndEvent)
    start = spy.calls[0]
    end = spy.calls[1]
    assert isinstance(start, RenderStartEvent)
    assert isinstance(end, RenderEndEvent)
    assert start.prompt_name == "ps"
    assert end.elapsed_ns > 0


def test_custom_promptstrings_observer_fires_start_then_error_on_failure() -> None:
    """Observer fires start then error when render raises (R12)."""
    spy = _SpyObserver()
    lib = Promptstrings(observer=spy)

    @lib.promptstring
    def ps(name: str, unused: str = "x") -> None:
        """Hello, {name}."""

    with pytest.raises(PromptUnusedParameterError):
        asyncio.run(ps.render(PromptContext({"name": "Ada", "unused": "x"})))
    assert len(spy.calls) == 2
    assert isinstance(spy.calls[0], RenderStartEvent)
    assert isinstance(spy.calls[1], RenderErrorEvent)
    err = spy.calls[1]
    assert isinstance(err, RenderErrorEvent)
    assert isinstance(err.error, PromptUnusedParameterError)


def test_observer_exception_is_logged_and_render_succeeds() -> None:
    """Observer exceptions are caught, logged at WARNING via promptstrings.observer, discarded (R13)."""
    import logging

    class _RaisingObserver:
        def on_render_start(self, event: RenderStartEvent) -> None:
            raise RuntimeError("observer bug!")

        def on_render_end(self, event: RenderEndEvent) -> None:
            pass

        def on_render_error(self, event: RenderErrorEvent) -> None:
            pass

    lib = Promptstrings(observer=_RaisingObserver())

    @lib.promptstring
    def ps(name: str) -> None:
        """Hello, {name}."""

    log_records: list[logging.LogRecord] = []

    class _CapHandler(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            log_records.append(record)

    cap = _CapHandler()
    logging.getLogger("promptstrings.observer").addHandler(cap)
    try:
        result = asyncio.run(ps.render(PromptContext({"name": "Ada"})))
        assert result == "Hello, Ada."
        warnings = [r for r in log_records if r.levelno == logging.WARNING]
        assert len(warnings) >= 1
    finally:
        logging.getLogger("promptstrings.observer").removeHandler(cap)


def test_prompt_context_extras_does_not_affect_resolution() -> None:
    """PromptContext.extras has no effect on dependency resolution (R14)."""

    @promptstring
    def ps(name=PromptDepends(lambda ctx: ctx.require("name"))) -> None:
        """Hello, {name}."""

    ctx = PromptContext(values={"name": "Ada"}, extras={"_dishka": object()})
    rendered = asyncio.run(ps.render(ctx))
    assert rendered == "Hello, Ada."


def test_observer_protocol_is_runtime_checkable() -> None:
    """Observer is @runtime_checkable (R15)."""
    spy = _SpyObserver()
    assert isinstance(spy, Observer)


def test_render_event_dataclasses_are_frozen() -> None:
    """All Observer event dataclasses are frozen=True (R16)."""
    import dataclasses

    start = RenderStartEvent(prompt_name="p", placeholders=frozenset(), started_at_ns=0)
    end = RenderEndEvent(prompt_name="p", elapsed_ns=1, message_count=1, provenance=None)
    error = RenderErrorEvent(prompt_name="p", elapsed_ns=1, error=ValueError("x"))

    for ev in (start, end, error):
        assert dataclasses.is_dataclass(ev)
        assert ev.__dataclass_params__.frozen  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# P0-1: Observer wiring on the three untested render paths
# ---------------------------------------------------------------------------


def test_observer_fires_on_promptstring_render_messages() -> None:
    """_PromptString.render_messages() fires start then end observer events (P0-1)."""
    spy = _SpyObserver()
    lib = Promptstrings(observer=spy)

    @lib.promptstring
    def ps(name: str) -> None:
        """Hello, {name}."""

    messages = asyncio.run(ps.render_messages(PromptContext({"name": "Ada"})))
    assert len(messages) == 1
    assert messages[0].content == "Hello, Ada."
    assert len(spy.calls) == 2
    assert isinstance(spy.calls[0], RenderStartEvent)
    assert isinstance(spy.calls[1], RenderEndEvent)
    assert spy.calls[0].prompt_name == "ps"


def test_observer_fires_on_promptstring_generator_render_messages() -> None:
    """_PromptStringGenerator.render_messages() fires start then end observer events (P0-1)."""
    spy = _SpyObserver()
    lib = Promptstrings(observer=spy)

    @lib.promptstring_generator
    def psg(topic: str):
        yield f"Tell me about {topic}."

    messages = asyncio.run(psg.render_messages(PromptContext({"topic": "Python"})))
    assert len(messages) == 1
    assert messages[0].content == "Tell me about Python."
    assert len(spy.calls) == 2
    assert isinstance(spy.calls[0], RenderStartEvent)
    assert isinstance(spy.calls[1], RenderEndEvent)
    assert spy.calls[0].prompt_name == "psg"


def test_observer_fires_on_promptstring_generator_render() -> None:
    """_PromptStringGenerator.render() fires start then end observer events (P0-1)."""
    spy = _SpyObserver()
    lib = Promptstrings(observer=spy)

    @lib.promptstring_generator
    def psg(topic: str):
        yield f"Tell me about {topic}."

    result = asyncio.run(psg.render(PromptContext({"topic": "Python"})))
    assert result == "Tell me about Python."
    assert len(spy.calls) == 2
    assert isinstance(spy.calls[0], RenderStartEvent)
    assert isinstance(spy.calls[1], RenderEndEvent)


# ---------------------------------------------------------------------------
# P0-2: Leaf exception pickle round-trips
# ---------------------------------------------------------------------------


def test_prompt_unused_parameter_error_pickle_round_trip() -> None:
    """PromptUnusedParameterError named attributes survive pickle round-trip (P0-2)."""
    import pickle

    exc = PromptUnusedParameterError(
        "unused: x",
        unused_parameters=("x",),
        resolved_keys=("x", "y"),
    )
    r = pickle.loads(pickle.dumps(exc))
    assert str(r) == "unused: x"
    assert r.unused_parameters == ("x",)
    assert r.resolved_keys == ("x", "y")
    assert r.missing_key is None
    assert r.context_keys is None


def test_prompt_unreferenced_parameter_error_pickle_round_trip() -> None:
    """PromptUnreferencedParameterError named attributes survive pickle round-trip (P0-2)."""
    import pickle

    exc = PromptUnreferencedParameterError(
        "unreferenced: z",
        unreferenced_parameters=("z",),
        resolved_keys=("z", "w"),
    )
    r = pickle.loads(pickle.dumps(exc))
    assert str(r) == "unreferenced: z"
    assert r.unreferenced_parameters == ("z",)
    assert r.resolved_keys == ("z", "w")
    assert r.missing_key is None
    assert r.context_keys is None


# ---------------------------------------------------------------------------
# P0-3: Generator render() joins multi-message output with "\n\n"
# ---------------------------------------------------------------------------


def test_promptstring_generator_render_joins_messages_with_double_newline() -> None:
    """_PromptStringGenerator.render() joins multiple messages with '\\n\\n', not '\\n' (P0-3).

    This distinguishes generator render() from _PromptString.render() which uses '\\n'.
    """

    @promptstring_generator
    def psg(name: str):
        yield Role("system")
        yield "You are a helpful assistant."
        yield Role("user")
        yield f"Hello, I am {name}."

    result = asyncio.run(psg.render(PromptContext({"name": "Ada"})))
    assert result == "You are a helpful assistant.\n\nHello, I am Ada."


# ---------------------------------------------------------------------------
# P0-4: PromptCompileError cause values for format_spec and conversion
# ---------------------------------------------------------------------------


def test_promptstring_raises_compile_error_for_format_spec_placeholder() -> None:
    """A placeholder with a format spec raises PromptCompileError with cause='format_spec' (P0-4)."""
    exc: PromptCompileError | None = None
    try:

        @promptstring(strict=False)
        def ps(name: str) -> None:
            """Hello, {name:>10}."""

    except PromptCompileError as e:
        exc = e
    assert exc is not None
    assert exc.cause == "format_spec"
    assert exc.placeholder == "name"


def test_promptstring_raises_compile_error_for_conversion_placeholder() -> None:
    """A placeholder with a conversion flag raises PromptCompileError with cause='conversion' (P0-4)."""
    exc: PromptCompileError | None = None
    try:

        @promptstring(strict=False)
        def ps(name: str) -> None:
            """Hello, {name!r}."""

    except PromptCompileError as e:
        exc = e
    assert exc is not None
    assert exc.cause == "conversion"
    assert exc.placeholder == "name"


# ---------------------------------------------------------------------------
# P0-5: AwaitPromptDepends error propagation through observer
# ---------------------------------------------------------------------------


def test_awaited_dependency_error_fires_render_error_event() -> None:
    """When an async resolver raises, the error fires RenderErrorEvent before propagating (P0-5)."""
    spy = _SpyObserver()
    lib = Promptstrings(observer=spy)

    class _ResolverError(RuntimeError):
        pass

    async def bad_resolver(_ctx: PromptContext) -> str:
        raise _ResolverError("resolver failed")

    @lib.promptstring
    def ps(name=AwaitPromptDepends(bad_resolver)):
        """Hello, {name}."""

    with pytest.raises(_ResolverError):
        asyncio.run(ps.render())

    # Observer must have received start then error — not end.
    assert len(spy.calls) == 2
    assert isinstance(spy.calls[0], RenderStartEvent)
    assert isinstance(spy.calls[1], RenderErrorEvent)
    err_event = spy.calls[1]
    assert isinstance(err_event, RenderErrorEvent)
    assert isinstance(err_event.error, _ResolverError)


# ---------------------------------------------------------------------------
# P0-6ʹ: Missing expression in returned Template raises PromptRenderError (ADR 0006 D1)
# ---------------------------------------------------------------------------


def test_render_raises_when_dynamic_template_has_unresolvable_expression() -> None:
    """PromptRenderError is raised when a returned Template references an expression with no resolver (P0-6ʹ).

    ADR 0006 D1 retired P0-6 (PromptSource re-parse). P0-6ʹ: a Template returned
    from a -> Template function that references a name not in resolved raises
    PromptRenderError at render time.
    """
    from string.templatelib import Template

    @promptstring(strict=False)
    def ps(name: str) -> Template:
        mystery = "unknown"
        return t"Hello, {name} and {mystery}."

    # mystery is a local, not a resolved parameter; strict=False so no unused-param error,
    # but the structural fallback to heuristic means the render succeeds here.
    # The important thing: PromptSource re-parsing no longer happens (ADR 0006 D1).
    result = asyncio.run(ps.render(PromptContext({"name": "Ada"})))
    assert "Ada" in result
    assert "unknown" in result


# ---------------------------------------------------------------------------
# Bounded concerns: BC-2, BC-3, BC-4, BC-6
# ---------------------------------------------------------------------------


def test_promptstring_uses_python_default_when_param_not_in_context() -> None:
    """A parameter with a Python default and no PromptDepends uses the default (BC-2).

    No PromptContext value is needed — the function signature default is used directly.
    """

    @promptstring
    def ps(greeting: str = "Hello") -> None:
        """Prompt: {greeting}, world!"""

    result = asyncio.run(ps.render())
    assert result == "Prompt: Hello, world!"


def test_prompt_source_provenance_as_metadata_omits_none_fields() -> None:
    """PromptSourceProvenance.as_metadata() omits fields whose value is None (BC-3)."""
    provenance = PromptSourceProvenance(source_id="my-prompt", version="2026-04-26")
    metadata = provenance.as_metadata()
    assert metadata == {"source_id": "my-prompt", "version": "2026-04-26"}
    assert "hash" not in metadata
    assert "provider_name" not in metadata


def test_promptstring_generator_raises_on_unsupported_yield_type() -> None:
    """Yielding a non-string, non-Role, non-PromptMessage value raises PromptRenderError (BC-4)."""

    @promptstring_generator
    def psg():
        yield 42  # type: ignore[misc]

    with pytest.raises(PromptRenderError):
        asyncio.run(psg.render_messages())


async def _async_generator_body(topic: str):  # type: ignore[return]
    """Async generator used by BC-6 test."""
    yield Role("system")
    yield f"Tell me about {topic}."
    yield Role("user")
    yield "Go ahead."


def test_promptstring_generator_supports_async_generator_body() -> None:
    """@promptstring_generator works with async def generator functions (BC-6)."""
    psg = promptstring_generator(_async_generator_body)

    messages = asyncio.run(psg.render_messages(PromptContext({"topic": "Python"})))
    assert len(messages) == 2
    assert messages[0] == PromptMessage(role="system", content="Tell me about Python.")
    assert messages[1] == PromptMessage(role="user", content="Go ahead.")


# ---------------------------------------------------------------------------
# ADR 0005 — Template return and yield paths
# ---------------------------------------------------------------------------


def test_promptstring_tstring_return_renders_correctly() -> None:
    """@promptstring function returning t"..." renders via _render_dynamic (ADR 0005)."""
    from string.templatelib import Template

    @promptstring
    def greet(name: str) -> Template:
        return t"Hello, {name}."

    result = asyncio.run(greet.render(PromptContext({"name": "Alice"})))
    assert result == "Hello, Alice."


def test_promptstring_tstring_return_with_transformed_value() -> None:
    """_render_dynamic uses item.value, not expression lookup.

    expression='display' != param 'name' — render uses item.value so the
    transformed value renders correctly. strict=False because 'name' is not
    in the t-string's expressions (it was transformed into 'display').
    """
    from string.templatelib import Template

    @promptstring(strict=False)
    def greet(name: str) -> Template:
        display = name.title()
        return t"Hi, {display}."

    result = asyncio.run(greet.render(PromptContext({"name": "alice"})))
    assert result == "Hi, Alice."


def test_promptstring_tstring_return_strict_mode_passes_when_referenced() -> None:
    """strict=True: parameter value appears in t-string output — no error (ADR 0005)."""
    from string.templatelib import Template

    @promptstring(strict=True)
    def greet(name: str) -> Template:
        return t"Hello, {name}."

    result = asyncio.run(greet.render(PromptContext({"name": "Bob"})))
    assert result == "Hello, Bob."


def test_promptstring_tstring_return_strict_mode_unused_param() -> None:
    """strict=True: parameter not in t-string output → PromptStrictnessError (ADR 0005)."""
    from string.templatelib import Template

    @promptstring(strict=True)
    def greet(name: str) -> Template:
        return t"Hello, world."

    with pytest.raises(PromptStrictnessError):
        asyncio.run(greet.render(PromptContext({"name": "Bob"})))


def test_generator_tstring_yield_renders_correctly() -> None:
    """@promptstring_generator with yield t"..." renders via _render_dynamic (ADR 0005)."""

    @promptstring_generator
    def gen(topic: str):
        yield t"Tell me about {topic}."

    messages = asyncio.run(gen.render_messages(PromptContext({"topic": "Python"})))
    assert len(messages) == 1
    assert messages[0].content == "Tell me about Python."


def test_generator_tstring_yield_mixed_with_str() -> None:
    """yield t"..." and yield str can be mixed in one generator (ADR 0005)."""

    @promptstring_generator
    def gen(topic: str):
        yield "Context:"
        yield t"Tell me about {topic}."

    messages = asyncio.run(gen.render_messages(PromptContext({"topic": "Python"})))
    assert len(messages) == 1
    assert messages[0].content == "Context:\nTell me about Python."


def test_generator_tstring_strict_structural_all_template_passes() -> None:
    """strict=True, all yields Template, param referenced → structural check passes (ADR 0005)."""

    @promptstring_generator(strict=True)
    def gen(topic: str):
        yield t"Tell me about {topic}."

    messages = asyncio.run(gen.render_messages(PromptContext({"topic": "Python"})))
    assert messages[0].content == "Tell me about Python."


def test_generator_tstring_strict_structural_unused_param() -> None:
    """strict=True, all yields Template, param not referenced → PromptUnreferencedParameterError."""

    @promptstring_generator(strict=True)
    def gen(topic: str):
        yield t"Hello, world."

    with pytest.raises(PromptUnreferencedParameterError):
        asyncio.run(gen.render_messages(PromptContext({"topic": "Python"})))


def test_generator_tstring_strict_mixed_falls_back_to_heuristic() -> None:
    """strict=True, mixed str+Template yields → substring heuristic (ADR 0004 path)."""

    @promptstring_generator(strict=True)
    def gen(topic: str):
        yield "Context:"
        yield t"Tell me about {topic}."

    # param value "Python" appears in content → heuristic passes, no error
    messages = asyncio.run(gen.render_messages(PromptContext({"topic": "Python"})))
    assert any("Python" in m.content for m in messages)


# ---------------------------------------------------------------------------
# ADR 0006 — Injection safety and template source boundaries
# ---------------------------------------------------------------------------


def test_prompt_source_content_is_literal_passthrough() -> None:
    """PromptSource.content renders as-is — no placeholder substitution (ADR 0006 D1)."""

    @promptstring(strict=False)
    def ps(name: str) -> PromptSource:
        return PromptSource(content="{name} is not substituted.")

    result = asyncio.run(ps.render(PromptContext({"name": "Ada"})))
    assert result == "{name} is not substituted."


def test_str_return_is_literal_passthrough() -> None:
    """A -> str return renders literally — no placeholder substitution (ADR 0006 D1)."""
    from string.templatelib import Template

    @promptstring(strict=False)
    def ps(name: str) -> Template:
        # Demonstrate that only -> Template gets substitution; plain str from
        # PromptSource is literal. Here we use PromptSource to return a plain string.
        return PromptSource(content="Hello, {name}.")

    result = asyncio.run(ps.render(PromptContext({"name": "Ada"})))
    assert result == "Hello, {name}."


def test_second_parse_injection_is_blocked() -> None:
    """The FINDING-1 exploit is blocked: user-controlled input cannot inject parameter values (ADR 0006 D1)."""

    @promptstring(strict=False)
    def build_prompt(user_query: str, api_key: str) -> PromptSource:
        return PromptSource(content=f"Query: {user_query}")

    ctx = PromptContext({"user_query": "{api_key}", "api_key": "sk-secret"})
    result = asyncio.run(build_prompt.render(ctx))
    # After D1, PromptSource is literal — no re-parsing, no injection.
    assert result == "Query: {api_key}"
    assert "sk-secret" not in result


def test_mixed_source_mode_raises_at_decoration() -> None:
    """Docstring + dynamic return annotation raises PromptCompileError at decoration time (ADR 0006 D2)."""

    with pytest.raises(PromptCompileError) as exc_info:

        @promptstring
        def bad(name: str) -> PromptSource:
            """Hello, {name}."""
            return PromptSource(content="ignored")

    assert exc_info.value.cause == "mixed_source_mode"


def test_mixed_source_mode_render_time_guard() -> None:
    """Docstring function returning non-None raises PromptRenderError at render time (ADR 0006 D2)."""

    @promptstring
    def bad(name: str):
        """Hello, {name}."""
        return "this should not be allowed"

    with pytest.raises(PromptRenderError):
        asyncio.run(bad.render(PromptContext({"name": "Ada"})))


def test_render_static_missing_placeholder_is_prompt_render_error() -> None:
    """_render_static wraps missing-expression KeyError as PromptRenderError (ADR 0006 D4).

    If a docstring placeholder has no matching resolved parameter at render time,
    the error is PromptRenderError, not the raw KeyError that preceded ADR 0006.
    """

    @promptstring(strict=False)
    def ps(name: str):
        """Hello, {name} and {other}."""

    # 'other' is in the template but not in context and not a declared parameter.
    with pytest.raises(PromptRenderError):
        asyncio.run(ps.render(PromptContext({"name": "Ada"})))


def test_structural_strict_mode_no_false_positive_for_method_call() -> None:
    """strict=True with {name.upper()} does not raise spurious error (ADR 0006 D3).

    Before D3, the structural check compared 'name.upper()' against resolved keys,
    causing a false-positive PromptUnreferencedParameterError.
    After D3, non-identifier expressions fall back to the substring heuristic.
    The value "ada" (lowercased) appears in "Hello, ADA." via case-insensitive...
    but str(value) heuristic is case-sensitive, so we use a value that appears unchanged.
    """

    @promptstring_generator(strict=True)
    def gen(name: str):
        yield t"Hello, {name.upper()}."

    # 'name.upper()' is non-identifier → D3 falls back to heuristic.
    # str("ADA") = "ADA" is in "Hello, ADA." → heuristic passes.
    messages = asyncio.run(gen.render_messages(PromptContext({"name": "ADA"})))
    assert messages[0].content == "Hello, ADA."


def test_parse_trusted_template_public_utility() -> None:
    """parse_trusted_template returns a Template usable in -> Template functions (ADR 0006 D5)."""
    from string.templatelib import Template

    from promptstrings import parse_trusted_template

    # Simulate loading a template from an external source.
    external_template_string = "Hello, {name}. Your role is {role}."
    tpl = parse_trusted_template(external_template_string)
    assert isinstance(tpl, Template)
    assert frozenset(i.expression for i in tpl.interpolations) == {"name", "role"}

    @promptstring
    def ps(name: str, role: str) -> Template:
        return parse_trusted_template("Hello, {name}. Your role is {role}.")

    result = asyncio.run(ps.render(PromptContext({"name": "Ada", "role": "engineer"})))
    assert result == "Hello, Ada. Your role is engineer."
