---
title: API and DX baseline for promptstrings 1.0
status: accepted
created: 2026-04-26
updated: 2026-04-26
---

# API and DX baseline for promptstrings 1.0

> **Promoted to ADR.** This proposal has been distilled into
> [`../decisions/0001-api-and-dx-baseline-for-1.0.md`](../decisions/0001-api-and-dx-baseline-for-1.0.md),
> which carries the locked 1.0 contract. This proposal is preserved
> as historical context — it includes the full red-team-cycle trace,
> rationale, and decision drafting notes. For the canonical contract,
> read the ADR.

## Purpose

Define what `promptstrings` 1.0 promises, what is explicitly out of scope,
which lifecycle phases of an LLM application it integrates into, and how
that integration looks at the API level. This is the design baseline that
must be approved before a 1.0 tag.

Audience: external public users from 1.0 onward. Every promise below is a
public SemVer contract. Every non-promise is a deliberate refusal.

**Companion proposal:** the extension surface for 1.0 — `Promptstrings`
configuration carrier, `Observer` Protocol, `PromptContext.extras`, and
per-vendor adapter integration patterns — is specified in
[`api-1.0-integrations.md`](api-1.0-integrations.md). That proposal
layers on top of this baseline and does not retract anything from it.

**Vocabulary:** load-bearing terms used in this proposal (Promptstring
Protocol, decoration time, render time, render path, render call,
strict mode, provenance, cancellation safety, etc.) are defined
canonically in [`design/glossary.md`](../glossary.md). This proposal
does not redefine them.

This proposal is the output of a Swarm Mode design session. The decisions
below were each contested by named critics; rationale lives inline.

## Promises (1.0 contract)

> **Normative language:** The keywords MUST, MUST NOT, MAY, SHOULD, and
> SHOULD NOT in this section and the Non-promises section are used in
> conformance with [RFC 2119](https://www.rfc-editor.org/rfc/rfc2119).

### API surface

1. **Two decorators only.** The package exports exactly two
   decorators: `@promptstring` and `@promptstring_generator`. New
   decorators in 1.x will only be added if they satisfy the
   `Promptstring` Protocol. The exact callable type of these
   decorators is **not** part of the contract; users may rely on
   `@promptstring` and `promptstring(fn)` working as decorator and
   call expression respectively, but not on `type(promptstring)`
   being any specific class. The companion proposal
   ([`api-1.0-integrations.md`](api-1.0-integrations.md) Promise I-1)
   binds these names to methods of a default `Promptstrings()`
   singleton instance; users who construct their own `Promptstrings`
   instance decorate via `ps.promptstring` instead.

2. **`Promptstring` Protocol.** The package exports a runtime-checkable
   `Promptstring` Protocol. The class skeleton (bodies are `...` —
   implementations must satisfy the signatures):

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

   The `Parameter` type in `declared_parameters` is `inspect.Parameter`
   from the standard library. This is the 1.0-locked type. Replacing it
   with a custom dataclass is a **2.0-scope breaking change** — callers
   who type-annotate against `inspect.Parameter` or access
   `inspect.Parameter`-specific attributes would break. This change
   cannot be made in a 1.x minor or patch release. Users who iterate
   `declared_parameters` may rely on the `inspect.Parameter` interface
   (`name`, `default`, `annotation`, `kind`) for the entire 1.x line.

   The Protocol is the long-term extension surface. Concrete classes are
   implementation; user code should type against the Protocol, not against
   `_PromptString` or `_PromptStringGenerator`.

   **Protocol is append-only in 1.x.** The `Promptstring` Protocol may
   gain new members in minor 1.x releases, but existing members may not
   be removed or narrowed. Removing or narrowing any Protocol member
   would break implementations that satisfy the current Protocol, and is
   a 2.0-scope breaking change. "New decorators must satisfy the
   `Promptstring` Protocol" (Promise 1) means they must implement all
   members present at the time of their introduction.

   **Minimum `PromptMessage` schema.** Every `PromptMessage` returned by
   `render_messages` carries exactly these fields as part of the 1.0
   contract:
   - `role: str` — the message role (e.g. `"system"`, `"user"`,
     `"assistant"`). The set of valid role strings is not constrained by
     this library; it is governed by the LLM provider.
   - `content: str` — the rendered message body. Never empty; the library
     guarantees at least one character.
   - `source: PromptSourceProvenance | None` — present exactly when the
     user supplied a `PromptSource` with a non-`None` `provenance` field;
     `None` otherwise.

   `PromptSourceProvenance` carries `source_id`, `version`, `hash`, and
   `provider_name`, all `str | None`. The library propagates whatever the
   user supplies; it does not fill, validate, or modify any field.

   > **Implementation delta (1.0 blocker):** Neither `_PromptString` nor
   > `_PromptStringGenerator` currently exposes `placeholders` or
   > `declared_parameters` as attributes, and the `Promptstring` Protocol
   > class does not exist in `core.py`. Both must be added before the 1.0
   > tag. See the Promotion to ADR section below.

3. **`strict` is a public parameter on both decorators.**

   - `@promptstring(strict=True)` — default. Raises
     `PromptUnusedParameterError` when a resolved parameter is not
     consumed by the template.
   - `@promptstring_generator(strict=False)` — default. When `strict=True`
     is passed explicitly, raises `PromptUnreferencedParameterError` when
     a resolved parameter value cannot be found in the rendered output.

   The asymmetric defaults are intentional: template-based promptstrings
   can be checked structurally (placeholder membership), so strict is the
   safe default. Generator-based promptstrings are checked by a
   best-effort heuristic (see Promise 11 note on generators); strict is
   opt-in because the heuristic can produce false positives. Callers who
   switch from `@promptstring` to `@promptstring_generator` must
   explicitly pass `strict=True` if they want validation.

4. **`PromptContext` is the only value-injection mechanism.** No globals,
   no thread-locals, no env-style fallback. One bag, one rule.
   Passing `context=None` to `render` or `render_messages` is exactly
   equivalent to passing an empty `PromptContext()`. This equivalence is
   part of the 1.0 contract and will not change in 1.x.

   **Canonical type definition.** The 1.0 dataclass shape is:

   ```python
   from collections.abc import Mapping
   from dataclasses import dataclass, field
   from typing import Any

   @dataclass(frozen=True)
   class PromptContext:
       values: dict[str, Any] = field(default_factory=dict)
       extras: Mapping[str, Any] = field(default_factory=dict)
   ```

   Both fields are part of the 1.0 contract. This is the single
   authoritative definition of `PromptContext`; the integrations
   proposal does not redefine it.

   **`values` semantics.** User-supplied per-render values, addressed
   by string keys via resolver code (`ctx.require("user_id")`,
   `ctx.get("locale")`). The library reads `values` during dependency
   resolution.

   **`extras` semantics.** A documented namespace for framework-supplied
   handles (DI containers, request sessions, tracer references,
   eval-collector sinks). The library does not interpret any key in
   `extras`; it does not read, write, or enumerate `extras` itself.
   The type is `Mapping[str, Any]`, deliberately read-only at the type
   level. Convention (informative, not enforced): keys for framework
   state SHOULD use a single leading underscore (e.g.,
   `"_dishka_container"`, `"_otel_tracer"`). See
   [`api-1.0-integrations.md`](api-1.0-integrations.md) Promise I-3
   for the rationale and the integration patterns that motivated the
   field.

   **Resolver error propagation:** `PromptContext.require()` raises
   `PromptRenderError` when a key is absent. Any user-supplied resolver
   body that calls `require()` or raises its own `PromptRenderError`
   subclass will cause the same exception to propagate out of `render()`
   or `render_messages()`. A caller catching `PromptRenderError` after a
   render call cannot currently distinguish a library-level failure from a
   resolver-level failure using exception type alone. To distinguish them,
   callers may inspect the exception message or raise a custom subclass
   from within their resolver. A dedicated `PromptContextError` (separate
   from `PromptRenderError`) is a candidate for a future minor release if
   caller feedback indicates the disambiguation is needed.

   **Mutability contract.** `PromptContext` is frozen at the attribute
   level (`frozen=True` dataclass), but neither `values` (a `dict`) nor
   `extras` (a `Mapping`) is deeply immutable. Callers **MUST NOT**
   mutate either `context.values` or the underlying `context.extras`
   mapping after passing the context to any `render` or
   `render_messages` call. The library does not copy either at
   resolution entry; mutations concurrent with an active render are
   undefined behavior and will violate the re-entrancy promise
   (Promise 10). A future 1.x patch MAY add defensive copies at
   resolution entry; this will not be a breaking change.

5. **Error hierarchy is rooted in `PromptRenderError` and grows only by
   adding leaves.** Public exception classes carry named, picklable
   attributes plus a `to_dict()` returning a JSON-safe payload.

   **Inheritance note — `PromptCompileError`:** `PromptCompileError`
   currently inherits from `PromptRenderError` in the implementation.
   *Terminology: decoration time = module import time, when the
   `@promptstring` decorator is applied. These terms are used
   interchangeably throughout this document.*
   This means a blanket `except PromptRenderError` in a request handler
   will also catch decoration-time (import-time) errors that should
   crash the process, not be silently swallowed. Callers **MUST** catch
   `PromptCompileError` separately — at module import time, not inside
   per-request render handlers. The hierarchy is acknowledged here as a
   known ergonomic limitation; restructuring to a common base `PromptError`
   (with `PromptRenderError` and `PromptCompileError` as siblings) is a
   candidate for 2.0.

   `PromptStrictnessError` has two leaves:
   - `PromptUnusedParameterError` — raised by `@promptstring` when a
     resolved parameter name is not a member of the template's
     placeholder set (i.e., the template did not consume the parameter).
     Fix: remove the parameter from the function signature or add the
     corresponding `{name}` placeholder to the template.
   - `PromptUnreferencedParameterError` — raised by
     `@promptstring_generator` (when `strict=True`) when `str(value)` of
     a resolved parameter cannot be found in the joined generator output.
     Fix: yield a string that contains the resolved value, or remove the
     parameter from the function signature. Committed named attributes
     (part of the 1.0 contract): `exc.unreferenced_parameters` (tuple of
     parameter name strings that were not found in the output) and
     `exc.resolved_keys` (tuple of all parameter names that were resolved,
     mirroring the same field on `PromptUnusedParameterError` for
     symmetry). These attributes are testable in R4's generator-path
     assertion.

   These two failure modes have different fixes; class-level distinction
   is required for catch-blocks to be honest.

   > **Implementation delta (1.0 blocker):** `core.py` currently has
   > neither class — both paths raise `PromptStrictnessError` directly.
   > Both leaf classes must be added and wired to their respective code
   > paths before the 1.0 tag. DX test R4 is unpassable until they exist.
   > See the Promotion to ADR section below.

### Behavior

6. **Decoration is cheap.** No I/O, no async, no third-party imports
   at top level, no caller-visible side effects on import. Top-level
   imports of stdlib modules (e.g. `logging`, `time`, `inspect`,
   `dataclasses`) are permitted; lazy registry initialization
   performed by stdlib modules themselves (such as
   `logging.getLogger` populating the logger registry) is not
   considered a caller-visible side effect.

7. **Eager template parsing when docstring-sourced.** When a
   `@promptstring`-decorated function has a docstring template, the
   template is parsed at decoration time. `placeholders` is populated
   immediately and is immutable.

8. **Loud failure on missing template.** When a function has no docstring
   AND its return signature does not prove a `PromptSource` is returned,
   decoration raises `PromptCompileError` immediately. The error message
   names `python -OO` as a likely cause when `sys.flags.optimize >= 2`.

   **`PromptCompileError` cause disambiguation:** `PromptCompileError`
   currently does not have subtypes — it fires for three distinct causes:
   (a) genuinely missing docstring, (b) docstring stripped by `python -OO`
   or a build system, (c) template syntax error (unsupported format-spec
   or conversion). Since error message text is not promised (Non-promise
   3), programmatic callers cannot distinguish these causes from the
   string alone. A `PromptMissingSourceError` subtype (for cases a and b)
   and a `PromptTemplateSyntaxError` subtype (for case c) are planned for
   a minor 1.x release. Until those subtypes exist, callers who need
   programmatic disambiguation should inspect `sys.flags.optimize` or
   verify docstring presence at their own import time.

9. **Concurrent async resolution.** Sync `PromptDepends` dependencies run
   sequentially in declaration order. `AwaitPromptDepends` dependencies run
   **concurrently** via `asyncio.gather`. The first exception cancels
   the rest. **There is no limit** on the number of `AwaitPromptDepends`
   per function. (This replaces the current "at most one" runtime
   restriction, which was a placeholder, not a contract.)

   **This is a one-way door.** Once concurrent gather semantics are
   shipped in 1.0, rolling back to sequential `AwaitPromptDepends`
   execution is a 2.0-scope breaking change. Callers that relied on
   concurrency (e.g. concurrent DB + cache fetches) would suffer latency
   regressions; callers whose resolvers were not cancellation-safe and
   accidentally worked under sequential execution would start failing.
   The concurrent semantics are permanently part of the 1.x contract.

   > **Implementation delta (1.0 blocker — C1 delta):** `core.py` currently
   > enforces the at-most-one restriction at `_resolve_dependencies` and in
   > both `render` / `render_messages` on `_PromptString` and
   > `_PromptStringGenerator`. The guard must be removed and replaced with
   > `asyncio.gather` of all `AwaitPromptDepends` dependencies before the
   > 1.0 tag. **This change must be applied atomically across all four call
   > sites** (`_resolve_dependencies`, `_PromptString.render`,
   > `_PromptString.render_messages`, `_PromptStringGenerator.render_messages`);
   > updating any subset leaves the library in a broken intermediate state.
   > Until that change lands, this promise is a design target, not a live
   > guarantee. See the C1 delta in the Promotion to ADR section below for
   > the full two-pass loop and merge description.

10. **Re-entrancy.** `_PromptString` and `_PromptStringGenerator`
    instances are safe for concurrent `render` / `render_messages` calls.

11. **Strict-mode failures raise before any LLM call — with a scope
    qualifier.** The library never returns a partially-rendered prompt.
    If strict-mode validation fails, the caller's downstream LLM call
    site is never reached.

    **Scope: caller's downstream LLM call only.** "Before any LLM call"
    refers specifically to the *caller's downstream LLM call* — the call
    the caller would make after `render()` returns. It does not apply to
    LLM calls made inside resolver bodies or inside the wrapped function
    itself. Async resolvers execute during the Resolution phase (see
    Lifecycle integration map); any side effects they produce — including
    network requests, DB queries, or LLM calls within the resolver body
    — occur before strict validation runs. On the dynamic-source path,
    the wrapped function also runs before strict validation. A user who
    reads this promise as "if validation fails, nothing has happened yet"
    is incorrect; it means only "the caller's next LLM call will not
    fire."

    **Scope: structural vs. best-effort detection.**

    - For `@promptstring` (`strict=True` by default): the check is
      **structural** — it tests whether each resolved parameter name is a
      member of the template's placeholder set. This is sound and covers
      all inputs.
    - For `@promptstring_generator` (`strict=False` by default; opt-in
      via `strict=True`): the check is **best-effort** — it tests whether
      `str(value)` appears as a substring of the joined message content.
      This heuristic has known gaps: a value whose string representation
      is a common substring (e.g. `"True"`, `"1"`, `""`) will not raise
      even if the parameter was not intentionally referenced. The
      guarantee that strict failures raise before any LLM call applies
      only when the heuristic fires; it does not guarantee detection of
      all unreferenced parameters in generator mode.

    **Generator-body LLM calls are not covered by this guarantee:** For `@promptstring_generator` with `strict=True`, strict
    validation fires *after* the generator body has fully executed and
    all its `await` points have completed. If the generator body makes
    LLM calls (a common pattern: generate prompt parts, call LLM for
    context enrichment, yield the enriched content), those calls have
    already returned by the time strict validation raises
    `PromptUnreferencedParameterError`. This ordering gap exists
    independently of the heuristic's false-negative problem — even a
    structurally sound generator strict mechanism would not close it as
    long as strict validation occurs after generator execution. Callers
    who need the guarantee that no LLM call fires before validation
    should not use generator-body LLM calls with `strict=True`.

    > **Implementation delta (1.0 blocker):** A structurally sound
    > generator strict check (e.g., explicit placeholder annotation in the
    > generator protocol, or an opt-in `yield PARAM(name)` sentinel) should
    > replace the substring heuristic before 1.0 if the best-effort
    > qualification is not acceptable to users. See the Promotion to ADR
    > section below.

12. **Provenance flows unchanged.** `PromptMessage.source` carries a
    `PromptSourceProvenance` exactly when the user supplied one on a
    returned `PromptSource`. The library propagates provenance unchanged;
    it does not modify, hash, or version it.

### Imports & deps

13. **Pure stdlib runtime core.** The `promptstrings` package itself
    has zero third-party runtime dependencies and never imports any
    third-party package at module top level. Vendor-specific
    integration adapters (Pydantic serialization, Dishka /
    fast-depends DI helpers, OTel observers, structlog observers,
    eval-framework adapters, etc.) are **not** shipped as pip extras
    of this package; they live in separate distributions named
    `promptstrings-<vendor>` (e.g. `promptstrings-pydantic`,
    `promptstrings-dishka`). See
    [`api-1.0-integrations.md`](api-1.0-integrations.md) for the
    canonical integration model.

## Non-promises (explicit out-of-scope)

These are deliberate refusals. They will not be quietly added later — to
add any of them, supersede this baseline with a new ADR.

1. **Template caching strategy.** Implementations may compile-and-cache,
   parse-per-render, or memoize across instances; this is not part of the
   contract.

2. **Sibling dependency order.** The order in which sibling
   `PromptDepends` dependencies run beyond the declaration-order rule above,
   and the order in which `AwaitPromptDepends` tasks complete, is not
   promised. The resolver callable inside each dependency MUST be
   cancellation-safe and MUST NOT depend on side effects of other
   resolvers in the same render.

   **What "cancellation-safe" means:** when `asyncio.gather` raises
   (because one resolver raised), the remaining tasks are cancelled.
   A cancellation-safe resolver must tolerate receiving
   `asyncio.CancelledError` at any `await` point without corrupting
   shared state. Specifically: do not modify shared mutable objects in a
   `finally` block that runs on cancellation; do not suppress
   `CancelledError` (re-raise it); and do not rely on cleanup logic in a
   sibling resolver completing before your cancellation fires. The library
   performs no additional cleanup on cancellation beyond what
   `asyncio.gather` provides.

3. **Error message text.** The string format of error messages MAY
   change between minor versions. Programmatic code MUST use the named
   attributes, not parse the string.

4. **`render_messages` count, roles, or order beyond the Protocol
   minimum.** A consumer typed against `Promptstring` MUST rely only on
   "≥1 message of type `PromptMessage`."

5. **`.render()` output format on generator-backed instances.** When
   `.render()` is called on a `_PromptStringGenerator`-backed promptstring,
   the messages produced by `render_messages` are joined into a single
   string. The exact join separator (`"\n\n"`) is not promised and MAY
   change between minor versions. Callers who need predictable formatting
   MUST call `render_messages()` directly and format the messages
   themselves.

6. **Provenance authoring.** The library does not compute hashes, does
   not assign versions, does not fingerprint content. Provenance fields
   are user-authored; we propagate.

7. **Sync render API.** The library is async-only. Users wrap with
   `asyncio.run` if needed.

8. **Provider clients.** No LLM transports.

9. **Streaming, batching, multi-locale, prompt registries / servers,
   JSON-Schema generation for tools.** Not now, not later. Compose with
   whatever you already use.

10. **Dynamic-source introspection.** If a function dynamically returns a
    `PromptSource` at render time, `placeholders` reflects only the
    docstring-derived set. The Protocol does not promise to introspect
    dynamic sources.

11. **Mypy generic parameterization.** `_PromptString[T]` and similar
    generics are deferred past 1.0. Python's type system cannot honestly
    express "the wrapped function's parameter set matches a TypedDict
    context" for general functions. Half-correct generics mislead more
    than they help.

12. **Method inheritance for `@promptstring`.** Decorating methods that
    are inherited via subclassing is not in the contract; users who do
    this are outside the supported surface.

## Lifecycle integration map

| Phase | When | Library behavior | API surface | Promise | Non-promise |
|---|---|---|---|---|---|
| **Decoration** | Module import | Capture fn; if docstring is the source, parse template and compute `placeholders`; raise `PromptCompileError` if no docstring AND signature doesn't prove a `PromptSource` is returned | `@promptstring`, `@promptstring_generator` | No I/O, no third-party imports, cheap | Caching strategy of compiled template |
| **Introspection** | Anytime | Expose declared placeholders and parameters without rendering | `<ps>.placeholders`, `<ps>.declared_parameters`, `isinstance(x, Promptstring)` | Stable, immutable, side-effect-free | Reflecting dynamically-returned `PromptSource`s |
| **Resolution** | Per render | Walk signature; sync `PromptDepends` dependencies sequentially; `AwaitPromptDepends` dependencies concurrently via `gather`; first exception cancels rest | `PromptContext`, `PromptDepends`, `AwaitPromptDepends` | Sync→async→render order; instance is re-entrant; no cap on async deps | Sibling dependency order beyond rule above |
| **Compilation** | At decoration when possible; first render otherwise | Parse template into part list | internal | Format-spec/conversion rejected at compile | When exactly compilation occurs in dynamic-source case |
| **Render** | Per render | Substitute, enforce strict checks, emit `str` or `list[PromptMessage]` | `.render`, `.render_messages` | Strict failures raise before any caller-side LLM call | Specific error message text |
| **Post-render** | Caller-owned | `PromptMessage.source` carries `PromptSourceProvenance` if user supplied one | `PromptSource`, `PromptSourceProvenance` | Provenance flows through unchanged; immutable | Auto-hash, auto-version |
| **Versioning** | Out of library | User builds their own template registry on top | provenance fields | We propagate what you give us | We do not store, fetch, or fingerprint |

## DX rubric (falsifiable, both audiences)

Each criterion is a test the library must pass before 1.0. Failure to
meet a criterion is a 1.0 blocker.

- **R1.** `PromptUnusedParameterError` names the offending resolved
  parameter(s) via named attributes, not just message text.
  *Test:* decorate a `@promptstring` function with template `"{a}"` and
  a second resolved parameter `b`; call `render()`; assert that the
  raised `PromptUnusedParameterError` has an `exc.unused_parameters`
  attribute that is a tuple containing `"b"`, and that
  `exc.resolved_keys` is a tuple containing both `"a"` and `"b"`.
  (Note: the exact attribute names `unused_parameters` and
  `resolved_keys` on `PromptUnusedParameterError` are committed here as
  part of the 1.0 contract; the "exact field set deferred" non-promise
  in the *Out of scope* section applies only to exception classes not
  tested by R1–R10.)

- **R2.** Decoration does no I/O and imports no third-party packages.
  *Test:* `sys.modules` snapshot before and after `import promptstrings`;
  assert no third-party packages were imported.

- **R3.** `<promptstring>.placeholders` and `.declared_parameters` exist
  and require no awaiting.
  *Test:* type and runtime test against a decorated function.

- **R4.** Strict-mode failures produce different exception leaves for
  "unused parameter" vs "unreferenced parameter," and each leaf is
  raised from its respective code path (not interchangeably).
  *Test 1 — template path:* render a `@promptstring` function with an
  extra resolved parameter not in the template; assert
  `isinstance(exc, PromptUnusedParameterError)` and that `exc` is NOT
  an instance of `PromptUnreferencedParameterError`.
  *Test 2 — generator path:* render a `@promptstring_generator(strict=True)`
  function with a resolved parameter value whose `str()` does not appear
  in the yielded output; assert `isinstance(exc, PromptUnreferencedParameterError)`
  and that `exc` is NOT an instance of `PromptUnusedParameterError`.
  (R4 depends on the C2 delta being landed; see the implementation
  ordering in the Promotion to ADR section.)

- **R5.** Decoration succeeds with no event loop running.
  *Test:* import a module containing `@promptstring`-decorated functions
  in a script with no asyncio context; assert no runtime error.

- **R6.** Every public exception has a `to_dict()` returning a JSON-safe
  payload.
  *Test:* `json.dumps(exc.to_dict())` round-trips.

- **R7.** Every public type (`Promptstring` Protocol, `PromptContext`,
  `PromptDepends`, `AwaitPromptDepends`, all error classes) has a
  one-line class docstring.
  *Test (automatable):* for each class exported from
  `promptstrings.__all__` (or the public surface), assert
  `cls.__doc__ is not None and len(cls.__doc__.strip().splitlines()) == 1`
  (i.e., exactly one non-empty line after stripping leading/trailing
  whitespace). This formulation rejects multi-line docstrings and
  pathological all-whitespace docstrings equally, and can run in CI
  without interactive `help()` output.

- **R8.** Decorating a function with no docstring and no provable
  `PromptSource` return raises at decoration time, not render time.
  *Test:* import a module containing such a function; assert
  `PromptCompileError` is raised at import time, not when `render()` is
  called. (R8 will fail against current `core.py` and will fail if run
  before the decoration-time parsing delta lands — see Step 1 in the
  implementation ordering under Promotion to ADR.)

- **R9.** `Promptstring` is `runtime_checkable`.
  *Test:* `isinstance(decorated_fn, Promptstring)` is `True`.

- **R10.** Passing `context=None` is exactly equivalent to passing an
  empty `PromptContext()` (Promise 4).
  *Test:* render the same `@promptstring` function twice with identical
  resolved parameters — once calling `render(None)` and once calling
  `render(PromptContext())`; assert the two return values are equal and
  no exception is raised in either call.

## Decision rationale (why these and not others)

The major decisions in this baseline each rejected at least one
alternative. Recording the rejected paths so this baseline can be
defended later.

### Why a Protocol, not just two decorators

Rejected: "the two decorators are the API; users call them directly,
done." This violates substitutability — `_PromptString.render_messages`
returns exactly one system-role message; `_PromptStringGenerator` returns
multiple messages with arbitrary roles. A user typed against
`_PromptString` cannot drop in a `_PromptStringGenerator` without
rewriting call sites. The Protocol resolves this by stating the honest
minimum contract both implementations satisfy, and by becoming the
long-term extension surface for any future "kind of promptstring."

### Why decoration-time parsing, not lazy

Rejected: "parse on first render, cache." Lazy parsing is incompatible
with `placeholders` being a Protocol member callable without rendering.
Decoration-time parsing also surfaces template errors at module import,
where the fix is closer to the cause.

The `python -OO` failure mode (docstrings stripped at bytecode optimize
level 2) is handled by detecting the symptom — `__doc__ is None` — and
raising at decoration time with a message that names `-OO` as a likely
cause. Detect-by-symptom rather than by-cause covers also frozen apps
and exotic build systems where docstrings can disappear.

### Why concurrent async resolvers, not sequential

Rejected: "sequential in declaration order, like FastAPI's `Depends`."
FastAPI's sequential model exists because authentication-dependent
authorization needs ordering. Prompt rendering has no such constraint —
fetching from DB, cache, and vector store are independent. Sequential
costs latency users will not forgive in 1.0+. The cost of parallel is a
documented constraint: resolvers must be cancellation-safe.

The current "at most one `AwaitPromptDepends`" limit was a runtime
guard against unspecified semantics, not a contract. Removing it before
1.0 is required (per user direction), and removing it correctly means
specifying the new contract — concurrent gather — explicitly.

### Why split `PromptStrictnessError` into two leaves

Rejected: "one error class, two semantics, distinguish via the message."
The two failure modes have *different fixes*: a `PromptUnusedParameterError`
is fixed by removing the parameter or referencing it in the template; a
`PromptUnreferencedParameterError` is fixed by yielding a string that
contains the value. Different fixes deserve different exception classes.
Both still inherit from `PromptStrictnessError` so users who don't care
about the distinction can catch the parent.

### Why we don't auto-compute provenance hashes

Rejected: "if the user supplies content but no hash, we sha256 it." A
user might want git-SHA-of-the-template-file, content hash, or any
versioning scheme of their choosing as the "hash" field. Auto-filling
imposes our scheme on them. The library's job is to propagate what the
user supplies; an opt-in `compute_content_hash(source)` helper can live
in `promptstrings.utils` for users who want the convenience.

### Why no mypy generics for 1.0

Rejected: `_PromptString[T]` parametrized by the resolved-context type.
Python's type system cannot honestly express "the wrapped function's
parameter set matches a TypedDict shape" for general functions. The
generic version would produce false positives on legitimate code and
miss real errors. We commit to revisiting in 2.0 if PEP advances make
it tractable.

## Out of scope of *this proposal* (deliberate deferrals)

These are detail decisions that flow from the locked-in shape above.
They will be drafted as separate ADRs but are not 1.0 blockers.

- Exact field set on each error class's named-attributes API, **except**
  for the attributes explicitly committed in the DX rubric (R1 commits
  `exc.unused_parameters` and `exc.resolved_keys` on
  `PromptUnusedParameterError` as part of the 1.0 contract). Deferred
  field sets on classes not tested by R1–R10 will be specified in a
  follow-up ADR. (`inspect.Parameter` reuse is now locked for 1.0;
  custom dataclass is a 2.0 candidate.)
- A `promptstrings.utils.compute_content_hash(source)` helper as opt-in
  convenience.
- Whether to add an explicit `PromptIntrospectionError` for dynamic-source
  introspection attempts, or simply return the docstring-derived set
  with documentation.

## Promotion to ADR

### Implementation delta index

Inline blockquotes remain attached to their respective promises; this
table is a single-glance index for implementers.

| Delta | Promise | What changes | Inline blockquote? |
|-------|---------|--------------|--------------------|
| Protocol + attributes delta | Promise 2 | Add `Promptstring` Protocol; add `placeholders` / `declared_parameters` to both concrete classes | yes |
| C1 delta (gather) | Promise 9 | Replace at-most-one guard with `asyncio.gather`; atomic across 4 sites | yes |
| C2 delta (leaf exceptions) | Promise 5 | Add `PromptUnusedParameterError` and `PromptUnreferencedParameterError` leaf classes | yes |
| C4 delta (generator strict) | Promise 11 | Evaluate / replace substring heuristic | yes |
| L1 delta (catch guidance) | Promise 5 / Promise 8 | Surface `PromptCompileError` catch-at-import-time rule in all user-facing docs | no — doc-only delta |

When this proposal is accepted:

1. Distill into `design/decisions/0001-api-and-dx-baseline-for-1.0.md`.
   Drop the rationale section into the ADR's *Alternatives* and
   *Consequences* sections. Drop the rubric R1–R10 in full.
2. Move this proposal file to `design/notes/` as historical context, or
   delete it.
3. Open follow-up ADR drafts for each item under *Out of scope of this
   proposal* above.
4. Implement the deltas (all are 1.0 blockers):
   - Add the `Promptstring` Protocol to `core.py` (runtime-checkable;
     members: `placeholders`, `declared_parameters`, `render`,
     `render_messages`).
   - Add `placeholders: frozenset[str]` and
     `declared_parameters: Mapping[str, inspect.Parameter]` to both
     `_PromptString` and `_PromptStringGenerator`.
   - Move template parsing to decoration time for the docstring-source
     path; add `python -OO` detection (detect `__doc__ is None`).
   - **Remove the at-most-one `AwaitPromptDepends` guard and replace with
     `asyncio.gather`** (C1 delta — Promise 9). This is a **structural
     rewrite of `_resolve_dependencies`**, not a one-line patch. It
     requires: (a) a two-pass loop — collect `PromptDepends` dependencies
     and run them sequentially, then collect all `AwaitPromptDepends`
     dependencies and dispatch them as concurrent tasks via
     `asyncio.gather`; (b) removing the `awaited_dependency_count`
     return value and all four `> 1` guard checks across
     `_resolve_dependencies`, `_PromptString.render`,
     `_PromptString.render_messages`, and
     `_PromptStringGenerator.render_messages`; and (c) merging the
     gathered results back into the resolved dict. **This change must be
     applied atomically across all four call sites.** Updating any
     subset leaves the library in a broken intermediate state where
     multiple async resolvers run sequentially without a guard and
     without the promised concurrency. **This delta is irreversible once
     shipped:** callers who relied on concurrency (e.g. concurrent
     DB + cache fetches) would suffer latency regressions on rollback;
     callers whose resolvers were not cancellation-safe and accidentally
     worked under sequential execution would start failing. Rolling back
     gather to sequential is a 2.0-scope breaking change.
   - **Add `PromptUnusedParameterError`** as a leaf of
     `PromptStrictnessError`; wire it to the `_PromptString`
     unused-parameter check path (lines 190–196 and 210–216 in current
     `core.py` — the `extras = sorted(...)` block that flags resolved
     parameters absent from the template's placeholder set; unrelated
     to `PromptContext.extras`).
   - **Add `PromptUnreferencedParameterError`** as a leaf of
     `PromptStrictnessError`; wire it to the `_PromptStringGenerator`
     strict-check path (lines 274–285 in current `core.py`).
     (C2 delta — Promise 5.)
   - **Evaluate generator strict-mode heuristic** (C4 delta — Promise 11).
     The substring-containment check is best-effort and has known gaps for
     values whose `str()` is a common substring (e.g. `""`, `"True"`,
     `"1"`). Either (a) document the best-effort limitation as part of the
     1.0 contract (already done in Promise 11 above), or (b) replace with
     a structurally sound mechanism before tagging 1.0. If (a), ensure
     the release notes call this out prominently.
   - Add named attributes and `to_dict()` to all public exception classes.
   - Ensure `PromptCompileError` catch guidance appears in all user-facing
     documentation (catch at import time, not inside request handlers).
     (L1 delta.)

   **Required implementation order (prerequisites enforced):**

   The deltas above are not independent. The following sequence is the
   minimum safe order; landing them out of order creates broken
   intermediate states:

   ```
   Step 1: Decoration-time parsing delta
           (prerequisite for the Protocol delta and for R8)
   Step 2: Protocol delta + placeholders/declared_parameters
           (depends on Step 1)
   Step 3: Named attributes + to_dict() on all exception classes
           (prerequisite for R1 and R6)
   Step 4: C2 delta (leaf exceptions: PromptUnusedParameterError +
           PromptUnreferencedParameterError) — both leaves must land
           atomically in the same commit
           (prerequisite for R4; depends on Step 3)
   Step 5: C1 delta (gather) — all 4 sites must land atomically in
           the same commit (see note above)
           (prerequisite for Promise 9; independent of Step 4 but
           both depend on Step 3)
   Step 6: C4 delta (generator strict evaluation)
   Step 7: R1–R10 test suite — run only after all above deltas are
           landed; R8 will fail if run before Step 1, and R4 will
           fail if run before Step 4
   Step 8: Tag 1.0
   ```

   Steps 4 and 5 are independent of each other but both depend on
   Step 3. Steps 2 and 3 are independent but both depend on Step 1.

   - Land tests for R1–R10 (after all deltas above — see Step 7).
5. Tag 1.0 only after all R1–R10 tests pass and all deltas above are
   implemented.

### 0.x → 1.0 migration notes

Three behavior changes in 1.0 break silent assumptions in 0.x code:

1. **Import-semantic change (decoration-time parsing).** In 0.x,
   decorating a function with a missing or invalid docstring does not
   raise at import time — the error is deferred to the first `render()`
   call. In 1.0, `PromptCompileError` fires at decoration time (module
   import). Test suites that import modules containing
   `@promptstring`-decorated functions to test *other* code paths will
   fail at collection time if any decorated function has no valid
   docstring. Mocking the render call does not help — the error fires
   before any mock can be installed. Fix: ensure every `@promptstring`-
   decorated function has a valid docstring, or catch `PromptCompileError`
   at the import site (not inside request handlers).

2. **`type(exc) == PromptStrictnessError` exact-match catches silently
   break.** After the C2 delta, `PromptStrictnessError` is never raised
   directly — only its leaf subclasses (`PromptUnusedParameterError`,
   `PromptUnreferencedParameterError`) are. Code that uses exact-type
   equality (`type(exc) == PromptStrictnessError`) instead of `isinstance`
   will silently stop catching strictness errors. Fix: replace all
   `type(exc) ==` guards with `isinstance(exc, PromptStrictnessError)`.

3. **`AwaitPromptDepends` at-most-one guard is removed.** In 0.x, using
   more than one `AwaitPromptDepends` on a single function raises a
   `PromptRenderError` at render time. In 1.0, multiple
   `AwaitPromptDepends` dependencies run concurrently via `asyncio.gather`.
   Code that relied on the guard to catch a programming mistake will no
   longer receive that error; both will run. The resolver callable inside
   each dependency must be cancellation-safe (see Non-promise 2).

## History

Developed via Swarm Mode design session on 2026-04-26 (critics: Liskov,
Ronacher, Schlawack; evangelist: Ramírez). Refined through three red-team
rounds; this document is the final round-3 repair target.
