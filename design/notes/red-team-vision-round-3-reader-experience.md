# Red-Team Critique: VISION Round 3 — Reader Experience

**Target:** `design/VISION.md`
**Round:** 3 of 3 (final)
**Focus:** Reader experience — narrative flow, density, sentence clarity, heading hierarchy, terminology drift, formatting, above-the-fold estimate, cross-reference legibility, ending.
**Companion docs consulted:** `design/glossary.md`, `proposals/api-1.0-baseline.md`, `proposals/api-1.0-integrations.md`
**Date:** 2026-04-24

---

## Critique Iterations

### Iteration 1 — Narrative Flow and Emotional Arc (dimension a)

Reading P1 through P3 as the primary audience (developer-in-pain evaluating adoption):

**P1 arc:** Opens with an abstract structural argument before the reader feels the pain. The three-bullet failure-mode taxonomy (f-strings / `str.format()` / generic template engines) shifts the document into reference-comparison mode mid-narrative. This is useful content but it interrupts the pain arc. The transition back to narrative — "Because the template is entangled with the call site or left unenforced, the bug surfaces only when the LLM produces nonsense output" — is abrupt. A reader in f-string pain does not naturally follow the three-way comparison before hitting their recognition moment.

**P2 arc:** Strongest arc of the five. "invisible at design time and acute the first time something goes wrong in production" is the recognition moment the primary-audience framing promises. Pain → answer bridge is smooth. No arc problem.

**P3 arc:** Round-2 repair correctly placed developer-in-pain framing first. But the transition from the developer-debugger paragraph to the agent-tooling paragraph is a tonal break, not an escalation: "This pain intensifies as agent tooling becomes part of the debugging workflow" reads as a pivot to the secondary audience rather than a reason a developer-in-pain should care. The same developer is not obviously the one operating LLM agents as a debugging workflow.

**P4→P5 transition:** No explicit transition. P4 ends on a positive note (stable typed intermediate). P5 opens with a self-deprecating qualifier ("This is the lowest-acuity problem on the list"). The tonal descent is intentional (acuity ordering) but may read as the document losing confidence rather than preparing for a different register.

**Findings:**
- **A1 [bounded concern]:** P1 failure-mode taxonomy interrupts the pain arc and makes the transition back to narrative abrupt.
- **A2 [bounded concern]:** P3's agent-tooling paragraph reads as an audience pivot rather than an escalation of the developer-in-pain's own concern. Needs a stronger logical connector explaining why this same developer should care about agent tooling.
- **A3 [lower priority]:** P4→P5 tonal descension may create a minor confidence dip for the primary reader.

---

### Iteration 2 — Length and Signal Density (dimension b)

**Redundancy scan:**

- **"Library never authors provenance" appears twice within six sentences.** P2 answer: "The library never authors provenance — it does not synthesize hashes, does not assign versions." Then, immediately in the scope boundary paragraph: "The library imposes no scheme of its own." The core claim is repeated in different framings with no new information added.

- **P3 answer is four topics in one answer block:** (1) the 1.0 contract for exception hierarchy, (2) the current `core.py` state as 1.0 blocker, (3) the 1.x stability claim, (4) a 2.0 restructuring candidate sentence. The 2.0-candidate sentence ("A restructuring to a common base `PromptError`...is a candidate for 2.0") is implementation roadmap content. It belongs in baseline, not VISION.

- **P5 answer redundancy:** "The library auto-emits zero spans. The library never makes 'transport choices' for the user." Two sentences stating the same constraint in different words. One is sufficient.

- **Inference-framing hedge stacking:** The inference-framing paragraph (Purpose & audience) already front-loads the disclaimer for the entire document. "In the design team's experience" recurs explicitly in P2 and P3, and "in the design team's expectation" in P3. The first paragraph covers them all; the repeated hedges add reading friction.

**Findings:**
- **B1 [verified issue]:** "The library never authors provenance" + "The library imposes no scheme of its own" — same claim twice within six sentences in P2 answer. Cut the second instance or fold it into the first.
- **B2 [verified issue]:** P3 answer contains a 2.0 restructuring candidate sentence — vision-inappropriate implementation roadmap content. Remove or move to baseline.
- **B3 [bounded concern]:** P5 "auto-emits zero spans" and "never makes transport choices" say the same thing. Cut one.
- **B4 [lower priority]:** Second and third occurrences of "in the design team's experience/expectation" are partially covered by the inference-framing disclaimer. Consider removing inline hedges from P2 and P3 as redundant with the opening paragraph.

---

### Iteration 3 — Sentence-Level Clarity (dimension c)

**Long / over-nested sentences:**

- **Lines 106–110 (P1 answer):** "Strictness is structural and on by default: a template placeholder with no resolved value raises `PromptRenderError` at render time (via `PromptContext.require()`); a resolved parameter that the template does not consume raises `PromptUnusedParameterError` via the strict-mode check." — one sentence carrying: the default mode, channel 1 with a parenthetical aside, and channel 2. Should be split into at minimum two sentences.

- **Lines 403–406 (Audiences — convergence paragraph):** "The doc treats this convergence as load-bearing: any future design change that improves agent-DX at the cost of human-DX, or vice versa, should be flagged in this document as a tension before being made." — 43-word sentence. Split after "load-bearing."

- **P3 and P5 pathology-bridge openers** use identical 25-word structure ("This is the '…' limb of the organizing pathology…: a prompt string has no structured contract, so…"). The parallel is intentional but both sentences are long enough to create parsing friction as entry points to their sections.

**Findings:**
- **C1 [verified issue]:** Lines 106–110: one sentence carries three distinct ideas (strictness default + two error channels). Split into two sentences.
- **C2 [bounded concern]:** Lines 403–406: 43-word sentence in the convergence paragraph. Split at "load-bearing."
- **C3 [lower priority]:** P3 and P5 pathology-bridge openers are both long. The parallel structure is a strength; shortening them would improve entry speed.

---

### Iteration 4 — Heading Hierarchy and Visual Distinction (dimension d)

**`###` level collision:**

The "Design properties" section uses `###` for its three property headings — the same level as the five problem headings. The section introduction explicitly says Design Properties are "not user pains" and have a "different role." The visual hierarchy does not communicate this: a reader scanning headings sees five problem `###` headings and then three more `###` property headings at identical visual depth.

**Bold-label paragraphs:**

"**The library's answer.**", "**Asymmetry note.**", and "**Important scope boundary.**" are bold-labeled paragraphs with no heading-level markup. They look like ad-hoc subsections but are invisible to document-outline tools, screen readers, and agent parsers that consume heading structure.

**Findings:**
- **D1 [verified issue]:** Design properties `###` headings are visually indistinguishable from problem `###` headings, despite the text asserting a categorical role distinction. The Design Properties section should use either a visual separator or promote its properties to a clearly distinct visual treatment — or the section intro text should be restructured so the `##` heading itself signals the distinction.
- **D2 [bounded concern]:** Bold-label paragraphs function as subsections but have no heading markup. Using `####` consistently for "The library's answer," "Asymmetry note," and "Important scope boundary" would make the section structure navigable by heading-level tools.

---

### Iteration 5 — Terminology Drift (dimension e)

Checking every non-trivial term in VISION against the glossary:

- **"decoration time"** — glossary-canonical. ✓
- **"render time"** — glossary-canonical. ✓
- **"strict mode"** — glossary-canonical. ✓
- **"Observer"** — glossary-canonical. ✓
- **"adapter authors"** / "adapter packages" — consistent with glossary. ✓
- **"PromptSource"** — used in P2 answer ("A decorated function that returns a `PromptSource` with `provenance=PromptSourceProvenance(...)` causes that provenance to flow..."). `PromptSource` is not defined in the glossary. The glossary defines `Provenance` as `PromptSourceProvenance` metadata, but does not define `PromptSource` as a type. A reader landing on VISION first has no anchor for what `PromptSource` is.
- **"organizing pathology"** — used three times as if it is a defined concept, but it is not in the glossary. The organizing paragraph calls it "the underlying pathology in current prompt-handling code" — an ungoverned shorthand.
- **"best-effort heuristic"** — consistent between VISION and baseline. ✓
- **"first-class object"** — informal, not in glossary, used loosely in P1.
- **"provider-agnostic intermediate type"** — not a glossary term; consistent with usage elsewhere but ungoverned.

**Findings:**
- **E1 [bounded concern]:** `PromptSource` is used in P2 answer as a type name without definition in the glossary. Add a parenthetical definition on first use, or add `PromptSource` to the glossary.
- **E2 [lower priority]:** "The organizing pathology" functions as a glossary term but is not defined in the glossary. Consider adding a one-line entry or using "prompt-as-string pathology" throughout, since "prompt-as-code" is already named as the "organizing frame."

---

### Iteration 6 — Heading Punctuation and Formatting (dimension f)

**`##` headings:**
- `## Purpose & audience` — uses `&` (ampersand). No other `##` heading uses `&`.
- `## The problems we're solving` — uses contraction. No other `##` heading uses a contraction.
- `## Open questions deliberately not in this doc` — colloquial ("not in this doc"). Inconsistent with more formal headings like "Relationship to other docs."

**`###` problem headings:** Numbered, sentence case, no trailing punctuation. Consistent within the set. ✓

**`###` design property headings:** No number, sentence case, no trailing punctuation. Consistent within the set. ✓

**Findings:**
- **F1 [lower priority]:** `## Purpose & audience` — the `&` is inconsistent. Should be `## Purpose and audience`. Note also: the body discusses "audiences" (plural), so `## Purpose and audiences` would be more accurate.
- **F2 [lower priority]:** `## Open questions deliberately not in this doc` — colloquial phrasing inconsistent with other headings. Consider `## Open questions` or `## What this document does not answer`.

---

### Iteration 7 — Above-the-Fold Estimate (dimension g)

The document claims P1–P3 are "above-the-fold — what a 60-second-reader sees without scrolling."

**Line count from "## The problems we're solving" through end of P3:**
- Organizing paragraph: lines 52–66 (≈15 lines)
- P1 heading + body: lines 67–124 (≈58 lines)
- P2 heading + body: lines 126–165 (≈40 lines)
- P3 heading + body: lines 167–221 (≈55 lines)

**Total: ≈168 lines.**

At 250–350 words per minute reading pace (comfortable technical prose), P1 alone contains approximately 350 words — already beyond 60 seconds for most readers. P1's failure-mode taxonomy is particularly slow: it is a detailed comparison requiring active parsing.

The "60 seconds" claim is empirically false by a wide margin. The claim is made in the primary-audience framing and sets an expectation the document fails to meet.

**Finding:**
- **G1 [verified issue]:** The "60-second-reader sees without scrolling" claim is false. P1 alone exceeds 60 seconds for the typical technical reader. The claim should be removed or replaced with honest language ("the primary problems that justify adoption," "the first things to read"). Alternatively, the three above-the-fold problems must be substantially shortened to support the claim — but that would require removing content that rounds 1–2 added for argumentative correctness.

---

### Iteration 8 — Cross-Reference Legibility (dimension h)

**`→ Anchored by` lines in P1–P5:**

- **P1:** "baseline Promise 11 (strict-mode failures raise before any LLM call)" — parenthetical gloss is adequate for a VISION-first reader.
- **P2:** "integrations Promise I-2's `RenderEndEvent.provenance` field" — no gloss. A VISION-first reader knows `RenderEndEvent` is an event type (P5 introduces it) but may have reached P2 before P5. No self-explanatory context here.
- **P3:** "DX rubric R1, R6" — entirely opaque to a VISION-first reader. "DX rubric" is not defined in VISION or in the glossary; it is a baseline-internal concept. No parenthetical is provided.
- **P4:** "baseline Promise 1 (two decorators)" — adequate. "the `PromptMessage` minimum schema declared in Promise 2" — no gloss, but `PromptMessage` has been introduced in P4's body, so adequate in context.
- **P5:** "integrations Promise I-2 (Observer + events)" — parenthetical gloss is adequate.

**Findings:**
- **H1 [bounded concern]:** "DX rubric R1, R6" in P3's anchor line is opaque. Either remove the rubric references from VISION (they are baseline-internal) or add a parenthetical: "(the falsifiable DX rubric in the baseline)."
- **H2 [lower priority]:** P2's `RenderEndEvent.provenance` reference has no gloss. Add "(the render-completion event that carries provenance to observers)" or similar.

---

### Iteration 9 — Ending and Closure (dimension i)

The final content section is `## Open questions deliberately not in this doc`. Its last bullet:

> *Field-data evidence of user pain.* Not yet collected; this VISION is inference-framed. Bumping to `vision_version: 1.0` requires at least one external adopter's confirmed pain on at least the above-the-fold problems.

The section then ends. The next section is `## Revision history` (administrative).

The last thing the primary reader (developer-in-pain) reads before administrative history is an admission of unvalidated status: "not yet collected; inference-framed." This is accurate — and the inference-framing is correctly handled elsewhere in the document. But as a closing note for a vision document, it leaves the reader's final impression as "this is a promising design that isn't validated yet," rather than any sense of direction or resolve.

Vision documents need closure. The current section order produces the wrong ending: the document's most uncertainty-forward content lands last.

**Finding:**
- **I1 [verified issue]:** The document ends on an unvalidated caveat. This is an inappropriate ending for a vision document being read by someone evaluating adoption. Move "Open questions" earlier (before "Relationship to other docs") so the document closes on the "Audiences in detail" or "Relationship to other docs" section, both of which convey direction rather than uncertainty. Alternatively, add a brief closing paragraph after "Open questions" — two or three sentences that give the reader a sense of where this library is going and why that direction is right.

---

## Summary Ledger

**Target document:** `/Users/thunderbird/Projects/promptstrings/design/VISION.md`

**Focus used:** Reader experience — narrative flow (a), length/density (b), sentence clarity (c), heading hierarchy (d), terminology drift (e), heading formatting (f), above-the-fold estimate (g), cross-reference legibility (h), ending (i).

### Findings by severity

#### Verified issues (must fix before commit)

| # | Finding | Location | Description |
|---|---------|----------|-------------|
| G1 | Above-the-fold claim is false | Purpose & audience + problems intro | "60-second-reader sees without scrolling" is empirically wrong by a factor of 3–4×. |
| D1 | Design Properties `###` visually indistinguishable from problem `###` | Design properties section | Categorical role distinction stated in text is invisible in heading hierarchy. |
| C1 | Line 106–110: three ideas in one sentence | P1 answer | Strictness default + channel 1 + channel 2 in one compound sentence. Split. |
| I1 | Document ends on an unvalidated caveat | Open questions section | Last content before revision history is "not yet collected; inference-framed." |
| B1 | "Never authors provenance" stated twice | P2 answer | Same claim in two consecutive framings, no new information. |
| B2 | 2.0 restructuring candidate sentence in VISION | P3 answer | Implementation roadmap content, belongs in baseline not VISION. |

#### Bounded concerns (real issues, defensible not to fix)

| # | Finding | Location | Description |
|---|---------|----------|-------------|
| A1 | P1 failure-mode taxonomy interrupts pain arc | P1 | Three-bullet comparison shifts to reference mode mid-narrative; transition back is abrupt. |
| A2 | P3 agent-tooling pivot reads as audience switch | P3 | "intensifies as agent tooling" needs a stronger connector for the primary audience. |
| B3 | P5 "auto-emits zero spans" / "never makes transport choices" redundant | P5 answer | Same constraint stated twice. |
| C2 | 43-word sentence in convergence paragraph | Audiences in detail | Split at "load-bearing." |
| H1 | "DX rubric R1, R6" opaque to VISION-first reader | P3 anchor line | No gloss; rubric is baseline-internal. |
| E1 | `PromptSource` undefined in glossary | P2 answer | Used as a type name without definition. |

#### Lower priority (polish)

| # | Finding | Location | Description |
|---|---------|----------|-------------|
| D2 | Bold-label paragraphs lack heading markup | P1, P2 | "The library's answer," "Asymmetry note," "Important scope boundary" are invisible to outline tools. |
| A3 | P4→P5 tonal descension | P5 intro | "lowest-acuity problem" after P4's positive close. |
| B4 | Repeated inline inference hedges | P2, P3 | Covered by opening disclaimer; second and third occurrences add friction. |
| C3 | P3 and P5 pathology-bridge openers both long | P3, P5 openings | Parallel is intentional; both sentences are parsing obstacles. |
| E2 | "The organizing pathology" ungoverned | Throughout | Used as if a defined term; not in glossary. |
| F1 | `## Purpose & audience` uses `&` | Section heading | Inconsistent with all other `##` headings; body says "audiences" (plural). |
| F2 | `## Open questions deliberately not in this doc` colloquial | Section heading | Inconsistent register with other `##` headings. |
| H2 | P2 `RenderEndEvent.provenance` has no gloss | P2 anchor line | A VISION-first reader has no context for this field name. |

---

### Ordered fix list for the repair round (priority order)

1. **[G1] Remove or soften the "60-second" claim.** Replace "what a 60-second-reader sees without scrolling" with honest language such as "the primary problems — the ones that independently justify adoption." The claim sets an expectation the document cannot meet and damages credibility on first contact.

2. **[I1] Fix the ending.** Move `## Open questions deliberately not in this doc` earlier (before `## Relationship to other docs`), so the document closes on "Audiences in detail" or "Relationship to other docs" — both of which convey direction rather than uncertainty. Alternatively, add a two-sentence closing paragraph after "Open questions."

3. **[D1] Visually distinguish Design Properties from Problems.** The `##`-level heading "Design properties" already exists, but the `###` headings below it are visually identical to problem headings. Add a brief visual separator phrase or typographic marker to the `## Design properties` heading or its introduction that makes clear to a scanner that this section is declarative, not pain-asserting.

4. **[C1] Split lines 106–110 into two sentences.** The compound sentence with colon + two semicolon-clauses + two parenthetical asides carries three ideas. Suggested split: end the first sentence after "on by default," then open a new sentence for the two error channels.

5. **[B1] Remove the duplicate provenance-propagation claim in P2.** "The library never authors provenance — it does not synthesize hashes, does not assign versions" and "The library imposes no scheme of its own" say the same thing within six sentences. Keep whichever formulation fits the flow; cut the other.

6. **[B2] Remove the 2.0 restructuring candidate sentence from P3 answer.** "A restructuring to a common base `PromptError`...is a candidate for 2.0; see baseline Promise 5" is implementation roadmap content inappropriate in VISION. The baseline already carries it; remove from VISION.

7. **[A2] Strengthen the P3 agent-tooling bridge.** The sentence "This pain intensifies as agent tooling becomes part of the debugging workflow" needs a prior sentence explaining why the developer-in-pain (primary audience) already has agent tooling in their workflow — otherwise the paragraph reads as a pivot to the secondary audience. One sentence of context ("As developer toolchains increasingly include AI code-repair tools…") would bridge it.

8. **[H1] Gloss or remove "DX rubric R1, R6" in P3's anchor line.** Either add a parenthetical ("the falsifiable DX rubric in the baseline") or remove the rubric references from VISION entirely, since they are baseline-internal.

9. **[B3] Cut one of the two P5 redundant no-transport sentences.** "The library auto-emits zero spans" and "The library never makes 'transport choices' for the user" say the same thing. Keep the more precise one.

10. **[F1] Fix `## Purpose & audience` to `## Purpose and audience` (or `## Purpose and audiences`).** The body discusses "audiences" plural; the heading should match, and `&` should not appear in headings where no other heading uses it.

11. **[C2] Split the convergence paragraph's 43-word sentence.** Break at "load-bearing": end the sentence there, then start a new sentence for the governance instruction.

12. **[E1] Add `PromptSource` to the glossary or add a parenthetical definition on first use in P2.** A VISION-first reader has no anchor for what `PromptSource` is.

13. **[F2] Rename `## Open questions deliberately not in this doc`.** Consider `## Open questions` or `## What this document does not answer` to match the register of other headings.

14. **[H2] Add a gloss to the P2 `RenderEndEvent.provenance` anchor reference.** Add "(the render-completion event that carries provenance to attached observers)" so a VISION-first reader has context.

---

*Fix items 1–6 are required before commit. Items 7–14 are strongly recommended for the final polish pass.*
