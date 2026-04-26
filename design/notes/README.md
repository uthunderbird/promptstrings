# Notes

Exploratory thinking, scratch work, research dumps, half-formed ideas.

This folder is the escape valve. Without it, exploratory thoughts pollute
`proposals/` (which should hold *concrete recommendations*) and
`decisions/` (which should hold *accepted decisions*).

## Conventions

- Filename: `kebab-case-title.md`. No numbers.
- Frontmatter is optional but encouraged:
  ```yaml
  ---
  title: <…>
  status: draft
  created: YYYY-MM-DD
  ---
  ```
- Notes can be deleted at any time. They are not load-bearing.
- When a note firms up into a concrete recommendation, **promote it to
  `proposals/`** rather than letting it grow indefinitely here.

## Index

<!-- Optional. Don't feel obligated to keep this current. -->

### Red-team critique artifacts (2026-04-26)

These were produced during iterative critique cycles on the proposals
and on VISION. They are durable trace, not load-bearing for current
decisions; consult them only if you need to know *why* a finding was
fixed a particular way.

**On the proposals (3-round cycle on api-1.0-baseline.md and
api-1.0-integrations.md):**
- [`red-team-round-1-contract-completeness.md`](red-team-round-1-contract-completeness.md)
- [`red-team-round-2-execution-and-rollback.md`](red-team-round-2-execution-and-rollback.md)
- [`red-team-round-3-wording-and-legibility.md`](red-team-round-3-wording-and-legibility.md)

**Cross-document audit (between baseline and integrations):**
- [`red-team-cross-doc-consistency-audit.md`](red-team-cross-doc-consistency-audit.md)

**On VISION (3-round cycle on VISION.md):**
- [`red-team-vision-round-1-argumentative-integrity.md`](red-team-vision-round-1-argumentative-integrity.md)
- [`red-team-vision-round-2-consistency.md`](red-team-vision-round-2-consistency.md)
- [`red-team-vision-round-3-reader-experience.md`](red-team-vision-round-3-reader-experience.md)

**Corpus-level audit (the entire `design/` tree):**
- [`red-team-corpus-integrated-audit.md`](red-team-corpus-integrated-audit.md)
