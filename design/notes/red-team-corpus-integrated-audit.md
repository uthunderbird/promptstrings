---
title: Cross-corpus audit — design/ as an integrated system
status: critique
created: 2026-04-26
---

# Cross-corpus integrated audit

**Target:** the entire `/Users/thunderbird/Projects/promptstrings/design/`
directory, audited as a system. Not a document-by-document re-critique
(those rounds happened); this audit asks whether the assembly itself
stands up.

**Three axes:**
- **Integration** — does VISION's apex framing actually flow into the
  proposals' contracts? Does the glossary anchor vocabulary used across
  the corpus? Are cross-doc pointers complete and bidirectional?
- **Non-contradiction** — does any claim in any document contradict any
  claim in any other?
- **Completeness** — are there things a reader would reasonably expect
  to find but doesn't?

**Method:** Swarm Red Team session 2026-04-26. Four critic experts
(cross-reference graph audit, formal hierarchy, contract integrity,
gap-and-emptiness detection) plus a mechanism-audit pass on the
directory README's own organizing claims. Filesystem-grounded; every
finding cites a specific file and (where applicable) a line.

## Summary

The corpus is **largely sound**. The cross-doc audit's earlier
canonicalization (proposals → glossary → VISION) held; no document
quietly modifies a claim made in another, and the layering hierarchy
declared in the directory README is honored by the actual content.

Three real defects remain:

- **F1** — broken markdown link from `integrations.md` to a
  non-existent `design/dx/integration-patterns.md`.
- **F8** — the repo-root `README.md` does not reference `design/` at
  all. The entire SSOT hierarchy is invisible from the repo entry
  point.
- **F3** — the glossary is partial in a way that's not honest: ten
  load-bearing terms used elsewhere in the corpus are absent, and the
  glossary itself declares no selection criterion.

Several smaller defects (F2, F4–F7, F9–F12) are convention
non-compliance, dead vocabulary, and discoverability polish. None
break integration; collectively they erode the corpus's claim to be a
finished SSOT.

## Findings catalog

Result types: `verified issue` (V), `working criticism` (W),
`speculative concern` (S), `recommendation` (R).

### P1 — required to honor the SSOT promise

| ID | Type | Description |
|----|------|-------------|
| **F1** | V | `design/proposals/api-1.0-integrations.md:474` links to `design/dx/integration-patterns.md` — file does not exist. The link lands on a 404. The integrations doc treats the target as the canonical home of per-vendor sketches. |
| **F8** | V | The repo-root `README.md` makes zero references to `design/`, `VISION.md`, `api-1.0-baseline.md`, or `api-1.0-integrations.md`. A first-time visitor or an LLM agent landing on the repo cannot find the design hierarchy without knowing it exists. The SSOT promise is undermined by invisibility. |

### P2 — required to keep the hierarchy honest

| ID | Type | Description |
|----|------|-------------|
| **F3** | V | The glossary is partial without declaring a selection criterion. Missing: 7 contract symbols (`PromptStrictnessError`, `PromptUnusedParameterError`, `PromptUnreferencedParameterError`, `PromptRenderError`, `RenderStartEvent`, `RenderEndEvent`, `RenderErrorEvent`) and 3 conceptual terms used as load-bearing referents in VISION (`DX rubric`, `above-the-fold`, `prompt-as-code`). A reader cannot tell whether absence means "trivial" or "intentional." |
| **F5** | V | `design/glossary.md` lacks frontmatter despite `design/README.md`'s explicit convention "every doc that isn't an ADR should carry a frontmatter block." The most-cited non-contract doc in the corpus transgresses the convention the directory declares. |
| **F7** | W | The baseline's `PromptContext.extras` impl-delta blockquote does not warn implementers that `extras` is already a local-variable name in `core.py:191/211/280` (unused-parameter strict-check loop). When the public field lands, the local will collide. Code-affecting fact, not a doc bug per se, but the docs should flag it for the implementer. |

### P3 — convention and consistency polish

| ID | Type | Description |
|----|------|-------------|
| **F2** | W | VISION's hierarchy diagram (lines 437–438) references `decisions/0001-…` / `decisions/0002-…` as if those ADRs exist. They don't. Ellipsis softens the claim, but a reader scanning the diagram believes ADRs exist. |
| **F4** | W | Five glossary terms (`Guessability`, `Legibility (of errors)`, `Strictness gradient`, `Falsifiable rubric criterion`, `Cancellation safety`) are unused in main docs (VISION, baseline, integrations). They were added during prior design discussions and never made it into the documents that supposedly need them. Either remove or use. |
| **F6** | W | Five subfolder READMEs (`dx/README.md`, `agent-dx/README.md`, `decisions/README.md`, `notes/README.md`, `proposals/README.md`) lack frontmatter, in violation of the directory README's own convention. The convention is effectively unenforced. |
| **F9** | W | `dx/README.md` and `agent-dx/README.md` end with honest "_No DX docs yet._" / "_No agent-DX docs yet._" but lack frontmatter (see F6). The empty-tier signaling is honest; the frontmatter compliance is not. |
| **F10** | W | `decisions/README.md` indexes "_No ADRs yet._" Combined with VISION's hierarchy diagram (F2) referencing 0001-… / 0002-…, a reader sees claims of ADRs that don't exist. Either VISION's diagram or the decisions README phrasing should be tightened. |
| **F11** | R | `design/notes/README.md` does not index the 7 red-team artifacts in the directory. A reader landing on `notes/` sees seven kebab-case files with no map. |
| **F12** | R | `design/README.md`'s "How to add a doc" section does not mention `VISION.md`. VISION is the apex of the hierarchy and the only doc whose addition rule is "don't add another; modify in place." Make explicit. |

## Mechanism audit — "coherent, complete design hierarchy"

Per `mechanism-audit.md`:

**1. What does the target explicitly promise?** The directory README
declares a layered hierarchy with VISION at the apex and defined roles
per subdirectory; a frontmatter convention on all non-ADR docs; "How
to add a doc" rules per layer; a glossary as canonical vocabulary.

**2. What does the mechanism actually guarantee?**

| Promise | Status |
|---|---|
| VISION exists at apex | ✓ |
| Proposals exist as in-flight RFCs | ✓ (2 docs) |
| ADRs exist in `decisions/` | ✗ (zero; both proposals are still `status: proposed`) |
| `dx/` holds DX deep-dives | ✗ (zero deep-dives; only stub README) |
| `agent-dx/` holds agent-DX deep-dives | ✗ (zero deep-dives; only stub README) |
| Glossary holds canonical shared vocabulary | ⚠ partial (F3) |
| Notes hold exploratory / artifact docs | ✓ |
| Frontmatter convention on all non-ADR docs | ✗ (glossary + 5 subfolder READMEs non-compliant) |
| Cross-references resolve | ⚠ one broken (F1) |
| Discoverable from repo root | ✗ (F8) |
| Layering integrity (no doc transgresses its declared role) | ✓ |
| Non-contradiction across docs | ✓ |

**3. Where does the stronger reading fail?**

- **Discoverability** (F8): the SSOT-ness of VISION depends on readers
  *finding* it. The repo-root README does not point to `design/`.
- **Resolvable cross-references** (F1): one published link 404s.
- **Glossary canonicalness** (F3): partial coverage without a
  declared selection rule undermines the glossary's job as the
  authoritative vocabulary anchor.
- **"Coherent, complete"** overstates: directories
  (`dx/`, `agent-dx/`, `decisions/`) promise content tiers that contain
  only stubs.

**4. Minimal fix set:** see P1 / P2 / P3 catalog above.

## What the audit explicitly did NOT find

- **No new cross-doc contradictions.** The earlier cross-doc audit's
  canonicalization fixes held. Every numbered Promise reference
  (Promise 1, 2, 5, 11, 12, 13, I-2) in VISION lands at the correct
  promise in the current baseline / integrations text.
- **No silent contract drift.** No document quietly modifies a claim
  made in another.
- **No layering transgression.** Each document respects its declared
  role: VISION is purpose, proposals are contracts, glossary is
  vocabulary, notes are critique artifacts.
- **No code-vs-doc contradictions.** The proposals' impl-delta
  blockquotes correctly identify what `core.py` lacks today and what
  it must contain by 1.0; the existing `placeholders` and `extras`
  occurrences in `core.py` are pre-existing internal names, not
  evidence of contract violation.

## Provenance

This audit was produced via Swarm Red Team mode on 2026-04-26. The
four critic experts were Donald Knuth (cross-reference graph audit),
Edsger Dijkstra (formal hierarchy), Barbara Liskov (cross-document
contract integrity), and a composite gap-detection role for
completeness and emptiness questions. The mechanism-audit pass tested
the directory README's "coherent, complete design hierarchy" claim.
No expert-disagreement required adjudication; the four lines of
critique converged on overlapping defects from different angles.

The findings are catalogued by result-type and priority. The repair
pass should work the ordered fix list top-down — F8 and F1 first
(discoverability and broken pointer), then F3, F5, F7 (canonicalness
and code-affecting facts), then F2/F4/F6/F9/F10 (convention
compliance), then F11/F12 (recommendations).
