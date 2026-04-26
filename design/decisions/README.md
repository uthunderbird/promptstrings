# Architecture Decision Records (ADRs)

Numbered, append-only records of accepted decisions. Once an ADR is
`Accepted`, it is immutable — to change a decision, write a new ADR that
supersedes the old one and update the old one's `Superseded by` field.

## Index

<!-- Add entries as ADRs are accepted. Keep newest at the top. -->

- [0002 — Integration seams for 1.0](0002-integration-seams-for-1.0.md)
  — `Promptstrings` configuration carrier, `Observer` Protocol with
  three event dataclasses, `PromptContext.extras` namespace; per-vendor
  adapter integration model. Layers on top of 0001 without retracting.
  Accepted 2026-04-26.
- [0001 — API and DX baseline for 1.0](0001-api-and-dx-baseline-for-1.0.md)
  — 13 promises, 12 non-promises, lifecycle integration map, DX rubric
  R1–R10. The locked SemVer contract for the core library.
  Accepted 2026-04-26.

## Adding an ADR

1. Copy `0000-template.md` to `NNNN-kebab-case-title.md` using the next
   monotonic number.
2. Fill in Context, Decision, Alternatives, Consequences. Alternatives are
   mandatory.
3. Open as `Status: Proposed`. Flip to `Accepted` when the call is made.
4. Add an entry to the Index above.

## Why ADRs

Decisions decay without context. Six months from now, "why did we choose
the decorator API over a class API?" should have a one-link answer, not a
git-archaeology session.
