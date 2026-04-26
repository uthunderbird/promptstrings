# Glossary

Shared vocabulary for design discussions about `promptstrings`. When a
term in this glossary appears in a design doc, it means *this specific
thing*, not the generic English usage.

Terms are alphabetical within each section. Add new entries as they
become load-bearing in conversation; remove entries that fall out of use.

## Library concepts

- **Promptstring Protocol** — the runtime-checkable `Protocol` exported
  by the library that defines the minimum contract any "promptstring"
  satisfies: `placeholders`, `declared_parameters`, `render`,
  `render_messages`. The long-term extension surface; user code should
  type against this Protocol, not against concrete classes.

- **Concrete decorator** — `@promptstring` or `@promptstring_generator`.
  The two public ways to construct an object that satisfies the
  Promptstring Protocol. New concrete decorators will only be added if
  they also satisfy the Protocol.

- **Decoration time** — the moment a `@promptstring`-decorated function
  is processed at module import. This is when the library captures the
  function, parses the docstring template if present, computes
  `placeholders`, and raises `PromptCompileError` if neither a docstring
  nor a provable `PromptSource` return is available.

- **Render time** — the moment `.render(...)` or `.render_messages(...)`
  is called. This is when dependencies are resolved, the template is
  substituted, strict-mode checks fire, and the output is produced.

- **Configuration carrier** — a class whose only role is to hold
  configuration parameters and bind them to a behaviour surface
  exposed as instance methods. The `Promptstrings` class is a
  configuration carrier; it is not an "app object" — it does not own
  routing, lifespan, middleware, or an event loop.

- **Observer** — the runtime-checkable Protocol exported by the
  library that defines a sync sink for render-lifecycle events
  (`on_render_start`, `on_render_end`, `on_render_error`). External
  packages implement `Observer` to bridge promptstrings into OTel,
  structlog, eval frameworks, etc.

- **Adapter package** — a separate Python distribution that integrates
  `promptstrings` with a specific external library (Pydantic, Dishka,
  fast-depends, OTel, structlog, eval frameworks). Adapter packages
  are out-of-tree, depend on `promptstrings` plus the third-party
  library, and provide either helper functions (e.g., `from_dishka`,
  `from_fastdeps`) or `Observer` implementations.

- **Extras (`PromptContext.extras`)** — the documented namespace on
  `PromptContext` for framework-supplied handles (DI containers,
  request sessions, tracer references, eval-collector sinks). Not
  interpreted by the library; convention is leading-underscore keys
  for framework state.


- **Promptstring** — a callable produced by `@promptstring` or
  `@promptstring_generator`. Carries a template (from docstring or
  return value), a strictness mode, and a set of declared parameters.

- **Template** — the string with `{identifier}` placeholders. Source is
  either the function's docstring or a `PromptSource` returned at call
  time. Format specs and conversions are deliberately rejected at compile
  time.

- **Placeholder** — a `{identifier}` slot in a template. Must be a valid
  Python identifier; no format spec, no conversion. Resolved against the
  set of resolved parameters at render time.

- **Resolver** — a callable wrapped in `PromptDepends` or
  `AwaitPromptDepends`. Takes a `PromptContext` and returns the resolved
  parameter value. Sync resolvers run synchronously; async resolvers
  must be wrapped in `AwaitPromptDepends`.

- **PromptContext** — the per-render bag of values supplied by the
  caller. Resolvers read from it; parameter defaults fall back to it
  when no resolver is declared.

- **Strict mode** — when `strict=True` (default for `@promptstring`),
  every resolved parameter must appear in the rendered template, and
  every placeholder must be resolved. Catches the "silently dropped
  variable" class of prompt bugs.

- **Provenance** — `PromptSourceProvenance` metadata attached to a
  `PromptSource`. Carries `source_id`, `version`, `hash`,
  `provider_name`. Surfaces on every `PromptMessage` produced from that
  source so downstream consumers can trace which template version
  produced which message.

- **Render path** — the full async path from
  `<promptstring>.render(ctx)` through dependency resolution, source
  selection, template compilation, and final string emission. Two
  shapes: `render` (single string) and `render_messages` (list of
  `PromptMessage`).

## DX vocabulary

- **Guessability** — the property that an agent or human inventing a
  method or argument name by analogy lands on the actual API. High
  guessability reduces friction asymmetrically more for agents than for
  humans.

- **Legibility (of errors)** — the property that an error message
  contains enough structured context (offending symbol, resolved values,
  template line) for the reader to fix the cause without re-running.

- **Surface** — the public API: classes, functions, decorators, types,
  and exceptions exported from the package. "Tightening the surface"
  means removing or hiding things; "broadening the surface" means
  adding.

- **Strictness gradient** — the spectrum from "library tells you nothing
  is wrong" to "library refuses anything ambiguous." `promptstrings`
  sits intentionally toward the strict end; design docs should justify
  any move toward laxness.

- **Promise / non-promise** — a *promise* is a behavior the library
  guarantees across versions per SemVer; a *non-promise* is a behavior
  the library deliberately does not guarantee, even if the current
  implementation happens to exhibit it. The DX baseline lists both
  explicitly so users know what they may rely on.

- **Falsifiable rubric criterion** — a DX claim stated as a test the
  library either passes or fails. Vague claims like "errors are
  helpful" are not rubric criteria; "errors expose the offending
  placeholder via `exc.placeholder`" is.

- **Cancellation safety** — the property that a coroutine, when
  cancelled mid-flight (e.g. when `asyncio.gather` cancels siblings
  after one fails), releases its resources cleanly without leaking
  open connections, half-acquired locks, or partial writes. Required
  of any `AwaitPromptDepends` resolver.

## Process vocabulary

- **ADR** — Architecture Decision Record. A numbered, immutable record
  of a decision and its rationale. Lives in `decisions/`.

- **Proposal** — an in-flight recommendation, not yet decided. Lives in
  `proposals/`. Promoted to an ADR on acceptance.

- **Note** — exploratory thinking, scratch, research. Lives in `notes/`.
  Not load-bearing; can be deleted at any time.

- **Superseded** — an ADR whose decision has been replaced by a newer
  ADR. The old one is not deleted; its `Status` becomes `Superseded by
  NNNN` and the new one's `Supersedes` field points back. This
  preserves the audit trail of why minds changed.
