---
title: External dev API and integration seams for promptstrings 1.0
status: accepted
created: 2026-04-26
updated: 2026-04-26
---

# External dev API and integration seams for promptstrings 1.0

> **Promoted to ADR.** This proposal has been distilled into
> [`../decisions/0002-integration-seams-for-1.0.md`](../decisions/0002-integration-seams-for-1.0.md),
> which carries the locked 1.0 integration contract. This proposal is
> preserved as historical context — it includes the full red-team-cycle
> trace, per-vendor sketches, and decision rationale. For the canonical
> contract, read the ADR.

## Purpose

Extend the 1.0 baseline with the minimum public surface needed to plug
in external concerns — Pydantic for serialization, Dishka and
fast-depends for dependency injection, OpenTelemetry for tracing,
structlog or stdlib `logging` for structured logs, eval frameworks
(Inspect-AI, OpenAI Evals, deepeval, ragas), and prompt-management
systems (LangSmith Hub, PromptLayer, Helicone, Pezzo, Agenta) — without
bloating the core, without coupling the library to any one vendor, and
without breaking the SemVer contract already in
[`api-1.0-baseline.md`](api-1.0-baseline.md).

This proposal **adds**, it does not retract. Every promise in the
existing baseline still stands.

Audience: external public users from 1.0 onward. Same SemVer rigor as
the baseline.

This proposal is the output of a Swarm Mode design session on
2026-04-26. The decisions below were each contested by named critics;
rationale lives inline.

## Constraints (locked by user before iteration)

- **Constructor in 1.0:** yes, minimal `Promptstrings(*, observer=None)`
  as a configuration carrier. Module-level decorators delegate to a
  default singleton. Existing user code keeps working unchanged.
- **Pydantic in core:** **no.** Pydantic adapters live entirely in a
  separate `promptstrings-pydantic` package. Core public types stay
  pure stdlib `@dataclass(frozen=True)` with no Pydantic-aware methods
  or hooks. The core never imports Pydantic.
- **DI seam:** Design A. `PromptDepends(callable)` remains the only
  injection primitive. Framework-specific helpers (Dishka,
  fast-depends) live in external adapter packages and use
  `PromptContext.extras` to thread framework handles.
- **Surface budget:** ≤6 new public symbols. Final tally below: 5
  symbols + 1 field, under budget.

## Summary of additions

| Addition | Kind | Public name |
|---|---|---|
| Configuration carrier class | new symbol | `Promptstrings` |
| Observer Protocol | new symbol | `Observer` |
| Render-start event | new symbol | `RenderStartEvent` |
| Render-end event | new symbol | `RenderEndEvent` |
| Render-error event | new symbol | `RenderErrorEvent` |
| Framework-handle namespace | new field on existing type | `PromptContext.extras` |

**Total new public surface: 5 symbols + 1 field.** Under the 6-symbol
budget.

## New promises (1.0 contract)

> **Normative language:** The keywords MUST, MUST NOT, MAY, SHOULD, and
> SHOULD NOT in this section are used in conformance with
> [RFC 2119](https://www.rfc-editor.org/rfc/rfc2119), as in the
> baseline.

### Promise I-1 — `Promptstrings` configuration carrier

The package exports a `Promptstrings` class as the configuration carrier
for cross-cutting concerns. The class skeleton:

```python
class Promptstrings:
    """Configuration carrier for cross-cutting concerns.

    Module-level @promptstring and @promptstring_generator delegate to a
    default singleton instance. Construct your own when you need a
    custom observer or future extension hooks.
    """
    def __init__(self, *, observer: "Observer | None" = None) -> None: ...

    def promptstring(self, fn=None, *, strict: bool = True): ...
    def promptstring_generator(self, fn=None, *, strict: bool = False): ...
```

Module-level decorators:

```python
_default = Promptstrings()
promptstring = _default.promptstring
promptstring_generator = _default.promptstring_generator
```

**Constructor additivity rule (1.0 promise):** all
`Promptstrings.__init__` parameters are keyword-only. New parameters
MUST be added in minor releases as keyword-only with defaults that
preserve current behavior. Removing or renaming any parameter is a
2.0-scope breaking change.

**Instance-bound observer (1.0 promise):** the `observer` passed to a
`Promptstrings(...)` instance applies only to renders performed via
that instance's decorators. There is no "set the global observer"
pattern. Users who want a custom observer MUST construct their own
`Promptstrings(observer=...)` and decorate against it.

**Default singleton (1.0 promise):** the module-level `promptstring`
and `promptstring_generator` names are stable bindings to the methods
of a default `Promptstrings()` singleton instance with a no-op
observer. The default singleton is constructed once at module import.
Replacing the default singleton is not part of the public API.

> **Implementation delta (1.0 blocker):** `core.py` currently has no
> `Promptstrings` class; `@promptstring` and `@promptstring_generator`
> are bare module-level functions. The class must be added and the
> module-level names rebound to its default-singleton methods before
> 1.0. See *Promotion to ADR — additions* below.

### Promise I-2 — `Observer` Protocol and event types

The package exports a runtime-checkable `Observer` Protocol and three
immutable event types:

```python
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

@dataclass(frozen=True)
class RenderStartEvent:
    """Emitted exactly once at the start of each render call."""
    prompt_name: str
    placeholders: frozenset[str]
    started_at_ns: int  # time.monotonic_ns()

@dataclass(frozen=True)
class RenderEndEvent:
    """Emitted exactly once at the successful end of each render call."""
    prompt_name: str
    elapsed_ns: int
    message_count: int
    provenance: "PromptSourceProvenance | None"

@dataclass(frozen=True)
class RenderErrorEvent:
    """Emitted exactly once when a render call raises."""
    prompt_name: str
    elapsed_ns: int
    error: BaseException

@runtime_checkable
class Observer(Protocol):
    """Sync structured-event sink for render lifecycle.

    Implementations MUST be safe to call from inside the render path
    without blocking the event loop. Methods MUST NOT raise; if they
    do, exceptions are logged via
    `logging.getLogger('promptstrings.observer')` at WARNING and
    discarded.
    """
    def on_render_start(self, event: RenderStartEvent) -> None: ...
    def on_render_end(self, event: RenderEndEvent) -> None: ...
    def on_render_error(self, event: RenderErrorEvent) -> None: ...
```

**Event ordering (1.0 promise):** for any single render call, exactly
one of the following sequences fires:
- `on_render_start` → `on_render_end`, OR
- `on_render_start` → `on_render_error`.

`on_render_start` always fires first, before any `PromptDepends` or
`AwaitPromptDepends` resolver runs. `on_render_end` and
`on_render_error` are mutually exclusive for a given call.

**Error-event timing relative to baseline strict-mode (1.0 promise):**
when a render raises (compile-time check, strict-mode validation, or
resolver failure), `on_render_error` fires *after* the exception is
raised inside the render path and *before* it propagates to the
caller. The render result is never returned to the caller after
`on_render_error` fires. This preserves baseline Promise 11's
guarantee that strict-mode failures raise before any caller-side LLM
call: the observer is invoked *between* the strict-mode raise and the
caller's `await` point, never replacing the propagation.

**Sync-only hooks (1.0 promise):** Observer methods are synchronous.
Implementations that need async work MUST schedule it themselves
(e.g., `asyncio.create_task(...)`) and return immediately. Async
observer methods are not part of the 1.0 contract; introducing them
would require a sequencing contract not designed for 1.0.

**Observer-exception policy (1.0 promise):** exceptions raised from
any Observer method are caught by the library, logged via
`logging.getLogger("promptstrings.observer")` at WARNING level, and
discarded. Render outcome is unaffected. This requires `core.py` to
import `logging` (stdlib, allowed). The logger name is part of the 1.0
contract.

**Provenance on `RenderEndEvent` (1.0 promise):** when the rendered
output carries a `PromptSourceProvenance` (because the decorated
function returned a `PromptSource` with a non-`None` `provenance`),
the same provenance is exposed on the `RenderEndEvent`. When no
provenance is present, the field is `None`. The library does not
synthesize provenance.

> **Implementation delta (1.0 blocker):** the render paths in
> `_PromptString` and `_PromptStringGenerator` must call
> `self._observer.on_render_start(...)` before resolution begins,
> `self._observer.on_render_end(...)` on successful return, and
> `self._observer.on_render_error(...)` on any raised exception
> (including strict-mode failures and resolver failures). Wrap each
> Observer call in `try/except BaseException` with the WARNING-log
> fallback. Use `time.monotonic_ns()` for elapsed measurement.

### Promise I-3 — `PromptContext.extras` namespace

This proposal added the `extras` field to `PromptContext`. **The
canonical type definition, including both fields, the `extras`
semantics, the leading-underscore key convention, and the mutability
contract, lives in [`api-1.0-baseline.md`](api-1.0-baseline.md)
Promise 4.** This section preserves the rationale that motivated the
addition; the normative content is in the baseline.

**Why a separate field, not a sub-namespace inside `values`.** Mixing
user values and framework handles in `values` would pollute
`ctx.require("user_id")` semantics with framework-private keys. Two
separate fields make intent visible: user code reads from `values`,
framework code reads from `extras`. Documented in the rationale below
under *Why `extras` separate from `values`, not a single dict*.

**Adapter integration patterns.** See *Per-vendor integration
sketches* below — each adapter (Dishka, fast-depends, OTel, eval
collectors) constructs `PromptContext(values=..., extras={...})` at
the request boundary or wraps the user's render call site. The
library does not own any of this; it treats `extras` as opaque.

> **Implementation delta (1.0 blocker):** `PromptContext` in `core.py`
> currently has only `values`. The `extras` field MUST be added per
> the dataclass shape declared in baseline Promise 4 and the dataclass
> kept `frozen=True`. No render-path code changes are required because
> `extras` is invisible to library logic by design.
>
> **Local-variable name collision warning.** `core.py` currently uses
> `extras` as a local variable name in the strict-mode unused-parameter
> check (lines 191, 211, 280 in current `core.py` — the
> `extras = sorted(name for name in resolved if name not in compiled.placeholders)`
> idiom). When `PromptContext.extras` lands as a public field, the
> implementer MUST rename these locals (recommend `unused_params` or
> similar) to avoid reader confusion and to prevent any future
> `from … import extras` from shadowing them. Renaming the locals is
> independent of and may precede the `PromptContext.extras` field
> addition.

## Lifecycle map row deltas

The canonical lifecycle map is the table in
[`api-1.0-baseline.md`](api-1.0-baseline.md). This proposal does not
republish it. It extends two rows with text deltas:

**Resolution row gains:** when the render call begins,
`Observer.on_render_start` fires before any `PromptDepends` or
`AwaitPromptDepends` runs. `PromptContext.extras` is available
throughout resolution as part of the `PromptContext` passed in.

**Render row gains:** on successful completion,
`Observer.on_render_end` fires after the result is fully constructed
and just before return. On any exception (compile, strict-mode,
resolver), `Observer.on_render_error` fires after the exception is
raised inside the render path and before it propagates to the caller.
The render result is never returned to the caller after
`on_render_error` fires.

No other rows change.

## Additional non-promises

The baseline's non-promises stand. This proposal adds the following.
Non-promises in this proposal are numbered `N-1` through `N-9` to
disambiguate from the baseline's non-promises 1–12.

**N-1.** *No auto-emitted OTel spans.* The library does not import
`opentelemetry`, does not start spans, does not set attributes.
`Observer` is the only observability seam; an external
`promptstrings-otel` adapter is the right consumer.

**N-2.** *No DI container lifetime ownership.* `promptstrings` does
not enter, exit, or scope-manage any DI container. The caller's
framework owns container lifetimes; `promptstrings` is a passive
consumer of resolved values via `PromptDepends`.

**N-3.** *No `DependencyResolver` Protocol in 1.0.*
`PromptDepends(callable)` remains the seam. Framework integration is
wrapper-shaped (see integration sketches below). Locking a resolver
Protocol shape while DI frameworks are still evolving (fast-depends
2.x, Dishka recent revamp) would commit the library to an interface
it cannot reliably defend across 1.x. May be revisited in 2.0.

**N-4.** *No `TemplateLoader` Protocol in 1.0.* Returning a
`PromptSource` from a decorated function is the seam for
prompt-management systems. Caching, refresh, and hot-reload are
caller responsibility. May be revisited in 1.x or 2.0 if real-world
patterns demand it.

**N-5.** *No bundled Pydantic adapters.* Per user decision, Pydantic
integration lives entirely in `promptstrings-pydantic`. Core public
types do not declare `__get_pydantic_core_schema__` or any other
Pydantic-aware method.

**N-6.** *No async Observer methods in 1.0.* Sync only. Users
requiring async work spawn tasks inside their sync hook. Async
observers would require a sequencing contract; deferred past 1.0.

**N-7.** *No plugin registry or named-backend lookup.* No
`register_resolver(name, impl)`, no `Promptstrings.from_config(...)`.
Configuration is via constructor; everything else is parameterized at
decoration or render time.

**N-8.** *No enforcement of `extras` key conventions.* The
leading-underscore convention is informative only. The library does
not validate, namespace, or restrict `extras` keys.

**N-9.** *No global observer setter.* No `set_default_observer(obs)`
or equivalent. The default singleton's observer is fixed at module
import. Users with a custom observer construct their own
`Promptstrings(...)` instance.

**N-10.** *No promise about asyncio task / context ownership of
Observer calls under concurrent resolution.* `on_render_start` fires
on the task that called `render()`. When `AwaitPromptDepends`
resolvers run concurrently via `asyncio.gather`, those resolvers run
in their own tasks; the Observer is **not** invoked from those
resolver tasks. `on_render_end` and `on_render_error` fire on the
same task that called `render()`. Observer adapters that need
per-render correlation (e.g. for OTel span context propagation)
SHOULD use `contextvars` set on the calling task; the library does
not propagate any context across the gathered resolver tasks
automatically. This non-promise may be tightened in 1.x once adapter
authors report concrete needs.

## Decision rationale (why these and not others)

### Why a configuration-carrier class, not a full app object

Rejected: "FastAPI-style `Promptstrings()` app object that owns
routing, lifespan, middleware." `promptstrings` does not own routing,
does not run an event loop, does not manage lifespan. An app object
would imply responsibilities the library does not have. The
configuration-carrier shape (only `__init__` parameters; no `run()`,
no `mount()`, no `add_middleware()`) is the smallest class that
addresses the actual integration need: a place to attach an
`Observer` and future cross-cutting hooks.

Rejected: "no constructor at all; everything decorator-bound." This
was the initial position from one expert. It was overruled because
two integration scenarios (Dishka request scopes; OTel observer
configuration) both produced bad code without an instance to attach
config to. The constructor exists to give framework users a non-global
binding point.

### Why instance-bound observer, not a global setter

Rejected: "global `set_default_observer(obs)` mutates the default
singleton." Two libraries in the same process wanting different
observers would race on the global. The instance-bound model is
honest: the observer that fires is determined by which
`Promptstrings` instance you decorated against. Cost is one extra
line per integration (`ps = Promptstrings(observer=...)`); benefit is
no shared mutable state.

### Why three event dataclasses, not one with a phase field

Rejected: "single `RenderEvent` with `phase: Literal['start', 'end',
'error']`." Saves 2 symbols (we'd be at 3, not 5). Loses
discoverability: code-generation agents and IDEs surface three named
methods on the Protocol; a single-event design hides structure behind
an isinstance/match chain. With budget room (5 ≤ 6), the three-event
shape is the right call.

### Why sync observer methods, not async

Rejected: "async observers, awaited inside the render path." Couples
render's event loop semantics to user observer code; introduces
ordering questions ("are observers awaited in series? in parallel?
fire-and-forget?") not designed for 1.0. Sync hooks force observers
to be cheap; users who need async work spawn tasks themselves. Same
choice as `logging` and `structlog`. Re-openable in 1.x if real users
report systemic pain.

### Why swallow observer exceptions, not propagate

Rejected: "let observer exceptions propagate; render fails." Users
instrumenting prod (the primary observer-using audience) would face
production outages from telemetry bugs. Rejected: "swallow silently."
Telemetry bugs become invisible. Compromise: catch, log via stdlib
`logging` at WARNING with a stable logger name (`promptstrings.observer`),
discard. Operators have a knob; render is unaffected.

### Why Design A for DI, not a `DependencyResolver` Protocol

Rejected: "Protocol with `async resolve(parameter, marker, context) ->
Any` that the library defers to per parameter." Locks the library to
a specific resolution-call shape. fast-depends 2.x, Dishka post-revamp,
and any future DI library evolve their resolution interfaces; whatever
shape we publish in 1.0 will be wrong for at least one of them within
a year. `PromptDepends(callable)` is already a Protocol-of-one (the
resolver-callable shape); framework adapters wrap their container's
`get` into a closure and pass it. Not pretty as inline syntax, but
adapter packages provide thin helpers (`from_dishka`, `from_fastdeps`)
that hide the wrapping. Library stays uncommitted.

### Why `extras` separate from `values`, not a single dict

Rejected: "user values and framework handles share `PromptContext.values`
under documented key prefixes." Pollutes `ctx.require("user_id")` with
framework-private keys; agents and humans reading user code see
`_dishka_container` and have to know it's "framework, ignore." Two
separate fields make intent visible: user code reads from `values`,
framework code reads from `extras`. One extra field for a permanent
ergonomics win.

### Why no `TemplateLoader` Protocol

Rejected: "Protocol with `async load(name, version) -> PromptSource`
for prompt-management systems." The same concern as DependencyResolver:
locks too early. LangSmith, PromptLayer, Helicone, Pezzo, and Agenta
each have different fetch APIs, different version semantics, and
different caching expectations. A common Protocol would either be too
narrow (fits only LangSmith) or too generic (provides no value beyond
"return a `PromptSource`" — which is what the function body already
does). The seam is `PromptSource` returned from a decorated function;
caching and version selection are caller responsibility.

### Why Pydantic adapters out of core

Per user decision. Rationale recorded for completeness:

The alternative considered was a gated `__get_pydantic_core_schema__`
classmethod on each public dataclass with `try/except` Pydantic import
inside. Technically pure-stdlib at import time. Rejected because it
adds a "Pydantic-aware" surface to types that the baseline calls
"pure stdlib"; conceptually couples the type definition to a
third-party schema protocol. External `promptstrings-pydantic`
package preserves cleaner separation: anyone who installs it gets
first-class Pydantic; nobody else pays. Trade-off: Pydantic users
must `pip install promptstrings-pydantic` and import its
side-effecting setup module once.

## DX rubric additions (extends the baseline rubric)

Falsifiable criteria for the new surface:

- **R11.** Module-level `@promptstring` and `@promptstring_generator`
  produce instances whose observer is the default singleton's no-op
  observer, regardless of any later-constructed `Promptstrings()`.
  *Test:* construct `Promptstrings(observer=spy)`; decorate at module
  level via the bare `@promptstring`; render; assert `spy` saw zero
  calls.

- **R12.** Decorating via a constructed `Promptstrings(observer=spy)`
  fires `spy.on_render_start`, then exactly one of `on_render_end` /
  `on_render_error`, in that order, with `started_at_ns < end_event.
  started_at_ns + end_event.elapsed_ns`. *Test:* spy + render; assert
  call order and timing fields.

- **R13.** Observer methods that raise are logged via
  `logging.getLogger("promptstrings.observer")` at WARNING and do not
  affect render outcome. *Test:* observer raising in
  `on_render_start`; render still produces correct output; capture
  assert WARNING log with stable logger name.

- **R14.** `PromptContext` constructed with `extras={"_x": ...}` does
  not affect resolution of any user `PromptDepends` or
  `AwaitPromptDepends`. *Test:* render twice with identical `values`
  and different `extras`; output identical.

- **R15.** `Observer` is `runtime_checkable`. *Test:* `isinstance(obj,
  Observer)` returns `True` for a class implementing the three
  methods.

- **R16.** All Observer event dataclasses are `frozen=True`. *Test:*
  attempt mutation; assert raises.

## Per-vendor integration sketches

These live separately in
[`design/dx/integration-patterns.md`](../dx/integration-patterns.md)
once that doc is created. Including canonical examples here is part of
this proposal so reviewers can verify the 1.0 surface is sufficient.

### Pydantic — separate `promptstrings-pydantic` package

```python
# promptstrings_pydantic/__init__.py
from pydantic_core import core_schema
from promptstrings import (
    PromptMessage, PromptSource, PromptSourceProvenance, PromptContext,
)

def _adapt(cls):
    """Patch a stdlib dataclass to expose __get_pydantic_core_schema__."""
    def __get_pydantic_core_schema__(_cls, source, handler):
        return core_schema.dataclass_schema(_cls, ...)
    cls.__get_pydantic_core_schema__ = classmethod(__get_pydantic_core_schema__)
    return cls

# Patch at adapter-import time. Idempotent.
for _t in (PromptMessage, PromptSource, PromptSourceProvenance, PromptContext):
    _adapt(_t)
```

User installs `pip install promptstrings-pydantic` and imports it once
during application setup. From then on, all `promptstrings` types are
first-class in Pydantic models.

### Dishka — separate `promptstrings-dishka` package

```python
from dishka import AsyncContainer, Scope
from promptstrings import AwaitPromptDepends, PromptContext

def from_dishka(component_type, scope: Scope = Scope.REQUEST):
    """Wrap a Dishka container.get into an AwaitPromptDepends."""
    async def _resolve(ctx: PromptContext):
        container: AsyncContainer = ctx.extras["_dishka_container"]
        return await container.get(component_type, scope=scope)
    return AwaitPromptDepends(_resolve)

# User code
@ps.promptstring
def hello(user: User = from_dishka(User)) -> None:
    """Hello, {user.name}."""

# At request boundary (e.g. a FastAPI handler)
async with container() as request_container:
    ctx = PromptContext(
        values={"user_id": req.user_id},
        extras={"_dishka_container": request_container},
    )
    await hello.render(ctx)
```

Dishka owns the container's lifetime; `promptstrings` consumes
resolved values via `PromptDepends`.

### fast-depends — separate `promptstrings-fastdeps` package

```python
from fast_depends import inject, Depends
from promptstrings import AwaitPromptDepends, PromptContext

def from_fastdeps(injected_callable):
    """Wrap a fast-depends @inject-decorated callable."""
    async def _resolve(ctx: PromptContext):
        return await injected_callable(**ctx.values)
    return AwaitPromptDepends(_resolve)

@inject
async def get_user(user_id: int, repo: UserRepo = Depends(provide_repo)) -> User:
    return await repo.get(user_id)

@ps.promptstring
def hello(user: User = from_fastdeps(get_user)) -> None:
    """Hello, {user.name}."""
```

### OpenTelemetry — separate `promptstrings-otel` package

```python
import contextvars
from opentelemetry import trace
from promptstrings import (
    Observer, RenderStartEvent, RenderEndEvent, RenderErrorEvent,
)

_active_span: contextvars.ContextVar = contextvars.ContextVar("ps_otel_span")

class OtelObserver(Observer):
    def __init__(self, tracer_name: str = "promptstrings"):
        self._tracer = trace.get_tracer(tracer_name)

    def on_render_start(self, event: RenderStartEvent) -> None:
        span = self._tracer.start_span(f"promptstring.render:{event.prompt_name}")
        span.set_attribute("promptstring.placeholders", list(event.placeholders))
        _active_span.set(span)

    def on_render_end(self, event: RenderEndEvent) -> None:
        span = _active_span.get(None)
        if span is None:
            return
        span.set_attribute("promptstring.elapsed_ns", event.elapsed_ns)
        span.set_attribute("promptstring.message_count", event.message_count)
        if event.provenance:
            if event.provenance.source_id:
                span.set_attribute("promptstring.source_id", event.provenance.source_id)
            if event.provenance.version:
                span.set_attribute("promptstring.source_version", event.provenance.version)
        span.end()

    def on_render_error(self, event: RenderErrorEvent) -> None:
        span = _active_span.get(None)
        if span is None:
            return
        span.record_exception(event.error)
        span.set_status(trace.StatusCode.ERROR)
        span.end()

ps = Promptstrings(observer=OtelObserver())
```

Concurrent renders are correlated via `contextvars`. The library's
Observer surface stays simple; the adapter handles concurrency.

### structlog — separate `promptstrings-structlog` package

```python
import structlog
from promptstrings import Observer

class StructlogObserver(Observer):
    def __init__(self, logger=None):
        self._log = logger or structlog.get_logger("promptstrings")

    def on_render_start(self, event):
        self._log.debug(
            "render.start",
            prompt=event.prompt_name,
            placeholders=list(event.placeholders),
        )

    def on_render_end(self, event):
        self._log.info(
            "render.end",
            prompt=event.prompt_name,
            elapsed_ms=event.elapsed_ns / 1e6,
            message_count=event.message_count,
            source_id=event.provenance.source_id if event.provenance else None,
            source_version=event.provenance.version if event.provenance else None,
        )

    def on_render_error(self, event):
        self._log.error(
            "render.error",
            prompt=event.prompt_name,
            elapsed_ms=event.elapsed_ns / 1e6,
            error_type=type(event.error).__name__,
            error_message=str(event.error),
        )
```

### Inspect-AI / OpenAI Evals / deepeval / ragas — separate adapter packages or in-app code

Eval-framework integration is a special case of `Observer` +
provenance. No new Protocol needed in core.

```python
from promptstrings import Observer, RenderEndEvent

class EvalCollector(Observer):
    """Records every render to an eval-framework sink."""
    def __init__(self, sink):
        self._sink = sink

    def on_render_start(self, event):
        pass

    def on_render_end(self, event: RenderEndEvent):
        self._sink.record(
            prompt_name=event.prompt_name,
            provenance=event.provenance,
            elapsed_ms=event.elapsed_ns / 1e6,
            message_count=event.message_count,
        )

    def on_render_error(self, event):
        self._sink.record_failure(event.prompt_name, event.error)
```

The eval framework's job is the *evaluation*; promptstrings'
contribution is **provenance + observer events**.

### LangSmith Hub / PromptLayer / Helicone / Pezzo / Agenta — no adapter package needed

The seam is returning a `PromptSource` from the decorated function:

```python
from langsmith import Client
from promptstrings import promptstring, PromptSource, PromptSourceProvenance

_lsc = Client()

@promptstring
def chat_assistant(user_query: str) -> PromptSource:
    pulled = _lsc.pull_prompt("chat-assistant:v3")
    return PromptSource(
        content=pulled.template,
        provenance=PromptSourceProvenance(
            source_id="langsmith://chat-assistant",
            version=pulled.version,
            hash=pulled.commit_sha,
        ),
    )
```

Caching is the user's call (`functools.lru_cache`, refresh per render,
TTL cache, etc.). The library does not own this.

## Implementation deltas (additions to baseline plan)

This proposal layers on top of the baseline's implementation plan.
Once both this proposal and the baseline are accepted, the combined
ADR work order is:

### Implementation delta index (this proposal)

In addition to the deltas listed in the baseline's
[*Implementation delta index*](api-1.0-baseline.md#implementation-delta-index)
(5 rows covering the Protocol, gather, leaf exceptions, generator
strict, and catch guidance), this proposal adds three more:

| Delta | Inline location |
|---|---|
| `Promptstrings` class + module-decorator rebinding | Promise I-1 blockquote |
| `Observer` Protocol + 3 event dataclasses + render-path wiring | Promise I-2 blockquote |
| `PromptContext.extras` field | Promise I-3 blockquote |

### Ordered implementation sequence (additions only)

These steps run after the baseline's ordered implementation sequence
completes, or interleaved with it where dependencies allow:

1. Add `Observer`, `RenderStartEvent`, `RenderEndEvent`,
   `RenderErrorEvent` to `core.py`. Import `time` and `logging` at
   module top.
2. Add `_NoOpObserver` private implementation of `Observer`.
3. Add `Promptstrings` class with `__init__(*, observer=None)` storing
   `self._observer = observer or _NoOpObserver()`.
4. Move the existing `promptstring` and `promptstring_generator`
   decorator bodies to be methods on `Promptstrings`.
5. Wire Observer calls into both `_PromptString.render*` and
   `_PromptStringGenerator.render*` paths: `on_render_start` before
   resolution; `on_render_end` on success before return;
   `on_render_error` in `except BaseException` before re-raise. Wrap
   each Observer call in `try/except BaseException` with
   `logging.getLogger("promptstrings.observer").warning(...)`.
6. At module bottom, construct `_default = Promptstrings()` and rebind
   `promptstring = _default.promptstring`,
   `promptstring_generator = _default.promptstring_generator`.
7. Add `extras: Mapping[str, Any] = field(default_factory=dict)` to
   `PromptContext`. Confirm `frozen=True` is preserved.
8. Land tests for R11–R16.
9. Update `__init__.py` to export the 5 new symbols.

### Migration notes (0.x → 1.0, addition to baseline migration notes)

- **No code change required** for users on bare `@promptstring` /
  `@promptstring_generator`. Module-level decorators continue to work
  via the default singleton.
- **`PromptContext` constructor** gains a new optional `extras`
  parameter. Existing call sites passing only `values=` continue to
  work; existing call sites using positional args (none expected;
  `PromptContext` is dataclass-frozen) would break, but the dataclass
  has only one field today and positional construction is not part
  of the contract.
- **Pydantic consumers** must install `promptstrings-pydantic` (a new
  package) and import it once at startup. Pure-stdlib consumers see
  no change.

## Out of scope of *this proposal* (deferred to later design)

These flow from the locked-in shape and do not block 1.0:

- The exact `__init__` signature of every adapter package
  (`promptstrings-pydantic`, `promptstrings-dishka`,
  `promptstrings-fastdeps`, `promptstrings-otel`,
  `promptstrings-structlog`, `promptstrings-inspect`). Each is its own
  repo with its own ADR.
- Whether `from_dishka` and `from_fastdeps` should also accept
  `*, scope=...` and `*, validate=...` keyword-only modifiers. Adapter
  package design.
- Whether to ship a default OTel adapter under
  `promptstrings.observability.otel` gated by an optional extra. Lean
  no for 1.0; revisit if "no built-in OTel" friction is reported.
- Whether to add a `BatchObserver` protocol that fans-out events to
  multiple `Observer` instances. Trivial to implement in user code; no
  need to standardize.
- Whether the leading-underscore `extras` key convention should ever
  become enforced. Lean no permanently.

## Promotion to ADR

When this proposal is accepted:

1. Distill into
   `design/decisions/0002-integration-seams-for-1.0.md`. Drop the
   per-vendor sketches into the canonical doc
   (`design/dx/integration-patterns.md`); keep them out of the ADR.
2. Move this proposal file to `design/notes/` as historical context,
   or delete it once the ADR is accepted.
3. Create `design/dx/integration-patterns.md` containing the per-vendor
   sketches as canonical examples. Update `design/dx/README.md` to
   index it.
4. Implement the ordered sequence above.
5. Tag 1.0 only after R11–R16 tests pass, in addition to the
   baseline rubric's tests.

## Glossary

Definitions for the new vocabulary introduced by this proposal —
**Observer**, **configuration carrier**, **adapter package**, and
**extras (`PromptContext.extras`)** — are canonical in
[`design/glossary.md`](../glossary.md). This proposal does not
duplicate them.

## History

This proposal was developed via the Swarm Mode skill on 2026-04-26,
with named critics (Dishka maintainer, Charity Majors, Samuel Colvin)
and an evangelist (Sebastián Ramírez) contesting the constructor,
Observer, Pydantic, and DI seam decisions; rejected alternatives are
preserved in the rationale section. User decisions on constructor
inclusion, surface budget, Pydantic placement, and DI seam shape were
gathered before iteration narrowed to the final shape.
