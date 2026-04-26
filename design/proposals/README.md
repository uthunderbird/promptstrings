# Proposals (RFCs in flight)

Drafts being debated. Not yet decided.

A proposal is a document that:
- describes a concrete change or addition,
- has a recommendation (not just a survey of options),
- can plausibly become an ADR.

## Lifecycle

```
notes/  ─┐
         ├─▶  proposals/<title>.md  ─▶  decisions/NNNN-<title>.md
external ┘                              (proposal then archived/deleted)
```

When a proposal is accepted: distill its decision and rationale into an
ADR under `decisions/`, and either delete the proposal or move its
exploratory content to `notes/`. The proposal folder should not become a
graveyard of "decided but never archived" docs.

## Index

<!-- Keep this list small. If it grows past ~5, something is stalling. -->

- [API and DX baseline for 1.0](api-1.0-baseline.md) — promises,
  non-promises, lifecycle map, and DX rubric for the 1.0 contract.
  Proposed 2026-04-26.
- [External dev API and integration seams for 1.0](api-1.0-integrations.md)
  — `Promptstrings` configuration carrier, `Observer` Protocol with
  three event types, `PromptContext.extras` namespace; per-vendor
  integration sketches for Pydantic, Dishka, fast-depends, OTel,
  structlog, eval frameworks, and prompt-management systems. Layers
  on top of the baseline; nothing retracted. Proposed 2026-04-26.

## Frontmatter

```yaml
---
title: <human-readable title>
status: draft | proposed
created: YYYY-MM-DD
updated: YYYY-MM-DD
---
```
