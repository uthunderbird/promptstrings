---
title: Cross-document consistency audit — baseline vs integrations
status: critique
created: 2026-04-26
---

# Cross-document consistency audit

**Targets:**
- `/Users/thunderbird/Projects/promptstrings/design/proposals/api-1.0-baseline.md`
- `/Users/thunderbird/Projects/promptstrings/design/proposals/api-1.0-integrations.md`

**Scope:** contradictions and overlaps *between* the two documents. Per-document
critique was performed in earlier rounds and is not repeated here.

**Method:** Swarm Red Team session 2026-04-26. Four critic experts (cross-reference
graph audit; formal layering; substitution and contract integrity; terminology
and duplicate detection) plus a mechanism-audit pass on the integrations doc's
"adds, does not retract" guarantee.

## Summary

The integrations doc's structural claim — *"This proposal adds, it does not
retract. Every promise in the existing baseline still stands."* — **holds at
the API contract level**, with one explicit contradiction (the
`promptstrings[pydantic]` illustrative example in baseline Promise 13).

The bigger problem is **definition locality**: several concepts are defined or
partially-defined in *both* documents, with no canonical owner declared. Readers
who encounter only one document get incomplete or stale information. A reader
of the live `glossary.md` plus *both* docs sees three definitions of
"configuration carrier," two mutability paragraphs about `PromptContext` (one
per field), and a "Glossary additions" section in integrations that lists
entries already present in the live glossary.

There are also two internal-to-integrations defects: a duplicate `##
Promotion to ADR` H2, and a stale "Glossary additions" section.

This audit produces a P0/P1/P2/P3 fix catalog and a per-concept canonicalization
table assigning each shared concept to a single owner document.

## Findings catalog

Result types: `verified issue` (V), `bounded concern` (B), `working criticism`
(W), `speculative concern` (S), `recommendation` (R).

### P0 — required for the "additive, non-retracting" claim to stand

| ID | Type | Description |
|----|------|-------------|
| **F-01** | V | **Baseline Promise 13 example contradicts integrations decision.** Baseline writes `promptstrings[pydantic]` as the canonical illustrative pip extras; integrations canonicalizes Pydantic support in a *separate* distribution `promptstrings-pydantic`. The two cannot both be the official pattern. |
| **F-02** | V | **Two `## Promotion to ADR` H2 sections in integrations.** Lines 673 (`— additions`) and 750 (plain). Markdown TOCs and link tools collide. They cover legitimately different content. |
| **F-03** | V | **Stale `## Glossary additions` section in integrations.** Lists Observer, Configuration carrier, Adapter package, Extras as if they were yet to be added to `design/glossary.md` — but the live glossary already contains all four. |
| **F-04** | V | **`PromptContext` definition split across docs without bidirectional pointer.** Baseline Promise 4 has the type, semantics, and mutability contract for `values`; integrations Promise I-3 has the type, semantics, and mutability contract for `extras`. Each doc shows the dataclass body, but neither tells the reader to consult the other for the rest. |
| **F-05** | V | **Integrations "Updated lifecycle integration map (delta from baseline)" looks like a 2-row replacement of baseline's 7-row table.** A reader of integrations alone could believe the lifecycle map is 2 rows. The text says "delta from baseline"; the structure says "this is the table." |

### P1 — strengthens robustness

| ID | Type | Description |
|----|------|-------------|
| **F-06** | B | **`logging` and `time` imports unaddressed in baseline Promise 5 ("Decoration is cheap").** Baseline says "no third-party imports at top level, no side effects on import." Integrations Promise I-2 introduces top-level `import logging` and uses `time.monotonic_ns()`. Both are stdlib, defensibly fine, but unaddressed in baseline. |
| **F-07** | B | **Two "Implementation delta index" tables, no cross-reference.** Baseline has a 5-row index for its deltas; integrations has a 3-row index for its own. An implementer must consult both. Recommend an explicit cross-reference in integrations. |
| **F-08** | B | **Count-based cross-references in integrations** ("R1–R10," "8-step sequence," "7-row table") will go stale if baseline is revised. Recommend content-based references. |
| **F-09** | R | **Asymmetric pointer.** Integrations links to baseline; baseline does not link to integrations. Reader landing on baseline first has no signal that an extension surface exists. |
| **F-10** | R | **Non-promise numbering collision.** Baseline non-promises 1–12, integrations non-promises 1–9. Future references like "non-promise 5" will be ambiguous. Recommend `N-1`–`N-9` for integrations. |

### P2 — consistency polish

| ID | Type | Description |
|----|------|-------------|
| **F-11** | W | **Module-level decorator type changes from function to bound method.** Integrations Promise I-1 redefines `promptstring = _default.promptstring`. This is observable via `inspect.ismethod()`. Baseline doesn't promise `type(promptstring) is FunctionType`, so this is not a contract break, but it should be acknowledged. |
| **F-12** | W | **Observer-event timing relative to strict-mode validation underspecified.** Integrations says `on_render_error` fires "before propagation"; baseline says strict-mode failures raise before any caller-side LLM call. The intended order (strict-fail → on_render_error → propagate) works but isn't explicit. |
| **F-13** | W | **"extras" used in two senses.** Baseline Promise 13 uses "extras" for pip extras (`promptstrings[pydantic]`); integrations uses "extras" for `PromptContext.extras`. Resolves automatically once F-01 removes the misleading example. |
| **F-14** | W | **"render time" vs "render path" vs "render call" used interchangeably across both docs and the glossary.** Pick one canonical term per concept. |

### P3 — defer-able

| ID | Type | Description |
|----|------|-------------|
| **F-15** | S | **Observer + concurrent gather context ownership.** When `on_render_start` is sync and `AwaitPromptDepends` resolvers run via `asyncio.gather`, which thread/context "owns" the observer call? Probably the caller of `render()`; not documented. Adapter authors will surface real cases first. |
| **F-16** | R | **Glossary should be canonical for shared terms.** "Configuration carrier," "Observer," "Adapter package," "Extras" are currently defined or re-explained in three places (glossary + integrations Promise + integrations decision rationale). Glossary should be the canonical definition; both proposal docs reference glossary terms inline. |

## Mechanism audit — "adds, does not retract"

Per `mechanism-audit.md`:

**1. What does the target explicitly promise?**
The integrations doc opens with: *"This proposal adds, it does not retract.
Every promise in the existing baseline still stands."*

**2. What does the mechanism actually guarantee?**
A row-by-row audit of each baseline promise against each integrations
modification:

| Baseline concept | Integrations action | Additive? |
|---|---|---|
| `Promptstring` Protocol | Not touched | ✓ |
| Two decorators (Promise 1) | Type changes from function to bound method | ✓ (baseline silent on type) |
| `PromptContext` (Promise 4) | New `extras` field added | ✓ |
| Error hierarchy (Promise 5) | Not touched | ✓ |
| Decoration cheapness (Promise 5/cheap) | Top-level `logging`, `time` imports | ✓ (stdlib) |
| Eager template parsing (Promise 7) | Not touched | ✓ |
| Concurrent async (Promise 9) | Observer events fire around resolution | ✓ |
| Re-entrancy (Promise 10) | Sync observer; not async-spawned | ✓ |
| Strict-mode raises before LLM (Promise 11) | `on_render_error` before propagation | ✓ assuming F-12 fix |
| Provenance flows (Promise 12) | Provenance flows to `RenderEndEvent` | ✓ |
| Pure stdlib (Promise 13) | Adds stdlib imports; **changes Pydantic distribution model** | ✓ for the imports; **✗ for the example** |

**3. Where does the stronger reading fail?**
At one place: baseline Promise 13's `promptstrings[pydantic]` example is now
misleading. The integrations doc canonicalizes Pydantic support outside the
`promptstrings` package entirely. The example is not a *promise* per se, but
it appears in a SemVer-contract document and will be quoted by readers as
the canonical extras pattern.

**4. Minimal fix set:** see P0–P1 catalog above. P0 items are required for the
"adds, does not retract" claim to stand without exception. P1 items strengthen
robustness; the claim survives without them but with friction.

## Canonicalization decisions

Every overlap is assigned a single canonical owner. The non-canonical document
either (a) holds a one-line pointer, (b) deletes the duplicate, or (c) keeps a
local statement explicitly marked as a restatement.

| Concept | Canonical doc | What the other doc does |
|---|---|---|
| `PromptContext` full shape (both fields + mutability) | **Baseline Promise 4** | Integrations Promise I-3 becomes a thin "this proposal adds the `extras` field; the canonical type lives in baseline Promise 4" pointer. |
| Pure-stdlib + Pydantic-out-of-core stance | **Baseline Promise 13** (strengthened) | Integrations Constraints + Non-promise 5 reduce to "see baseline Promise 13" pointers. The misleading example in baseline is removed. |
| Module-level decorator semantics | **Split, with bidirectional pointer.** Baseline Promise 1 owns the API surface; integrations Promise I-1 owns the configuration-carrier mechanism. | Baseline Promise 1 gains a one-line forward pointer to integrations I-1. |
| `Observer` Protocol, events, exception-swallow policy | **Integrations Promise I-2** | Baseline gains zero new text on observability. |
| Stdlib top-level import policy (`logging`, `time`) | **Baseline Promise 5 + Promise 13** (amended) | Integrations Promise I-2's "stdlib, allowed" parenthetical reduces to a pointer. |
| Lifecycle map | **Baseline** (the 7-row table) | Integrations replaces its "Updated lifecycle integration map" *table* with text deltas: "Resolution row gains: …" / "Render row gains: …". |
| DX rubric | **Split** (R1–R10 baseline; R11–R16 integrations) | No change; this is the cleanest layered relationship in the docs. |
| Implementation delta index | **Split** | Integrations adds an explicit cross-reference: "in addition to the baseline's delta index (5 rows), this proposal adds 3 more." |
| Decision rationale | **Split** (each doc owns its own decisions) | No change. |
| Out-of-scope of *this proposal* | **Split** (each doc owns its own) | No change. |
| Promotion to ADR | **Each doc owns its own.** Integrations' duplicate H2 must be resolved internally. | Rename one of the duplicate sections in integrations. |
| Glossary entries (Observer, Configuration carrier, Adapter package, Extras) | **`design/glossary.md`** is canonical | Integrations' "Glossary additions" section is deleted or reduced to "see `design/glossary.md`." Inline definitions in proposal-doc bodies become pointers where possible. |
| RFC 2119 normative-language declaration | **Each doc owns its own** | A SemVer doc cannot rely on conformance language declared in a sibling doc; both keep their declaration. |

## Ordered fix list

The repair pass should work through the catalog in this order. Each fix is a
distinct, identifiable edit; none collapse into a vague "cleanup."

### P0 (required)

1. **F-02:** rename one of the two `## Promotion to ADR` H2 sections in
   integrations. Suggested rename for line 673: `## Implementation deltas
   (additions to baseline plan)`. Keep line 750 as `## Promotion to ADR`.
2. **F-03:** delete the `## Glossary additions` section in integrations
   (lines 767–786). Replace with a single sentence in the History section
   or a pointer: "Glossary entries for these terms (Observer, configuration
   carrier, adapter package, extras) live in `design/glossary.md`."
3. **F-01:** remove or replace the `promptstrings[pydantic]` example in
   baseline Promise 13. Replace the parenthetical with a generic
   illustrative name (e.g. `promptstrings[example-extra]`) **and** add a
   sentence: "Vendor-specific integration adapters are *not* shipped as pip
   extras of this package; they live in separate distributions named
   `promptstrings-<vendor>`. See `api-1.0-integrations.md` for the
   integration model."
4. **F-04:** consolidate the canonical `PromptContext` definition in
   **baseline Promise 4**. Move the `extras` field declaration and its
   mutability paragraph into baseline Promise 4. Rewrite integrations
   Promise I-3 as: "This proposal added the `extras` field; the canonical
   type definition (including the mutability contract) now lives in
   baseline Promise 4." Keep the rationale, examples, and convention
   discussion in integrations Promise I-3.
5. **F-05:** rename integrations' "Updated lifecycle integration map (delta
   from baseline)" to "Lifecycle map row deltas." Replace the 2-row table
   with text deltas:
   - "Resolution row gains: when the render call begins, …"
   - "Render row gains: on successful completion, …"
   This eliminates the structural illusion of a partial-table replacement.

### P1 (recommended)

6. **F-06:** amend baseline Promise 5 ("Decoration is cheap") to add: "Top-level
   imports of stdlib modules (e.g. `logging`, `time`) are permitted; these do
   not count as 'side effects on import' even if the module performs lazy
   registry initialization."
7. **F-09:** add a one-line link in baseline (near top, after the Purpose
   section) pointing to `api-1.0-integrations.md`.
8. **F-10:** renumber integrations non-promises as `N-1` through `N-9` to
   disambiguate from baseline 1–12.
9. **F-08:** replace count-based cross-references in integrations with
   content-based ones: "extends the baseline rubric (currently R1–R10)" → "extends
   the baseline rubric"; "baseline's existing 8-step sequence" → "baseline's
   ordered implementation sequence"; "baseline's 7-row lifecycle table" → "baseline's
   lifecycle map."
10. **F-07:** add an explicit cross-reference in integrations' Implementation
    delta index: "In addition to the deltas listed in
    `api-1.0-baseline.md`'s delta index, this proposal adds the following."

### P2 (polish)

11. **F-11:** add a sentence to baseline Promise 1: "The exact callable type
    of these decorators is not part of the contract; users may rely on
    `@promptstring` and `promptstring(fn)` working, not on `type(promptstring)`."
12. **F-12:** tighten integrations Promise I-2 to make Observer-error timing
    explicit: "On any exception (compile, strict-mode, resolver), `on_render_error`
    fires after the exception is raised inside the render path and before it
    propagates to the caller. The render result is never returned to the
    caller after `on_render_error` fires."
13. **F-13:** sweep integrations doc for bare "extras" and ensure each occurrence
    is either backticked code (`extras`) or qualified ("pip extras," "framework
    handles in `extras`"). Auto-resolves once F-01 removes the misleading
    example.
14. **F-14:** sweep both docs and the glossary for "render time / path / call"
    consistency. Glossary canonical: *render time* = the moment, *render path*
    = the code flow, *render call* = a specific invocation.

### P3 (deferred)

15. **F-15:** document Observer + concurrent gather context ownership in a
    later design doc, after first adapter authors hit real cases.
16. **F-16:** sweep both proposal docs for inline definitions of glossary terms.
    Replace with glossary references where the inline definition adds nothing.

## What this audit explicitly did NOT find

- **No outright contract contradictions.** No integrations promise breaks any
  baseline promise. The baseline `promptstrings[pydantic]` example is the
  closest thing, and it is an example, not a promise.
- **No baseline retractions.** Every baseline promise still stands as written.
- **No silent narrowing.** No integrations text quietly tightens a baseline
  guarantee.
- **No cross-reference numerical errors.** Every numbered reference in
  integrations to baseline (R1–R10, 8-step sequence, 7-row table) is currently
  accurate; the concern is *future* drift, not present incorrectness.

## Provenance

This audit was produced via Swarm Red Team mode. The four critic experts
were Donald Knuth (cross-reference audit), Edsger Dijkstra (formal layering),
Barbara Liskov (substitution and contract integrity), and a copy editor
(terminology and duplicate detection). A mechanism-audit pass tested the
"adds, does not retract" structural guarantee. No expert-disagreement required
adjudication; the four lines of critique converged on the same defects from
different angles.

The findings are catalogued by result-type and priority. The canonicalization
table assigns every shared concept to a single owner document. The repair
pass should work the ordered fix list top-down.
