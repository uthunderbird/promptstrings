---
title: Red-team round 3 — wording precision, internal consistency, and legibility
target: design/proposals/api-1.0-baseline.md
round: 3 of 3
focus: Wording precision, internal consistency, and legibility for both human and LLM-agent readers
date: 2026-04-24
---

# Red-team round 3 — wording precision, internal consistency, and legibility

## Scope

Rounds 1 and 2 addressed contract gaps and execution correctness. This round
assumes both are fixed and asks: can the document be understood, applied, and
referenced without producing further confusion? The grounding code at
`src/promptstrings/core.py` was used for verification of concrete claims.

---

## Critique iterations

### Iteration 1 — Internal consistency and cross-reference audit

#### R10 omitted from pass criteria (verified issue)

The rubric has ten tests: R1 through R10. The implementation ordering in the
Promotion to ADR section says:

> Step 7: R1–R9 test suite — run only after all above deltas are landed

Step 8 in the same sequence says:

> Tag 1.0 only after all R1–R9 tests pass and all deltas above are implemented.

R10 (`context=None` equivalence to empty `PromptContext()`) is omitted from
both gating statements. This is an internal inconsistency: R10 is a 1.0
blocker by the logic of the document (it tests a Promise 4 commitment), but
the step sequence does not require it to pass before tagging.

#### Duplicate "Scope of this guarantee" headers (verified issue)

Promise 11 contains two bold sub-headings both named `**Scope of this
guarantee**`. The first is tagged "(Fix C-4)" and covers the LLM-call scope
qualifier. The second (untagged) covers the structural-vs.-heuristic
distinction. A reader scanning headings encounters two identical heading labels
with different content. An LLM agent introspecting structure will find the
second and may discard the first as superseded. The "(Fix C-4)" tag makes the
first heading look like an editorial patch note rather than a normative
sub-section.

#### "Fix C-4" and "Fix C-5" labels embedded in headings (verified issue)

The heading `**Scope of this guarantee (Fix C-4):**` and the heading
`**Generator-body LLM calls are not covered by this guarantee (Fix C-5):**`
use editorial patch tags that have no cross-reference legend anywhere in the
document. The ADR section uses "C1 delta," "C2 delta," and "C4 delta" (no
hyphen) — which may or may not be the same as "Fix C-4" and "Fix C-5."
No mapping is provided. Any reader who was not present during the editing
session cannot interpret these tags. They appear to be version-control
commentary that was not cleaned up after round 2.

#### C1 delta described incompletely in Promise 9 blockquote (verified issue)

Promise 9's Implementation delta blockquote reads:

> The guard must be removed and replaced with `asyncio.gather` of all
> `AwaitPromptDepends` resolvers before the 1.0 tag. Until that change
> lands, this promise is a design target, not a live guarantee.

The ADR section's C1 delta bullet is materially more detailed, specifying: (a)
a two-pass loop, (b) the four specific call sites that must be updated
atomically (`_resolve_dependencies`, `_PromptString.render`,
`_PromptString.render_messages`, `_PromptStringGenerator.render_messages`),
and (c) the merge step. The atomicity constraint — "updating any subset leaves
the library in a broken intermediate state" — does not appear in the Promise 9
blockquote at all. A reader who reads the Promise blockquote and considers
themselves briefed will miss the atomicity requirement.

#### Step 7 / Step 8 cross-references are accurate for other rubric items

Checked: R4's dependency on C2 delta is stated in R4 ("R4 depends on the C2
delta being landed"). R8's dependency on Step 1 is stated in R8. These are
consistent and correct.

---

### Iteration 2 — Terminology consistency

#### "Decoration time" / "import time" / "module import" not formally equated

The three phrasings are used interchangeably throughout:
- "decoration-time (import-time) errors" — Promise 5
- "at decoration time" — Promise 7
- "at import time" — R8 test description
- "decoration time (module import)" — migration note 1

A first-time reader encounters "decoration time" in Promise 5 before any
formal equation. The parenthetical "(import-time)" in Promise 5 treats them as
obvious synonyms; the Lifecycle table treats "Decoration" as a phase name and
"Module import" as its When column value. No single sentence in the Promises
section formally states the equivalence. The migration note at the end of the
document is the clearest equating statement, but it appears 600+ lines in.
Bounded concern: experienced Python developers will infer the equivalence, but
a one-line definitional callout at the first use of "decoration time" would
close it.

#### RFC 2119 capitalization inconsistent

Non-promise 2 uses uppercase `MUST` and `MUST NOT` (RFC 2119 normative usage):

> Resolvers MUST be cancellation-safe and MUST NOT depend on side effects of
> other resolvers in the same render.

Promise 13 uses uppercase `MAY`. Promise 4's Mutability contract uses lowercase
`must not`. Promise 4's future-patch note uses lowercase `may`. No RFC 2119
conformance declaration appears anywhere in the document. A SemVer contract
document that mixes uppercase and lowercase normative terms without declaration
is either unintentionally inconsistent or inadvertently invoking RFC 2119
semantics in some places and not others. Either resolution is acceptable; the
current state is neither.

#### "Resolver" used for two distinct referents

"Resolver" is used to mean:
1. The `PromptDepends.resolver` callable attribute (the actual function).
2. The `PromptDepends` or `AwaitPromptDepends` parameter-default object.

Example from Promise 9: "Sync `PromptDepends` resolvers run sequentially" —
here "resolver" means the `PromptDepends` object, not the `.resolver`
callable. This is a bounded concern that experienced readers will parse
correctly, but it produces a mild impedance mismatch for agent readers that
index the word "resolver" against the code's `Resolver` type alias
(`Callable[[PromptContext], Any] | Callable[[PromptContext], Awaitable[Any]]`).

---

### Iteration 3 — Human legibility

#### Decision-maker path: contract and status are mixed

The Promises section is the contract. The Implementation delta blockquotes
scattered through it are status indicators ("this is not yet built"). A
decision-maker evaluating "is this 1.0 design acceptable" must mentally filter
out five "not yet implemented" blockquotes. This is a workable but imperfect
design for a document that is simultaneously a contract baseline and a project
status board. The blockquotes all end with "See the Promotion to ADR section
below" — the consistent referral creates a five-times read-the-ADR-section
pattern.

#### Exception catcher path: `PromptCompileError` guidance scattered

A user writing catch-blocks needs to know: catch `PromptCompileError` at
import time, not inside request handlers. This guidance appears in:
- Promise 5 (inheritance note)
- The ADR section (L1 delta bullet)
- Migration note 1

Three occurrences with different emphasis. None is prominently foregrounded
as a "key catch-block rule." A developer reading only the Non-promises section
or only the error hierarchy section will not encounter the most important
catch-block guidance before encountering a runtime problem.

---

### Iteration 4 — LLM agent legibility

#### `PromptUnreferencedParameterError` named attributes not specified (verified issue)

R1 commits specific attributes on `PromptUnusedParameterError`:
`exc.unused_parameters` (tuple) and `exc.resolved_keys` (tuple).

Nowhere in the document are the corresponding named attributes of
`PromptUnreferencedParameterError` specified. The "Out of scope" section
acknowledges this asymmetry: "Exact field set on each error class's
named-attributes API, **except** for the attributes explicitly committed in
the DX rubric (R1 commits...)." But R4 tests `PromptUnreferencedParameterError`
behaviorally (is it raised, is it not an instance of the other leaf) without
committing any attribute names. An agent generating a skeleton implementation
of `PromptUnreferencedParameterError` has no guidance on what named attributes
to add. The "Out of scope" note defers this to a follow-up ADR, but the
document then tags R4 as a 1.0-blocker test — a test that requires the class
to exist — without specifying its contract surface. This leaves a gap between
"the class must exist and be wired" (R4) and "the class's attributes are
TBD." Minimum needed: a parallel committed attribute set (even if just
`exc.unreferenced_parameters` and `exc.resolved_keys`).

#### Protocol member list not in a code block

Promise 2 presents the `Promptstring` Protocol members as prose bullets with
backtick-formatted names and type annotations. An agent generating the Protocol
class body must parse prose to extract:
- `placeholders: frozenset[str]`
- `declared_parameters: Mapping[str, inspect.Parameter]`
- `async render(context: PromptContext | None) -> str`
- `async render_messages(context: PromptContext | None) -> list[PromptMessage]`

These are exactly the lines needed to write the class. A code-fenced Protocol
skeleton (even with `...` bodies) would be directly extractable. The current
prose format is machine-parseable but requires inference for type annotation
syntax.

---

### Iteration 5 — Length, signal density, redundancy

#### Notes section is historical fluff

The Notes section (last section, two sentences) records the names of Swarm
session participants and the session date. It contains no contract content, no
implementation guidance, no test criteria, and no decision rationale. Its
presence does not serve any of the four identified reader goals. It is
appropriate context to carry into `design/notes/` as historical attribution
when the proposal is archived, but it adds noise at the end of a technical
contract document. A reader reaching the end of a 660-line document after
reading through the Migration notes would expect a summary or a "next actions"
statement — the Notes section delivers neither.

#### Signal density decline

The document grew from ~321 lines (round 0) to ~661 lines (round 2). The
growth is largely explained by: (a) five Implementation delta blockquotes with
substantial repetition of ADR-section content, (b) the "one-way door" argument
for the C1 delta appearing in both Promise 9 and the ADR bullet with nearly
identical text, (c) the "Scope of this guarantee" content under Promise 11
spanning three separate sub-headings that collectively address one topic. The
signal-to-noise ratio has not collapsed, but the scattered-blockquote pattern
is the primary driver of density loss.

---

## Summary of findings

### Critical findings (readability or correctness blockers)

**F1 [CRITICAL] — R10 missing from Step 7 and Step 8 pass criteria.**
Both gating statements say "R1–R9." R10 tests a Promise 4 commitment and is a
1.0 blocker by the document's own logic. An implementation team following the
step sequence would tag 1.0 with R10 untested.

**F2 [CRITICAL] — `PromptUnreferencedParameterError` named attributes not specified.**
R1 commits `exc.unused_parameters` and `exc.resolved_keys` on
`PromptUnusedParameterError`. No analogous attributes are committed for
`PromptUnreferencedParameterError`. R4 requires the class to exist and be
wired but does not commit its API surface. The "Out of scope" note defers the
field set, creating an asymmetric contract: one leaf exception has committed
attributes; the other does not.

**F3 [CRITICAL] — "Fix C-4" / "Fix C-5" editorial tags embedded in headings with no legend.**
These labels appear to be round-2 patch annotations that were not cleaned up.
They are opaque to any reader who was not in the editing session and create an
inconsistency with the "C1 delta," "C2 delta," "C4 delta" (no hyphen) labels
in the ADR section.

**F4 [CRITICAL] — Duplicate "Scope of this guarantee" heading in Promise 11.**
Two bold headings with identical text under Promise 11. An agent reader will
find two headings and cannot determine whether the second supersedes the first.
A human reader must read both to discover they cover different topics.

**F5 [CRITICAL] — C1 delta atomicity constraint missing from Promise 9 blockquote.**
The blockquote summarizes the C1 delta without the 4-site atomicity requirement
that is the central implementation risk. A developer briefed only by the
Promise 9 blockquote may implement the gather change at one site and ship a
broken intermediate state.

### Lower-priority findings

**F6 [MODERATE] — RFC 2119 capitalization inconsistent.**
`MUST`, `MUST NOT`, `MAY` appear uppercase in Non-promise 2 and Promise 13
but lowercase elsewhere. No conformance declaration. The document should either
declare RFC 2119 usage and capitalize consistently, or drop uppercase normative
terms entirely.

**F7 [MODERATE] — "Decoration time" / "import time" not formally equated at first use.**
The terms appear as obvious synonyms in context but are never formally equated
in the Promises section where they first appear. A one-line equivalence
statement in Promise 7 or a parenthetical on first use in Promise 5 would
close this.

**F8 [MODERATE] — Implementation delta blockquotes scattered through Promises section.**
Five blockquotes, each ending with "See the Promotion to ADR section below."
This pattern mixes contract content with project status and creates repetition.
Collapsing all five into a single "Implementation status" subsection before
the Promotion to ADR section (or removing the blockquotes and keeping only
the ADR section) would improve scannability for both audiences.

**F9 [MODERATE] — Notes section is historical fluff.**
Two sentences of session attribution at the end of a technical contract
document. No contract content. Should be removed from the proposal and carried
to archival notes when the proposal is promoted.

### Recommendations

**F10 [LOW] — Protocol member list should be a code block.**
A code-fenced skeleton of the `Promptstring` Protocol class body is directly
machine-extractable. The current prose bullets require inference. Cost to fix:
one code block.

**F11 [LOW] — "Resolver" used for two distinct referents.**
In context "sync `PromptDepends` resolvers" means the `PromptDepends` objects,
not the `.resolver` callables. Consider "sync `PromptDepends` parameters" or
"sync `PromptDepends` dependencies" for the outer objects to avoid the
collision with the `Resolver` type alias in the code.

**F12 [LOW] — R7 test condition edge case.**
`"\n" not in cls.__doc__.strip()` accepts a multi-line docstring that has no
embedded newlines but begins with whitespace followed by a newline when
unstripped. The intent is clear; the formulation may miss pathological cases.

---

## Compact ledger

**Target document:** `design/proposals/api-1.0-baseline.md`

**Focus used:** Round 3 — wording precision, internal consistency, and
legibility for human and LLM-agent readers.

**Main findings:**

| # | Severity | Finding |
|---|----------|---------|
| F1 | CRITICAL | R10 missing from Step 7 and Step 8 pass criteria ("R1–R9" should be "R1–R10") |
| F2 | CRITICAL | `PromptUnreferencedParameterError` named attributes not committed; asymmetric with R1's `PromptUnusedParameterError` contract |
| F3 | CRITICAL | "Fix C-4" / "Fix C-5" editorial tags in Promise 11 headings have no legend; inconsistent with "C1/C2/C4 delta" naming in ADR section |
| F4 | CRITICAL | Two identical "Scope of this guarantee" bold headings under Promise 11 |
| F5 | CRITICAL | Promise 9 blockquote omits 4-site atomicity constraint for C1 delta; partial duplication creates implementation risk |
| F6 | MODERATE | RFC 2119 capitalization inconsistent; no conformance declaration |
| F7 | MODERATE | "Decoration time" / "import time" not formally equated at first use |
| F8 | MODERATE | Five scattered implementation-delta blockquotes mix contract with status; each forward-references the ADR section |
| F9 | MODERATE | Notes section is historical fluff; does not serve any reader goal |
| F10 | LOW | Protocol member list in Promise 2 is prose; a code-fenced skeleton would be machine-extractable |
| F11 | LOW | "Resolver" used for both `PromptDepends` objects and `.resolver` callables |
| F12 | LOW | R7 test condition has an edge case with unstripped leading-newline docstrings |

**Ordered fix list (priority order for the repair round):**

1. **F1** — In Step 7 and Step 8, replace "R1–R9" with "R1–R10."
2. **F4** — Rename the first "Scope of this guarantee" sub-heading in Promise 11 to something distinctive, e.g., "Scope: caller's downstream LLM call only." Remove or resolve the "(Fix C-4)" tag.
3. **F3** — Remove all "Fix C-N" editorial tags from headings throughout. In the ADR section, standardize to "C1 delta," "C2 delta," "C4 delta" (no hyphen) and ensure every heading reference uses the same form.
4. **F5** — Add the atomicity constraint to the Promise 9 Implementation delta blockquote (or replace the blockquote body with a one-line summary and a clear pointer: "See C1 delta in Promotion to ADR for the atomicity requirement.").
5. **F2** — Either commit analogous named attributes for `PromptUnreferencedParameterError` (e.g., `exc.unreferenced_parameters` and `exc.resolved_keys`) in Promise 5 and test them in R4, or explicitly note in R4 that the attribute set for this leaf is deferred to the follow-up ADR and is not tested by R4.
6. **F6** — Add a one-line RFC 2119 conformance declaration below the Purpose section header, or convert all uppercase `MUST`/`MUST NOT`/`MAY` occurrences to lowercase equivalents for consistency.
7. **F9** — Remove the Notes section. Move its content to a `<!-- historical: ... -->` HTML comment or to a separate archival file.
8. **F8** — Evaluate consolidating the five scattered implementation-delta blockquotes. Minimum: ensure each blockquote body does not contradict the ADR section's description; consider whether each blockquote adds anything not in the ADR section or can be reduced to one sentence + pointer.
9. **F7** — Add a parenthetical at the first occurrence of "decoration time" in Promise 5: "(also called import time; these terms are used interchangeably throughout this document)."
10. **F10** — Add a code-fenced `Promptstring` Protocol skeleton to Promise 2, after the prose bullet list.
11. **F11** — In Promise 9 and Non-promise 2, use "sync `PromptDepends` dependencies" (not "resolvers") for the parameter-default objects to distinguish them from the `.resolver` callable.
12. **F12** — Tighten the R7 test condition to `cls.__doc__ is not None and len(cls.__doc__.strip().splitlines()) == 1` to express "exactly one non-empty line" without the edge case.
