---
title: Red-team critique — VISION Round 2 (internal consistency and cross-document coherence)
status: note
created: 2026-04-24
---

# Red-Team Critique: VISION Round 2 — Internal Consistency and Cross-Document Coherence

**Target:** `/Users/thunderbird/Projects/promptstrings/design/VISION.md` (vision_version 0.2)

**Companion documents consulted:**
- `proposals/api-1.0-baseline.md`
- `proposals/api-1.0-integrations.md`
- `glossary.md`

**Round context:** Round 1 repaired argumentative integrity (rewrote Problems 1 and 4; added scope boundary to Problem 2). This round assumes the five-problem spine is sound and stress-tests whether the document agrees with itself, with the two contracts, and uses vocabulary consistently.

---

## Critique process

### Iteration 1 — Cross-reference verification (stress-test a)

Each anchor pointer in VISION was read against the actual promise in the baseline or integrations proposal.

| VISION anchor | Claimed target | Verified? | Notes |
|---|---|---|---|
| P1 → baseline Promise 11 | Strict-mode failures raise before any LLM call | ✓ | Promise 11 content matches exactly |
| P1 → `PromptUnusedParameterError` / `PromptUnreferencedParameterError` under Promise 5 | Error hierarchy + leaf classes | ✓ | Promise 5 names both leaves |
| P2 → baseline Promise 12 | Provenance flows unchanged | ✓ | Exact match |
| P2 → integrations Promise I-2's `RenderEndEvent.provenance` | Field exists on event | ✓ | `RenderEndEvent.provenance: "PromptSourceProvenance | None"` confirmed |
| P3 → baseline Promise 5 | Error hierarchy + `to_dict()` | ✓ | Confirmed |
| P3 → DX rubric R1, R6 | Named attributes; `to_dict()` | ✓ | R1 commits `exc.unused_parameters` / `exc.resolved_keys`; R6 commits `to_dict()` |
| P4 → baseline Promise 1 | Two decorators | ✓ | Confirmed |
| P4 → `PromptMessage` minimum schema, Promise 2 | `role`, `content`, `source` | ✓ | Located in Promise 2's Promptstring Protocol section |
| P5 → integrations Promise I-2 | Observer + events | ✓ | Confirmed |
| Design Property → baseline Promise 13 | Pure stdlib core + adapter model | ✓ | Confirmed |

**Iteration 1 finding:** All anchor cross-references are accurate. No promise-number drift detected. Route closed.

---

### Iteration 2 — Behavior claims vs. contract (stress-test b)

**Claim A — P1: "missing placeholders raise, unused parameters raise"**

VISION P1 answer: "Strictness is structural and on by default: missing placeholders raise, unused parameters raise."

The contract (Promise 5, Promise 3, glossary "strict mode") distinguishes two error channels:

1. A *placeholder* in the template that cannot be resolved — fails via `PromptContext.require()` raising `PromptRenderError`. This is *not* a named strict-mode exception.
2. A *resolved parameter* that is not consumed by the template — raises `PromptUnusedParameterError` (the strict-mode named exception).

The glossary defines strict mode as: "every resolved parameter must appear in the rendered template, **and every placeholder must be resolved**." So both directions are in scope, but only the first (unused resolved parameter) has a named strict-mode exception class. VISION's phrasing "missing placeholders raise" treats an unfilled placeholder as a peer of the strict-mode unused-parameter error, which is accurate at the level of "it raises" but inaccurate at the level of "how." The two failure modes raise different exceptions through different paths.

**Claim B — P3: "named tuple fields"**

VISION P3: "In 1.0, `PromptUnusedParameterError` will expose `exc.unused_parameters` and `exc.resolved_keys` as **named tuple fields**, not buried in the message string."

Baseline Promise 5: "Public exception classes carry **named, picklable attributes** plus a `to_dict()` returning a JSON-safe payload."

Baseline R1: the attribute `exc.unused_parameters` holds a *tuple* value, but it is an instance attribute of the exception class, not a field of a `NamedTuple`. Calling these "named tuple fields" conflates the container type (exception class) with the value type (tuple). An implementer reading VISION might interpret "named tuple fields" as a `NamedTuple`-structured exception, which is not what the contract says. The contract says "named attributes" whose values happen to be tuples.

**Claim C — P4: provider adapter packages**

VISION P4 answer: "SDK-specific adapter packages map `list[PromptMessage]` to each provider's required dict schema. A team that swaps providers rewrites the adapter, not the prompt-construction code."

This is presented as part of the library's answer to P4 (provider coupling). However:
- No provider-specific dict-conversion adapter (for OpenAI, Anthropic, Gemini) is promised in baseline or integrations.
- Baseline Non-promise 8 explicitly says "No LLM transports."
- The integrations proposal covers OTel, DI, structlog, eval, and prompt-management adapters — not provider dict adapters.

The integrations doc's `per-vendor integration sketches` section covers Pydantic, Dishka, fast-depends, OTel, structlog, eval frameworks, and prompt registries — not OpenAI/Anthropic message-format converters.

VISION's answer implies these adapters will exist (or are part of what the library provides as a solution to P4), but there is no contract committing to them. This is a mild overclaim: the library's actual contracted answer to P4 is `list[PromptMessage]` as an agnostic intermediate type; whether provider dict converters get built is uncontracted.

**Claim D — P5: "The library auto-emits zero spans."**

Matched exactly by integrations Non-promise N-1. Valid. No issue.

**Iteration 2 findings:** Three behavior-claim issues (A: two-channel conflation; B: "named tuple fields" terminology; C: provider adapter overclaim). Route active.

---

### Iteration 3 — Demoted-item leakage (stress-test c)

Each of the three design properties was checked for problem-statement language, and each of the five problems was checked for duplication of design property language.

**Design properties read as properties?**
- "Prompt-time dependency injection": Contains explicit disclaimer "This is not a user pain." Reads as a property. Clean.
- "Static introspection of placeholders and parameters": "It is a free byproduct of the rendering discipline." Reads as a property. Clean.
- "No vendor lock-in": "This is a constraint, not a feature." Reads as a property. Clean.

**Problems duplicate property language?**
- P1 answer mentions testability and introspectability as benefits, but the framing is as a consequence of the structural fix, not as a standalone pain. The "Static introspection" property treats introspectability as a capability. Overlap is deliberate cross-referencing, not duplication.
- P3 and the "Static introspection" property have a bidirectional reference: P3 says "static introspection enables proactive generation"; the property says "it serves the same audiences problem 3 serves." This is coherent but slightly tangled — a reader may not know which section is the primary locus of the capability description.

**Iteration 3 finding:** No demoted-item leakage. One low-priority bidirectional-reference tangling noted.

---

### Iteration 4 — Terminology consistency (stress-test d)

**"definition time" vs. "decoration time"**

VISION P1 answer: "The template is separated from the call site at **definition time**, which makes it testable in isolation with a mock `PromptContext`..."

Glossary entry: "**Decoration time** — the moment a `@promptstring`-decorated function is processed at module import."

Baseline Promise 7: "Eager template parsing when docstring-sourced... the template is parsed at **decoration time**."
Baseline Promise 5: terminology clarification: "*decoration time = module import time, when the `@promptstring` decorator is applied.*"

"Definition time" is not defined in the glossary. In standard Python usage "definition time" typically refers to when the `def` statement executes, which for a module-level function is the same moment as import (and thus the same moment as decoration). However:
1. The glossary defines the canonical term as "decoration time."
2. "Definition time" is not in the glossary.
3. Using a non-canonical synonym for a canonically defined term undermines the shared vocabulary discipline the glossary is meant to enforce.
4. Subtle ambiguity: "definition time" could also mean "when the developer wrote the source," which is quite different.

This is a genuine terminology inconsistency against the canonical glossary.

**"strict mode" usage**

Glossary: "**Strict mode** — when `strict=True` (default for `@promptstring`)..."
VISION uses "strictness," "strict checking," and the `strict=True` parameter directly, but does not consistently use the canonical term "strict mode." This is a mild informality, not a conflicting definition.

**"render time," "render call," "PromptContext," "promptstring," "decorator"**

All checked. Usage in VISION is consistent with glossary definitions and with baseline/integrations usage. No conflicts found.

**Iteration 4 finding:** One critical terminology inconsistency ("definition time" vs. "decoration time"). One mild informality ("strict mode" vs. "strictness").

---

### Iteration 5 — Audience-framing consistency (stress-test e)

**P1 — primary audience (developer in pain):** Opens with concrete f-string/format bug scenario. Clear developer-in-pain framing. ✓

**P2 — primary audience:** Opens with "When an output goes wrong — a regression, a compliance flag, a surprising response..." Post-incident pain framing. ✓

**P3 — secondary audience drift:** Opens with: "LLM-agent code-generation tools — Cursor, Copilot, Claude Code, custom runtime agents — succeed or fail based on whether they can read errors and self-correct."

This is framed from the perspective of the agent as stakeholder, not from the developer's pain. The developer's pain is implicit (their agents can't fix bugs), but a developer who does not use agent tooling would not recognize their own pain in this opening. P3 is in the "above the fold" set (P1–P3 are what a 60-second reader sees). The primary audience (working developer, possibly without heavy agent tooling) hits P3 and finds the problem statement is about their agents, not about their own error-debugging experience.

The developer *does* have direct pain here: stringly-typed errors that require re-running with prints to diagnose. That pain is present in the body but not in the opening sentence.

**P4 — primary audience:** Opens with SDK `list[dict]` provider coupling. Developer-in-pain framing. ✓

**P5 — secondary audience:** Opens with observability tooling reference. Acknowledged as lowest-acuity and post-scroll in the doc itself. Acceptable.

**Iteration 5 finding:** P3's opening sentence serves the secondary audience (agent tooling) more than the primary audience (developer in pain). This is defensible given P3's acknowledged dual-audience purpose, but creates an inconsistency with how P1, P2, and P4 open.

---

### Iteration 6 — "Prompt-as-code" pathology mapping (stress-test f)

The organizing paragraph defines the single pathology as: prompts "have no schema, no interface contract, no testability surface, and no versioning discipline."

| Problem | Pathology limb | Explicit or inferential? |
|---|---|---|
| P1 (structural entanglement) | No schema, no interface contract, no testability surface | Explicit — directly mentioned in answer |
| P2 (provenance unrecoverable) | No versioning discipline | Explicit |
| P3 (errors illegible to agents) | No interface contract (errors have no structure) | Inferential — requires understanding that unstructured strings produce unstructured errors |
| P4 (provider coupling) | No schema, no interface contract | Explicit (provider-specific dict has no stable schema) |
| P5 (invisible to observability) | No testability surface (at runtime) | Inferential — "testability surface" must be extended to mean runtime observability |

**Iteration 6 finding:** The organizing frame claims all five problems are symptoms of the single pathology, but P3 and P5 require inferential steps. The connections exist but are not articulated. A reader who traces the pathology through the doc will find P3 and P5 feel like they have different etiologies (error ergonomics; observability infrastructure) from P1/P2/P4 (template structure and versioning). The "all five are symptoms of one pathology" claim is partly rhetorical.

---

### Iteration 7 — Revision history accuracy (stress-test g)

All stated Round 1 changes (C1, C2, C3, L1, L2, L3, D1, D2, D3, M1, M2) were verified against the current VISION text. Each change is present and correctly described.

**Date inversion finding:**

| Version | Date in history | Frontmatter |
|---|---|---|
| 0.1 | 2026-04-26 | `created: 2026-04-26` |
| 0.2 | 2026-04-24 | `updated: 2026-04-26` |

Version 0.2 (a revision of 0.1) is dated 2026-04-24 — two days *before* 0.1 (2026-04-26). A later version cannot predate an earlier one. The `updated` frontmatter field (2026-04-26) does not match the 0.2 revision date (2026-04-24) either.

Most probable cause: version 0.1 was drafted with a placeholder future date (2026-04-26); the Round 1 critique that produced 0.2 was conducted today (2026-04-24, the actual current date), and 0.2 was stamped with today's actual date. The dates need to be reconciled: either 0.1 should be backdated to 2026-04-24 or earlier (if it was genuinely written before today), or 0.2 should use a consistent date relative to 0.1.

**Iteration 7 finding:** Revision history date for 0.2 (2026-04-24) precedes revision history date for 0.1 (2026-04-26). The frontmatter `updated` field (2026-04-26) is inconsistent with the 0.2 revision date. This is internally incoherent.

---

## Findings

### Critical findings

**F1 — Revision history date inversion** [CRITICAL]

The 0.2 revision date (2026-04-24) precedes the 0.1 revision date (2026-04-26). The `updated` frontmatter field (2026-04-26) does not match the 0.2 date. A later revision cannot predate an earlier one; as written, the document's own history contradicts itself.

*Probable cause:* 0.1 was drafted with a placeholder future date; 0.2 was stamped with the actual current date. Fix: reconcile to a consistent chronology. The simplest repair is to use a single consistent date for all 0.x drafts (they were produced in the same design session), or update 0.1 to 2026-04-24 and both frontmatter fields to 2026-04-24.

**F2 — "definition time" vs. "decoration time" — non-canonical vocabulary** [CRITICAL]

VISION P1 answer uses "definition time" ("The template is separated from the call site at definition time") for a concept the glossary defines as "decoration time." "Definition time" is not a glossary term. The standard Python reading of "definition time" is ambiguous (could mean authoring time, not import time). The baseline uses "decoration time" consistently throughout.

*Fix:* Replace "definition time" with "decoration time" in P1 answer.

---

### Lower-priority findings (bounded concerns)

**F3 — "missing placeholders raise" conflates two error channels** [BOUNDED CONCERN]

P1 answer: "missing placeholders raise, unused parameters raise." The phrase "missing placeholders" (a placeholder in the template that has no resolved value) fails via `PromptContext.require()` raising `PromptRenderError`, not as a named strict-mode exception. "Unused parameters raise" is the strict-mode named path (`PromptUnusedParameterError`). Treating them as a symmetrical pair ("X raise, Y raise") implies they are governed by the same mechanism, which they are not.

The glossary's strict-mode definition does say "every placeholder must be resolved" — so the semantics is correct — but the error path differs. A reader who expects a named exception for an unresolved placeholder (by symmetry with `PromptUnusedParameterError`) will be surprised.

*Fix:* Rephrase to distinguish the two channels: e.g., "A template placeholder with no resolved value raises at render time; a resolved parameter unused by the template raises as `PromptUnusedParameterError`."

**F4 — "named tuple fields" is a precision error** [BOUNDED CONCERN]

P3 answer calls `exc.unused_parameters` and `exc.resolved_keys` "named tuple fields." The contract (Promise 5, R1) calls them "named, picklable attributes" whose *values* are tuples. "Named tuple fields" imports the concept of `NamedTuple`, which is not the contract shape. An implementer reading VISION might structure the exception as a `NamedTuple` subclass rather than a regular class with tuple-typed instance attributes.

*Fix:* Replace "named tuple fields" with "named attributes (each a tuple of strings)."

**F5 — Provider adapter packages are not contracted** [BOUNDED CONCERN]

P4 answer presents "SDK-specific adapter packages map `list[PromptMessage]` to each provider's required dict schema" as part of the library's answer to the provider-coupling problem. But no provider dict-conversion adapters (OpenAI, Anthropic, Gemini format) are promised in baseline or integrations. The integrations proposal explicitly lists which adapter packages are in scope; provider dict converters are not among them. Baseline Non-promise 8 rules out LLM transports.

VISION cannot promise adapters that the contract documents have not committed to. This is an overclaim at the vision level.

*Fix:* Qualify the provider-adapter claim. Either: (a) note that provider dict adapters are *out of scope for the 1.0 contract* and would need their own proposals, or (b) reframe the answer to focus on what *is* contracted: `list[PromptMessage]` as a stable, provider-agnostic intermediate type, which *enables* adapter packages to be written without touching prompt-construction code.

---

### Recommendations (strengthening alignment)

**R1 — P3 opening sentence: add developer-in-pain framing** [RECOMMENDATION]

P3 currently opens with agent-centric framing ("LLM-agent code-generation tools... succeed or fail based on whether they can read errors and self-correct"). P1, P2, and P4 open with the primary audience (developer in pain) before serving the secondary audience. P3 is in the above-the-fold set. A working developer who does not use agent tooling will not recognize their own pain in P3's opening sentence.

*Fix:* Open P3 with the developer-facing error pain ("A stringly-typed `RuntimeError` with no structured attributes requires a debugger round-trip to diagnose") then pivot to agent illegibility as the amplifying problem.

**R2 — Make the pathology-to-problem mapping explicit for P3 and P5** [RECOMMENDATION]

The organizing frame's four-limb pathology ("no schema, no interface contract, no testability surface, no versioning discipline") maps cleanly to P1, P2, and P4 but requires inference for P3 ("no interface contract → unstructured errors") and P5 ("no testability surface → no runtime observability"). A one-clause bridge in the P3 and P5 opening ("This is a consequence of the 'no interface contract' limb of the core pathology: when errors have no structure...") would make the organizing claim load-bearing rather than rhetorical.

**R3 — Clarify which section owns the static introspection capability description** [RECOMMENDATION]

P3's answer says "static introspection enables proactive generation" and the Design Properties section says the static introspection capability "serves the same audiences problem 3 serves." The bidirectional reference is coherent but leaves authoritativeness unclear. Consider adding a brief cross-reference pointer in one direction ("the capability is described in the Design Properties section" or "this capability's role in answering problem 3 is noted above").

---

## Ledger

**Target document:** `/Users/thunderbird/Projects/promptstrings/design/VISION.md`

**Focus:** Internal consistency and cross-document coherence — cross-references, behavior claims vs. contract, demoted-item leakage, terminology, audience framing, pathology mapping, revision history accuracy.

**Main findings:**

| # | Severity | Finding |
|---|---|---|
| F1 | CRITICAL | Revision history date inversion: 0.2 dated 2026-04-24 precedes 0.1 dated 2026-04-26; `updated` frontmatter also inconsistent |
| F2 | CRITICAL | P1 uses "definition time" — not a glossary term; canonical term is "decoration time" |
| F3 | BOUNDED CONCERN | P1 "missing placeholders raise, unused parameters raise" conflates two distinct error channels (PromptRenderError vs. PromptUnusedParameterError) |
| F4 | BOUNDED CONCERN | P3 calls exception attributes "named tuple fields"; contract says "named, picklable attributes" (whose values happen to be tuples) |
| F5 | BOUNDED CONCERN | P4 presents provider dict-conversion adapter packages as part of the library's answer; no such adapters are promised in baseline or integrations |
| R1 | RECOMMENDATION | P3 opening sentence frames agent pain, not developer pain; inconsistent with P1/P2/P4 opening posture in the above-the-fold set |
| R2 | RECOMMENDATION | P3 and P5 connections to the organizing pathology are inferential; explicit bridge clause would make the "five symptoms of one pathology" claim load-bearing |
| R3 | RECOMMENDATION | Static introspection capability described in both P3 answer and Design Properties section; authoritativeness is unclear |

**Exact ordered fix list for the repair round (priority order):**

1. **F1 — Fix revision history dates.** Reconcile 0.1 and 0.2 dates to a consistent chronology. Update `updated` frontmatter field to match whichever date is adopted for 0.2. Simplest: set 0.1 to `2026-04-24` and 0.2 to `2026-04-24` (same design session); or set both to today's actual date. Do not leave 0.2 predating 0.1.

2. **F2 — Replace "definition time" with "decoration time" in P1 answer.** Exact location: "The template is separated from the call site at definition time" → "The template is separated from the call site at decoration time."

3. **F3 — Disambiguate the two error channels in P1 answer.** Replace "missing placeholders raise, unused parameters raise" with language that distinguishes `PromptRenderError` (unresolved placeholder, via `PromptContext.require()`) from `PromptUnusedParameterError` (unused resolved parameter, via strict mode).

4. **F4 — Replace "named tuple fields" in P3 answer.** Replace with "named attributes (each a tuple of strings)" or equivalent phrasing that does not imply `NamedTuple` structure.

5. **F5 — Qualify the provider adapter claim in P4 answer.** Either scope it to the 1.0-contracted adapter packages (and note provider dict converters need their own proposals), or reframe to focus on the contracted intermediate type (`list[PromptMessage]`) as what enables those adapters — not promising the adapters themselves.

6. **R1 — Reframe P3 opening to lead with developer-facing pain.** Add a developer-in-pain sentence before the agent-centric sentence.

7. **R2 — Add explicit pathology bridge in P3 and P5 openers.** One clause each connecting the problem to its specific limb of the organizing pathology.

8. **R3 — Add a directional cross-reference in the static introspection property** pointing to P3 (or vice versa) to clarify that P3 is the problem context and the design property is the capability description.
