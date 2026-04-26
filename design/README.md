# promptstrings — design docs

This directory holds living design documentation for `promptstrings`. It is
the canonical place for any document that influences how the library evolves,
how it should feel to use, or what was decided and why.

## Layout

| Path | Purpose | Lifetime |
|------|---------|----------|
| `VISION.md` | Single source of truth for the functional vision — problems the library solves and how its DX answers them. Updated in place; versioned via `vision_version` frontmatter. The apex of this hierarchy. | Living |
| `decisions/` | Accepted Architecture Decision Records (ADRs). Append-only history of what was decided and why. | Permanent |
| `proposals/` | RFCs in flight — drafts being debated, not yet accepted. When accepted, distilled into an ADR and the proposal is archived or deleted. | Transient |
| `dx/` | Developer Experience design docs targeting **human** users of the library. | Living |
| `agent-dx/` | Agent-DX design docs targeting **LLM agents** as users (introspection, error legibility, schema clarity). | Living |
| `notes/` | Exploratory thinking, scratch work, research dumps. Not yet shaped into a proposal. | Transient |
| `glossary.md` | Shared vocabulary used across the docs in this directory. | Living |

When introducing a term that appears repeatedly in design discussions,
add it to `glossary.md` so future readers and agents share precise
vocabulary.

## How to add a doc

- **Decision?** Copy `decisions/0000-template.md`, give it the next number, write it. ADRs are immutable once `Status: Accepted`; supersede with a newer ADR rather than editing.
- **Proposal?** Drop a kebab-case `.md` into `proposals/`. No number. When accepted, promote to an ADR.
- **DX or agent-DX deep dive?** Add a kebab-case `.md` to the appropriate folder and link it from that folder's `README.md`.
- **Just thinking out loud?** Use `notes/`. Move to `proposals/` when it firms up.

## Doc states

Every doc that isn't an ADR should carry a frontmatter block:

```yaml
---
title: <human-readable title>
status: draft | proposed | accepted | superseded | archived | living
created: YYYY-MM-DD
updated: YYYY-MM-DD
---
```

`status: living` is reserved for SSOT documents (currently `VISION.md`)
that are updated in place rather than superseded. Living docs may also
carry a numeric version field — `VISION.md` uses `vision_version: X.Y`
— bumped on substantive change and recorded in a *Revision history*
section at the bottom of the doc.

ADRs use the same field names but `status` is constrained to: `Proposed`,
`Accepted`, `Rejected`, `Superseded by NNNN`, `Deprecated`.
