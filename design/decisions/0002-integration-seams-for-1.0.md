# 0002 — Integration seams for 1.0

- **Status:** Accepted
- **Date:** 2026-04-26
- **Deciders:** Daniyar Supiyev (author); design contested via Swarm Mode session with named critics (Dishka maintainer, Charity Majors, Samuel Colvin) and synthesizer roles
- **Supersedes:** —
- **Superseded by:** —

## Context

ADR 0001 locks the 1.0 contract for `promptstrings` core. External
consumers who want to integrate with Pydantic for serialization,
Dishka or fast-depends for dependency injection, OpenTelemetry for
tracing, structlog for structured logs, eval frameworks (Inspect-AI,
deepeval, ragas), or prompt-management systems (LangSmith Hub,
PromptLayer) need extension seams that do not bloat the core, do not
couple the library to any one vendor, and do not break the SemVer
contract.

This ADR distills `proposals/api-1.0-integrations.md`, which was
red-teamed alongside the baseline proposal (cross-document
consistency audit) and as part of the corpus-integrated audit. The
proposal converged on the contract recorded here.

User constraints locked before this design iterated:
- Constructor in 1.0: yes, minimal `Promptstrings(*, observer=None)`
  as configuration carrier.
- Pydantic in core: no. Pydantic adapters live in a separate
  `promptstrings-pydantic` package; core public types stay pure
  stdlib `@dataclass(frozen=True)`.
- DI seam: Design A. `PromptDepends(callable)` remains the only
  injection primitive; framework helpers live in external adapter
  packages and use `PromptContext.extras`.
- Surface budget: ≤6 new public symbols. Final tally: 5 symbols + 1
  field, under budget.

This ADR **adds**, it does not retract. Every promise in ADR 0001
still stands.

## Decision

`promptstrings` 1.0 exports three additional contract entities
beyond ADR 0001: a `Promptstrings` configuration carrier class, an
`Observer` Protocol with three event dataclasses, and an `extras`
field on `PromptContext`. Total new public surface: 5 symbols + 1
field.

The keywords MUST, MUST NOT, MAY, SHOULD, and SHOULD NOT are used in
conformance with [RFC 2119](https://www.rfc-editor.org/rfc/rfc2119),
as in ADR 0001.

### Surface additions

| Addition | Kind | Public name |
|---|---|---|
| Configuration carrier class | new symbol | `Promptstrings` |
| Observer Protocol | new symbol | `Observer` |
| Render-start event | new symbol | `RenderStartEvent` |
| Render-end event | new symbol | `RenderEndEvent` |
| Render-error event | new symbol | `RenderErrorEvent` |
| Framework-handle namespace | new field on existing type | `PromptContext.extras` |

### New promises

#### Promise I-1 — `Promptstrings` configuration carrier

The package exports a `Promptstrings` class:

```python
class Promptstrings:
    """Configuration carrier for cross-cutting concerns.

    Module-level @promptstring and @promptstring_generator delegate
    to a default singleton instance. Construct your own when you
    need a custom observer or future extension hooks.
    """
    def __init__(self, *, observer: "Observer | None" = None) -> None: ...

    def promptstring(self, fn=None, *, strict: bool = True): ...
    def promptstring_generator(self, fn=None, *, strict: bool = False): ...
```

Module-level decorators delegate to a default singleton:

```python
_default = Promptstrings()
promptstring = _default.promptstring
promptstring_generator = _default.promptstring_generator
```

**Constructor additivity rule.** All `Promptstrings.__init__`
parameters are keyword-only. New parameters MUST be added in minor
releases as keyword-only with defaults that preserve current behavior.
Removing or renaming any parameter is a 2.0-scope breaking change.

**Instance-bound observer.** The `observer` passed to a
`Promptstrings(...)` instance applies only to renders performed via
that instance's decorators. There is no "set the global observer"
pattern. Users who want a custom observer MUST construct their own
`Promptstrings(observer=...)` and decorate against it.

**Default singleton.** The module-level `promptstring` and
`promptstring_generator` names are stable bindings to the default
singleton's methods, constructed once at module import. Replacing the
default singleton is not part of the public API.

#### Promise I-2 — `Observer` Protocol and event types

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
    """Sync structured-event sink for render lifecycle."""
    def on_render_start(self, event: RenderStartEvent) -> None: ...
    def on_render_end(self, event: RenderEndEvent) -> None: ...
    def on_render_error(self, event: RenderErrorEvent) -> None: ...
```

**Event ordering.** For any single render call, exactly one sequence
fires: `on_render_start` → `on_render_end`, OR
`on_render_start` → `on_render_error`. `on_render_start` always fires
first, before any `PromptDepends` or `AwaitPromptDepends` resolver
runs.

**Error-event timing relative to baseline strict-mode (Promise 11).**
When a render raises, `on_render_error` fires *after* the exception is
raised inside the render path and *before* it propagates to the
caller. The render result is never returned to the caller after
`on_render_error` fires. This preserves baseline Promise 11's
guarantee that strict-mode failures raise before any caller-side LLM
call.

**Sync-only hooks.** Observer methods are synchronous. Implementations
that need async work MUST schedule it themselves and return
immediately. Async observer methods are not part of the 1.0 contract.

**Observer-exception policy.** Exceptions raised from any Observer
method are caught by the library, logged via
`logging.getLogger("promptstrings.observer")` at WARNING level, and
discarded. Render outcome is unaffected. The logger name
`promptstrings.observer` is part of the 1.0 contract.

**Provenance on `RenderEndEvent`.** When the rendered output carries a
`PromptSourceProvenance`, the same provenance is exposed on the
`RenderEndEvent`. When no provenance is present, the field is `None`.
The library does not synthesize provenance.

#### Promise I-3 — `PromptContext.extras` namespace

`PromptContext` gains one new field (canonical type definition lives
in ADR 0001 Promise 4):

```python
@dataclass(frozen=True)
class PromptContext:
    values: dict[str, Any] = field(default_factory=dict)
    extras: Mapping[str, Any] = field(default_factory=dict)
```

**Purpose.** `extras` is a documented namespace for framework-supplied
handles (DI containers, request sessions, tracer references,
eval-collector sinks). The library does not interpret any key in
`extras`; it does not read, write, or enumerate `extras` itself.

**Type.** `extras` is typed as `Mapping[str, Any]`, deliberately
read-only at the type level. Frameworks SHOULD construct
`PromptContext` with extras populated at the start of a render and
SHOULD NOT mutate the extras mapping after passing the context to
`render` or `render_messages`.

**Convention (informative, not normative).** Keys for framework state
SHOULD use a single leading underscore (e.g. `"_dishka_container"`,
`"_otel_tracer"`) to flag "framework, not user-facing." This is a
convention only; the library does not enforce it.

### Updated lifecycle integration map (delta from ADR 0001)

The canonical lifecycle map is in ADR 0001. This ADR extends two rows:

**Resolution row gains:** when the render call begins,
`Observer.on_render_start` fires before any `PromptDepends` or
`AwaitPromptDepends` runs. `PromptContext.extras` is available
throughout resolution as part of the `PromptContext` passed in.

**Render row gains:** on successful completion,
`Observer.on_render_end` fires after the result is fully constructed
and just before return. On any exception, `Observer.on_render_error`
fires after the exception is raised inside the render path and before
it propagates to the caller. The render result is never returned to
the caller after `on_render_error` fires.

No other rows change.

### Additional non-promises

ADR 0001's non-promises stand. This ADR adds (numbered N-1 through
N-10 to disambiguate from ADR 0001's non-promises 1–12):

**N-1.** No auto-emitted OTel spans. The library does not import
`opentelemetry`. `Observer` is the only observability seam; an
external `promptstrings-otel` adapter is the right consumer.

**N-2.** No DI container lifetime ownership. `promptstrings` does not
enter, exit, or scope-manage any DI container.

**N-3.** No `DependencyResolver` Protocol in 1.0.
`PromptDepends(callable)` remains the seam.

**N-4.** No `TemplateLoader` Protocol in 1.0. Returning a
`PromptSource` from a decorated function is the seam for
prompt-management systems.

**N-5.** No bundled Pydantic adapters. Pydantic integration lives
entirely in `promptstrings-pydantic`. Core public types do not declare
`__get_pydantic_core_schema__` or any other Pydantic-aware method.

**N-6.** No async Observer methods in 1.0.

**N-7.** No plugin registry or named-backend lookup. No
`register_resolver(name, impl)`, no `Promptstrings.from_config(...)`.

**N-8.** No enforcement of `extras` key conventions.

**N-9.** No global observer setter. The default singleton's observer
is fixed at module import.

**N-10.** No promise about asyncio task / context ownership of
Observer calls under concurrent resolution. `on_render_start` fires
on the task that called `render()`. When `AwaitPromptDepends`
resolvers run concurrently via `asyncio.gather`, those resolvers run
in their own tasks; the Observer is **not** invoked from those
resolver tasks. Observer adapters that need per-render correlation
SHOULD use `contextvars` set on the calling task.

### DX rubric additions (R11–R16)

These extend ADR 0001's R1–R10 as falsifiable 1.0 gates.

- **R11.** Module-level `@promptstring` and `@promptstring_generator`
  produce instances whose observer is the default singleton's no-op
  observer, regardless of any later-constructed `Promptstrings()`.
  *Test:* construct `Promptstrings(observer=spy)`; decorate at module
  level via the bare `@promptstring`; render; assert `spy` saw zero
  calls.

- **R12.** Decorating via a constructed `Promptstrings(observer=spy)`
  fires `spy.on_render_start`, then exactly one of `on_render_end` /
  `on_render_error`, in that order, with `started_at_ns < end_event.
  started_at_ns + end_event.elapsed_ns`.

- **R13.** Observer methods that raise are logged via
  `logging.getLogger("promptstrings.observer")` at WARNING and do not
  affect render outcome. *Test:* observer raising in
  `on_render_start`; render still produces correct output; capture
  asserts WARNING log with stable logger name.

- **R14.** `PromptContext` constructed with `extras={"_x": ...}`
  does not affect resolution of any user `PromptDepends` or
  `AwaitPromptDepends`.

- **R15.** `Observer` is `runtime_checkable`.

- **R16.** All Observer event dataclasses are `frozen=True`.

## Alternatives considered

- **No constructor at all; everything decorator-bound** — rejected.
  Two integration scenarios (Dishka request scopes; OTel observer
  configuration) produced bad code without an instance to attach
  config to. The constructor exists to give framework users a
  non-global binding point.

- **FastAPI-style app object that owns routing, lifespan, middleware**
  — rejected. `promptstrings` does not own routing, does not run an
  event loop, does not manage lifespan. The configuration-carrier
  shape (only `__init__` parameters; no `run()`, `mount()`,
  `add_middleware()`) is the smallest class that addresses the
  integration need.

- **Global observer setter** (`set_default_observer(obs)` mutating
  the default singleton) — rejected. Two libraries in the same
  process wanting different observers would race on the global. The
  instance-bound model is honest: the observer that fires is
  determined by which `Promptstrings` instance you decorated against.

- **Single `RenderEvent` with `phase: Literal['start', 'end',
  'error']`** — rejected. Saves 2 symbols but loses discoverability:
  code-generation agents and IDEs surface three named methods on the
  Protocol; a single-event design hides structure behind an isinstance
  chain. With budget room (5 ≤ 6), three events is the right call.

- **Async observer methods** — rejected for 1.0. Couples render's
  event loop semantics to user observer code; introduces ordering
  questions not designed for 1.0. Sync hooks force observers to be
  cheap; users who need async work spawn tasks themselves. Re-openable
  in 1.x if real users report systemic pain.

- **Propagate observer exceptions** — rejected. Users instrumenting
  prod (the primary observer-using audience) would face production
  outages from telemetry bugs. **Swallow silently** — also rejected;
  telemetry bugs become invisible. Compromise: catch, log via stdlib
  `logging` at WARNING with a stable logger name, discard.

- **`DependencyResolver` Protocol with `async resolve(parameter,
  marker, context) -> Any` that the library defers to per parameter**
  — rejected. Locks the library to a specific resolution-call shape
  that won't fit fast-depends 2.x, Dishka post-revamp, or future DI
  libraries. `PromptDepends(callable)` is already a Protocol-of-one
  (the resolver-callable shape); framework adapters wrap their
  container's `get` into a closure. May revisit in 2.0.

- **`TemplateLoader` Protocol with `async load(name, version) ->
  PromptSource`** — rejected. Same lock-too-early concern as
  DependencyResolver. LangSmith, PromptLayer, Helicone, Pezzo, and
  Agenta each have different fetch APIs, version semantics, and
  caching expectations. The seam is `PromptSource` returned from a
  decorated function; caching and version selection are caller
  responsibility.

- **Pydantic-aware methods on core types** (gated
  `__get_pydantic_core_schema__` classmethod with try/except Pydantic
  import) — rejected per user decision. The alternative was
  technically pure-stdlib at import time, but conceptually couples
  the type definition to a third-party schema protocol. External
  `promptstrings-pydantic` package preserves cleaner separation.

- **`extras` shared with `values` under documented key prefixes** —
  rejected. Pollutes `ctx.require("user_id")` semantics with
  framework-private keys. Two separate fields make intent visible.

- **`extras` key convention enforcement** (library refuses
  non-underscore keys) — rejected. Convention is enough;
  over-enforcement creates friction. Open as 1.x design discussion if
  real-world pollution emerges.

## Consequences

**Positive:**
- Five integration vendors (Pydantic, Dishka, fast-depends, OTel,
  structlog) plus eval frameworks and prompt-management systems all
  compose cleanly with this surface, validated by sketches in
  `dx/integration-patterns.md`.
- Library remains pure stdlib at runtime; consumer applications
  bring whatever versions of OTel / Pydantic / etc. they already
  use.
- Observer Protocol gives adapter authors a stable surface that
  works identically across client codebases — cross-codebase
  consistency is the protocol's strongest justification.
- Configuration-carrier shape leaves the door open for future
  cross-cutting hooks (resolver, loader, etc.) as keyword-only
  additive `__init__` parameters.

**Negative:**
- Module-level decorator type changes from "function" to "bound
  method of singleton instance." Observable via
  `inspect.ismethod(promptstring)`. ADR 0001 explicitly says
  `type(promptstring)` is not part of the contract; the change is
  legitimate but observable.
- The instance-bound observer model means users who want different
  observers in different scopes must construct multiple
  `Promptstrings` instances and decorate against them separately —
  no global "switch the observer" knob.
- Adapter packages (`promptstrings-pydantic`, etc.) are out-of-tree
  work that the core library does not own; their quality and
  release cadence is independent.

**Neutral / follow-on:**
- Implementation deltas (additions to ADR 0001's work order; run
  after or interleaved with that sequence where dependencies allow):
  1. Add `Observer`, `RenderStartEvent`, `RenderEndEvent`,
     `RenderErrorEvent` to `core.py`. Import `time` and `logging` at
     module top.
  2. Add `_NoOpObserver` private implementation of `Observer`.
  3. Add `Promptstrings` class with `__init__(*, observer=None)`.
  4. Move existing `promptstring` and `promptstring_generator`
     decorator bodies to be methods on `Promptstrings`.
  5. Wire Observer calls into both `_PromptString.render*` and
     `_PromptStringGenerator.render*` paths with WARNING-log
     fallback for observer exceptions.
  6. At module bottom, construct `_default = Promptstrings()` and
     rebind module-level decorators.
  7. Add `extras` field to `PromptContext`. Confirm `frozen=True`
     preserved.
  8. Land tests for R11–R16.
  9. Update `__init__.py` to export the 5 new symbols.

  **Local-variable name collision warning:** when adding `extras` to
  `PromptContext`, the implementer MUST first rename the existing
  `extras` local variables in `core.py` (lines 191, 211, 280 in
  current `core.py` — the unused-parameter strict-check loop) to
  avoid reader confusion. Recommend `unused_params` or similar.

- 0.x → 1.0 migration notes (additions to ADR 0001's migration notes):
  - **No code change required** for users on bare `@promptstring` /
    `@promptstring_generator`.
  - **`PromptContext` constructor** gains an optional `extras`
    parameter; existing call sites passing only `values=` continue
    to work.
  - **Pydantic consumers** must install `promptstrings-pydantic` (a
    new package) and import it once at startup. Pure-stdlib
    consumers see no change.

- Per-vendor adapter packages are anticipated as separate ADRs in
  separate repos:
  - `promptstrings-pydantic` (recommended for 1.0 release-day
    validation) — gated `__get_pydantic_core_schema__` patching
    pattern.
  - `promptstrings-otel` (recommended for 1.0 release-day
    validation) — `OtelObserver` with `contextvars` per-render
    correlation.
  - `promptstrings-dishka`, `promptstrings-fastdeps`,
    `promptstrings-structlog`, `promptstrings-inspect` — post-1.0,
    each its own out-of-tree ADR.

- Per-vendor integration patterns for these adapters are documented
  canonically in [`../dx/integration-patterns.md`](../dx/integration-patterns.md)
  (currently a draft stub; the integrations proposal carried the
  initial sketches, which migrate to the canonical doc as adapters
  validate).

## Notes

This ADR distills `proposals/api-1.0-integrations.md` (status:
proposed prior to this ADR's acceptance). The proposal carries
decision rationale, red-team findings trace, and historical drafting
notes; this ADR carries the locked contract.

The proposal was developed via a Swarm Mode design session (named
critics: Dishka maintainer, Charity Majors, Samuel Colvin; evangelist:
Sebastián Ramírez; synthesizer role) and hardened through the
cross-document consistency audit and corpus-integrated audit.

VISION context for these seams:
[`../VISION.md`](../VISION.md) (Problem 5
"observability blind spot" anchors integrations Promise I-2; design
property "no vendor lock-in" anchors the adapter-packages model).

Companion ADR:
[`0001-api-and-dx-baseline-for-1.0.md`](0001-api-and-dx-baseline-for-1.0.md).
