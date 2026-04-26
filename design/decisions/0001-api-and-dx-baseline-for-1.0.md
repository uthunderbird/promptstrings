# 0001 — API and DX baseline for 1.0

- **Status:** Accepted
- **Date:** 2026-04-26
- **Deciders:** Daniyar Supiyev (author); design contested via Swarm Mode session with named critics (Liskov, Ronacher, Schlawack, Ramírez) and synthesizer roles
- **Supersedes:** —
- **Superseded by:** —

## Context

`promptstrings` is a Python library for strict prompt-template
composition with provenance tracking and FastAPI-style dependency
injection. It is preparing its first public release (1.0) and needs a
locked SemVer contract before tagging.

Forces at play:

- **External 1.0 audience.** Per user direction, every promise in this
  ADR is a public SemVer contract. Every non-promise is a deliberate
  refusal. The library has no field data from external adopters yet;
  framing is inference-based.
- **Pure-stdlib runtime.** The core has zero third-party dependencies
  and never imports any third-party package at module top level. This
  constraint shapes every decision below.
- **Two-audience DX.** Humans writing application code AND LLM agents
  reading/writing that same code. Choices that serve agents (precise
  types, structured errors, introspectable state) generally also
  serve humans, and the design treats this convergence as
  load-bearing.
- **Pre-existing 0.x implementation.** The current `core.py` ships with
  several 0.x behaviors that must change for 1.0 to be honest (see
  *Consequences — Implementation deltas*).

This ADR is the distillation of `proposals/api-1.0-baseline.md`,
which was red-teamed across three rounds (contract completeness,
execution + rollback, wording + legibility) plus a cross-document
audit and a corpus-integrated audit. The proposal converged on the
contract recorded here; promotion to ADR locks it.

The vision context — *why* these promises matter, not *what* they
say — lives in [`../VISION.md`](../VISION.md). This ADR is the
*what*.

## Decision

The 1.0 SemVer contract for `promptstrings` consists of **13 promises**
and **12 non-promises** below. Public exception classes carry named,
picklable attributes plus `to_dict()`. The lifecycle integration map
defines seven phases. Ten falsifiable rubric criteria (R1–R10) gate
the 1.0 tag.

The keywords MUST, MUST NOT, MAY, SHOULD, and SHOULD NOT in the
*Promises* and *Non-promises* sections are used in conformance with
[RFC 2119](https://www.rfc-editor.org/rfc/rfc2119).

### Promises (1.0 contract)

#### API surface

1. **Two decorators only.** The package exports exactly two
   decorators: `@promptstring` and `@promptstring_generator`. New
   decorators in 1.x will only be added if they satisfy the
   `Promptstring` Protocol. The exact callable type of these
   decorators is **not** part of the contract; users may rely on
   `@promptstring` and `promptstring(fn)` working as decorator and
   call expression respectively, but not on `type(promptstring)`
   being any specific class. The companion ADR 0002 binds these
   names to methods of a default `Promptstrings()` singleton
   instance.

2. **`Promptstring` Protocol.** The package exports a
   runtime-checkable `Promptstring` Protocol:

   ```python
   from typing import Mapping, Protocol, runtime_checkable
   import inspect

   @runtime_checkable
   class Promptstring(Protocol):
       placeholders: frozenset[str]
       declared_parameters: Mapping[str, inspect.Parameter]

       async def render(self, context: PromptContext | None) -> str: ...
       async def render_messages(
           self, context: PromptContext | None
       ) -> list[PromptMessage]: ...
   ```

   `inspect.Parameter` is the 1.0-locked type for `declared_parameters`
   values; replacing it with a custom dataclass is a 2.0-scope
   breaking change. Users may rely on the `inspect.Parameter`
   interface (`name`, `default`, `annotation`, `kind`) for the entire
   1.x line.

   The Protocol is the long-term extension surface. Concrete classes
   are implementation; user code SHOULD type against the Protocol,
   not against `_PromptString` or `_PromptStringGenerator`.

   **Protocol is append-only in 1.x.** New members MAY be added in
   minor releases; existing members MUST NOT be removed or narrowed.

   **Minimum `PromptMessage` schema.** Every `PromptMessage` returned
   by `render_messages` carries:
   - `role: str` — message role (e.g. `"system"`, `"user"`,
     `"assistant"`); valid role strings governed by the LLM provider,
     not this library.
   - `content: str` — the rendered message body. Never empty.
   - `source: PromptSourceProvenance | None` — present exactly when
     the user supplied a `PromptSource` with non-`None` `provenance`.

   `PromptSourceProvenance` carries `source_id`, `version`, `hash`,
   `provider_name`, all `str | None`. The library propagates whatever
   the user supplies; it does not fill, validate, or modify any field.

3. **`strict` is a public parameter on both decorators.**
   - `@promptstring(strict=True)` — default. Raises
     `PromptUnusedParameterError` when a resolved parameter is not
     consumed by the template.
   - `@promptstring_generator(strict=False)` — default. When
     `strict=True` is passed explicitly, raises
     `PromptUnreferencedParameterError` when a resolved parameter
     value cannot be found in the rendered output.

   Asymmetric defaults are intentional: template-based promptstrings
   can be checked structurally; generator-based promptstrings are
   checked by a best-effort heuristic (Promise 11), so strict is
   opt-in for generators.

4. **`PromptContext` is the only value-injection mechanism.** No
   globals, no thread-locals, no env-style fallback. `context=None`
   is exactly equivalent to `PromptContext()` and will not change in
   1.x.

   Canonical 1.0 dataclass shape:

   ```python
   from collections.abc import Mapping
   from dataclasses import dataclass, field
   from typing import Any

   @dataclass(frozen=True)
   class PromptContext:
       values: dict[str, Any] = field(default_factory=dict)
       extras: Mapping[str, Any] = field(default_factory=dict)
   ```

   Both fields are part of the 1.0 contract. `extras` semantics and
   convention are defined in companion ADR 0002 (Promise I-3). The
   library reads `values` during dependency resolution; `extras` is
   not interpreted by the library.

   **Resolver error propagation.** `PromptContext.require()` raises
   `PromptRenderError` when a key is absent. User-supplied resolver
   bodies that raise `PromptRenderError` (or its subclasses)
   propagate out of `render` / `render_messages`. Distinguishing
   library failures from resolver failures by exception type alone
   is not currently possible; callers may inspect the message or
   raise their own subclass. A dedicated `PromptContextError` is a
   1.x candidate.

   **Mutability contract.** `PromptContext` is `frozen=True` at the
   attribute level. Neither `values` (a `dict`) nor `extras` (a
   `Mapping`) is deeply immutable. Callers MUST NOT mutate either
   after passing the context to render. Mutations during render are
   undefined behavior.

5. **Error hierarchy is rooted in `PromptRenderError` and grows only
   by adding leaves.** Public exception classes carry named,
   picklable attributes plus a `to_dict()` returning a JSON-safe
   payload.

   `PromptStrictnessError` has two leaves:
   - `PromptUnusedParameterError` — raised by `@promptstring` when a
     resolved parameter name is not a member of the template's
     placeholder set. Fix: remove the parameter or add the
     `{name}` placeholder.
   - `PromptUnreferencedParameterError` — raised by
     `@promptstring_generator` (when `strict=True`) when `str(value)`
     of a resolved parameter cannot be found in the joined generator
     output. Fix: yield a string containing the value, or remove the
     parameter.

   `PromptCompileError` currently inherits from `PromptRenderError` in
   the implementation. Callers MUST catch `PromptCompileError`
   separately at module import time, not inside per-request render
   handlers. Restructuring to a common base `PromptError` is a 2.0
   candidate.

   **Exact field sets** for each exception class beyond those tested
   by the rubric (R1 commits `exc.unused_parameters` and
   `exc.resolved_keys` on `PromptUnusedParameterError`) are deferred
   to a follow-up ADR (planned 0003).

#### Behavior

6. **Decoration is cheap.** No I/O, no async, no third-party imports
   at top level, no caller-visible side effects on import. Top-level
   imports of stdlib modules (e.g. `logging`, `time`, `inspect`,
   `dataclasses`) are permitted; lazy registry initialization
   performed by stdlib modules themselves is not considered a
   caller-visible side effect.

7. **Eager template parsing when docstring-sourced.** When a
   `@promptstring`-decorated function has a docstring template, the
   template is parsed at decoration time. `placeholders` is
   populated immediately and is immutable.

8. **Loud failure on missing template.** When a function has no
   docstring AND its return signature does not prove a `PromptSource`
   is returned, decoration raises `PromptCompileError` immediately.
   The error message names `python -OO` as a likely cause when
   `sys.flags.optimize >= 2`.

9. **Concurrent async resolution.** Sync `PromptDepends` dependencies
   run sequentially in declaration order. `AwaitPromptDepends`
   dependencies run **concurrently** via `asyncio.gather`. The first
   exception cancels the rest. There is no limit on the number of
   `AwaitPromptDepends` per function. Resolvers MUST be
   cancellation-safe and MUST NOT depend on side effects of other
   resolvers in the same render.

   **Cancellation-safe** means: tolerates `CancelledError` at any
   await point, does not suppress it, does not use finally-block
   side-effects on shared state, does not depend on sibling cleanup
   ordering.

   This is a one-way door: callers will rely on concurrency, and
   rolling back gather to sequential is a 2.0-scope breaking change.

10. **Re-entrancy.** `_PromptString` and `_PromptStringGenerator`
    instances are safe for concurrent `render` / `render_messages`
    calls. Instances hold no per-call mutable state.

11. **Strict-mode failures raise before any LLM call — with a scope
    qualifier.**

    *Scope: caller's downstream LLM call only.* If a strict-mode
    check fails at render time, the library raises before returning
    any result; the caller's downstream LLM call is never reached
    with a partially-validated prompt.

    *Scope: structural vs. best-effort detection.* For
    `@promptstring`, the placeholder-set check is structural and
    complete. For `@promptstring_generator` with `strict=True`, the
    substring-occurrence check is **best-effort** with known
    limitations (empty strings always pass; common substrings like
    `"True"` or `"1"` produce false negatives). The generator
    strict-mode mechanism is up for revision in a follow-up ADR
    (planned 0004); the current 1.0 contract documents the
    limitation rather than guaranteeing structural soundness.

    *Generator-body LLM calls are not covered by this guarantee.*
    For `@promptstring_generator`, strict validation fires after the
    generator body fully executes, so any LLM calls inside the
    generator body are out of scope. Users who need the guarantee
    that no LLM call fires before validation should not use
    generator-body LLM calls with `strict=True`.

12. **Provenance flows unchanged.** `PromptMessage.source` carries a
    `PromptSourceProvenance` exactly when the user supplied one on a
    returned `PromptSource`. The library propagates provenance
    unchanged; it does not modify, hash, or version it.

#### Imports & deps

13. **Pure stdlib runtime core.** The `promptstrings` package itself
    has zero third-party runtime dependencies and never imports any
    third-party package at module top level. Vendor-specific
    integration adapters (Pydantic, Dishka / fast-depends, OTel,
    structlog, eval frameworks, etc.) are **not** shipped as pip
    extras of this package; they live in separate distributions
    named `promptstrings-<vendor>`. See ADR 0002 for the integration
    model.

### Non-promises (explicit out-of-scope)

These are deliberate refusals. To add any of them, supersede this ADR
with a new ADR.

1. **Template caching strategy.** Implementations MAY compile-and-
   cache, parse-per-render, or memoize across instances; not part of
   the contract.
2. **Sibling dependency order.** Order in which sibling
   `PromptDepends` resolvers run beyond declaration-order, and the
   order in which `AwaitPromptDepends` tasks complete, is not
   promised.
3. **Error message text.** The string format of error messages MAY
   change between minor versions. Programmatic code MUST use named
   attributes, not parse the string.
4. **`render_messages` count, roles, or order beyond the Protocol
   minimum.** A consumer typed against `Promptstring` MUST rely only
   on "≥1 message of type `PromptMessage`."
5. **`.render()` output format on generator-backed instances.** When
   a `_PromptStringGenerator` is rendered via `.render()` (rather
   than `.render_messages()`), the join separator between yielded
   message contents is implementation-defined. Use `render_messages()`
   for predictable formatting.
6. **Provenance authoring.** The library does not compute hashes,
   does not assign versions, does not fingerprint content. Provenance
   fields are user-authored.
7. **Sync render API.** Library is async-only.
8. **Provider clients.** No LLM transports.
9. **Streaming, batching, multi-locale, prompt registries / servers,
   JSON-Schema generation for tools.** Not now, not later.
10. **Dynamic-source introspection.** If a function dynamically returns
    a `PromptSource`, `placeholders` reflects only the docstring-derived
    set.
11. **Mypy generic parameterization.** `_PromptString[T]` deferred past
    1.0; current Python type system cannot honestly express it.
12. **Method inheritance for `@promptstring`.** Decorating methods
    inherited via subclassing is not in the contract.

### Lifecycle integration map

| Phase | When | Library behavior | API surface | Promise | Non-promise |
|---|---|---|---|---|---|
| Decoration | Module import | Capture fn; if docstring is the source, parse template and compute `placeholders`; raise `PromptCompileError` if no docstring AND signature doesn't prove `PromptSource` return | `@promptstring`, `@promptstring_generator` | No I/O, no third-party imports, cheap | Caching strategy of compiled template |
| Introspection | Anytime | Expose declared placeholders and parameters without rendering | `<ps>.placeholders`, `<ps>.declared_parameters`, `isinstance(x, Promptstring)` | Stable, immutable, side-effect-free | Reflecting dynamically-returned `PromptSource`s |
| Resolution | Per render | Sync `PromptDepends` sequentially; `AwaitPromptDepends` concurrently via `gather`; first exception cancels rest | `PromptContext`, `PromptDepends`, `AwaitPromptDepends` | Sync→async→render order; instance is re-entrant; no cap on async deps | Sibling dependency order beyond rule above |
| Compilation | At decoration when possible; first render otherwise | Parse template into part list | internal | Format-spec/conversion rejected at compile | When exactly compilation occurs in dynamic-source case |
| Render | Per render | Substitute, enforce strict checks, emit `str` or `list[PromptMessage]` | `.render`, `.render_messages` | Strict failures raise before any caller-side LLM call | Specific error message text |
| Post-render | Caller-owned | `PromptMessage.source` carries `PromptSourceProvenance` if user supplied one | `PromptSource`, `PromptSourceProvenance` | Provenance flows through unchanged; immutable | Auto-hash, auto-version |
| Versioning | Out of library | User builds their own template registry on top | provenance fields | We propagate what you give us | We do not store, fetch, or fingerprint |

### DX rubric (R1–R10) — falsifiable 1.0 gates

These are the tests that gate the 1.0 tag. Failure to meet a criterion
is a 1.0 blocker.

- **R1.** Errors name the offending symbol AND the resolved keys via
  named attributes. *Test:* render `@promptstring` decorated function
  with an unused parameter; assert `exc` is a
  `PromptUnusedParameterError` with `exc.unused_parameters` and
  `exc.resolved_keys` set as tuples of strings.
- **R2.** Decoration does no I/O and imports no third-party packages.
  *Test:* `sys.modules` snapshot before and after `import promptstrings`.
- **R3.** `<promptstring>.placeholders` and `.declared_parameters`
  exist and require no awaiting.
- **R4.** Strict-mode failures produce different exception leaves for
  template path vs. generator path. *Test:* template path asserts
  `PromptUnusedParameterError` (not `PromptUnreferencedParameterError`);
  generator path asserts the reverse.
- **R5.** Decoration succeeds with no event loop running.
- **R6.** Every public exception has a `to_dict()` returning a
  JSON-safe payload. *Test:* `json.dumps(exc.to_dict())` round-trips.
- **R7.** Every public type carries a one-line class docstring.
  *Test:* `cls.__doc__ is not None` and
  `len(cls.__doc__.strip().splitlines()) == 1` after stripping.
- **R8.** Decorating a function with no docstring and no provable
  `PromptSource` return raises at decoration time, not render time.
  Fails against current `core.py` until decoration-time parsing
  delta lands.
- **R9.** `Promptstring` is `runtime_checkable`.
- **R10.** `render(None)` and `render(PromptContext())` are
  observably equivalent.

## Alternatives considered

A rejected alternative without explicit context is a preference, not
a decision. The major rejected alternatives:

- **Single decorator with a `mode` parameter** — would conflate
  template-rendered and generator-rendered semantics in one type.
  Rejected because the strict-mode mechanisms differ structurally
  (placeholder-set membership vs. substring occurrence) and the
  return types differ (single message vs. list with arbitrary roles).
  Two decorators preserve substitutability via the `Promptstring`
  Protocol while keeping the per-decorator semantics honest.

- **Lazy template parsing (parse on first render, cache)** — rejected.
  Incompatible with `placeholders` being a Protocol member callable
  without rendering. Decoration-time parsing also surfaces template
  errors at module import, where the fix is closer to the cause.

- **Sequential async resolvers (FastAPI-style `Depends`)** — rejected.
  FastAPI's sequential model exists because authentication-dependent
  authorization needs ordering. Prompt rendering has no such
  constraint; sequential costs latency external 1.0 users will not
  forgive. The cost of parallel is a documented constraint:
  resolvers must be cancellation-safe.

- **Single `PromptStrictnessError` class with two semantics** —
  rejected. The two failure modes have *different fixes*; class-level
  distinction is required for catch-blocks to be honest. Both
  inherit from `PromptStrictnessError` so users who don't care about
  the distinction can catch the parent.

- **Auto-computed provenance hashes** — rejected. A user might want
  git-SHA, content hash, or any versioning scheme of their choosing
  as the "hash" field. The library propagates what the user supplies;
  authoring would impose our scheme on them. An opt-in
  `compute_content_hash(source)` helper is a candidate for a future
  ADR.

- **`_PromptString[T]` mypy generics parametrized by resolved-context
  type** — rejected for 1.0. Python's type system cannot honestly
  express "the wrapped function's parameter set matches a TypedDict
  shape" for general functions. The generic version would produce
  false positives on legitimate code and miss real errors. Revisit
  in 2.0 if PEP advances make it tractable.

## Consequences

**Positive:**
- External 1.0 users get a stable, narrow contract: 13 promises, 12
  non-promises, knowable in one sitting.
- The `Promptstring` Protocol is the long-term extension surface;
  future "kinds of promptstring" satisfy it without breaking 1.x
  callers.
- Strict-mode failures are caught at render time, before any LLM
  call. The class of "silently dropped variable" prompt bugs ceases
  to exist (for `@promptstring`).
- Concurrent `AwaitPromptDepends` resolution gives users the
  asyncio behavior they expect from `await`-prefixed primitives.
- Pure stdlib runtime: no version conflicts with consumer
  applications' Pydantic / OTel / Dishka choices.

**Negative:**
- The concurrent-gather choice is a one-way door (Promise 9): rolling
  back to sequential is a 2.0-scope breaking change.
- The `inspect.Parameter` choice for `declared_parameters` locks the
  type for all of 1.x; a custom dataclass is 2.0-scope.
- `@promptstring_generator` strict-mode is best-effort (Promise 11);
  generator-body LLM calls are not covered. The follow-up ADR (0004)
  must decide whether to harden the mechanism or document the
  limitation permanently.
- No mypy generics in 1.0: strict-typed consumer code gets `Any`
  in places where genericized types would help.

**Neutral / follow-on:**
- Implementation deltas required before the 1.0 tag (this list is
  the work order):
  1. Decoration-time parsing delta (prerequisite for Protocol delta
     and for R8).
  2. `Promptstring` Protocol + `placeholders` / `declared_parameters`
     attributes on both concrete classes (depends on 1).
  3. Named attributes + `to_dict()` on all public exception classes
     (prerequisite for R1, R6).
  4. Leaf exceptions `PromptUnusedParameterError` and
     `PromptUnreferencedParameterError` — both atomic in one commit
     (prerequisite for R4; depends on 3).
  5. `asyncio.gather` for `AwaitPromptDepends` — atomic across all
     four call sites in `core.py`; remove the at-most-one guard
     (prerequisite for Promise 9; depends on 3). One-way door.
  6. Generator strict-mode mechanism — decision deferred to ADR 0004.
  7. R1–R10 test suite — runs only after deltas 1–6 land.
  8. Tag 1.0.

- 0.x → 1.0 migration notes:
  - **Import-semantic change:** decorating a function with no valid
    docstring now raises at module import (was deferred to first
    render). Test suites that import for unrelated paths must ensure
    every decorated function has a valid docstring.
  - **Exact-match exception catches break.** Code using
    `type(exc) == PromptStrictnessError` instead of
    `isinstance(exc, PromptStrictnessError)` will silently stop
    catching strictness errors after C2 lands. Replace with
    `isinstance`.
  - **The at-most-one `AwaitPromptDepends` guard is removed.** Code
    that relied on the guard to catch programming mistakes will no
    longer receive `PromptRenderError` for multiple async deps; both
    will run. Resolvers must be cancellation-safe.

- Companion ADR 0002 layers integration seams (`Promptstrings`
  configuration carrier, `Observer` Protocol, `PromptContext.extras`)
  on top of this baseline without retracting any promise here.

- Follow-up ADRs anticipated:
  - **0003** — error class field schema and `to_dict()` contract
    beyond R1-tested fields.
  - **0004** — generator strict-mode mechanism (keep heuristic vs.
    replace with structurally sound mechanism vs. drop).
  - Future — `compute_content_hash(source)` helper,
    `PromptIntrospectionError`, etc.

## Notes

This ADR distills `proposals/api-1.0-baseline.md` (status: proposed
prior to this ADR's acceptance). The proposal carries decision
rationale, red-team findings trace, and historical drafting notes;
this ADR carries the locked contract.

The proposal was developed via a Swarm Mode design session and
hardened through three red-team rounds (contract completeness,
execution + rollback, wording + legibility), a cross-document audit
against the integrations proposal, and a corpus-integrated audit
across all design docs. The findings catalogs are preserved in
`design/notes/red-team-round-{1,2,3}-*.md`,
`design/notes/red-team-cross-doc-consistency-audit.md`, and
`design/notes/red-team-corpus-integrated-audit.md`.

VISION context for this contract:
[`../VISION.md`](../VISION.md).
