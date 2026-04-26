---
title: Per-vendor integration patterns
status: draft
created: 2026-04-26
updated: 2026-04-26
---

# Per-vendor integration patterns

This document is the canonical home for per-vendor integration patterns
that adapter authors and library users rely on when wiring
`promptstrings` into Pydantic, Dishka, fast-depends, OpenTelemetry,
structlog, eval frameworks, and prompt-management systems.

**Status:** draft. The integrations proposal
([`../proposals/api-1.0-integrations.md`](../proposals/api-1.0-integrations.md))
currently carries the canonical sketches inline under *Per-vendor
integration sketches*; this document will absorb those sketches as
they are validated against real adapter packages and lift them to
their canonical home.

Until that migration:
- the integrations proposal is authoritative for the integration
  patterns;
- this document holds links and any stable supplementary material
  that doesn't fit a SemVer-contract proposal (e.g., expanded
  end-to-end examples, lifecycle diagrams, troubleshooting notes for
  adapter authors).

## Vendors covered (planned)

The integrations proposal documents these vendors today; this file
will eventually own the canonical version of each:

- **Pydantic** — `promptstrings-pydantic` adapter package shape
  (gated `__get_pydantic_core_schema__` patching).
- **Dishka** — request-scoped DI container handle threaded via
  `PromptContext.extras["_dishka_container"]`; `from_dishka` helper.
- **fast-depends** — `from_fastdeps` helper wrapping
  `@inject`-decorated callables.
- **OpenTelemetry** — `OtelObserver` implementing the `Observer`
  Protocol; per-render correlation via `contextvars`.
- **structlog** — `StructlogObserver` mapping render events to
  structured log records.
- **Eval frameworks** (Inspect-AI, OpenAI Evals, deepeval, ragas) —
  Observer-based collection of provenance + timing per render.
- **Prompt-management systems** (LangSmith Hub, PromptLayer,
  Helicone, Pezzo, Agenta) — `PromptSource`-returning decorated
  functions; user-owned caching.

## Out of scope

- Library-side adapters for any vendor. Per baseline Promise 13 and
  integrations Non-promise N-5, vendor adapters live in separate
  `promptstrings-<vendor>` distributions and are never bundled into
  `promptstrings` core.
- Vendor SDK transport details (token authentication, retry policies,
  rate limits, etc.). The library does not ship LLM transports
  (baseline Non-promise 8).

## Adding a vendor

When a new adapter package matures and its canonical pattern stabilizes,
promote its sketch from `api-1.0-integrations.md` into a section here.
Each section should include:

- the adapter package's PyPI name and minimum version
- the seam used (`PromptDepends`/`AwaitPromptDepends` callable shape,
  `Observer` impl, `PromptContext.extras` key, or returned
  `PromptSource`)
- a minimal end-to-end example
- known constraints (cancellation safety, scope ownership, etc.)

## Cross-references

- [`../proposals/api-1.0-baseline.md`](../proposals/api-1.0-baseline.md)
  — the 1.0 contract (Promises 1–13, Non-promises 1–12).
- [`../proposals/api-1.0-integrations.md`](../proposals/api-1.0-integrations.md)
  — extension surface (Promises I-1/I-2/I-3) and the current canonical
  per-vendor sketches.
- [`../glossary.md`](../glossary.md) — vocabulary
  (`Observer`, `Adapter package`, `Extras (PromptContext.extras)`, etc.).
