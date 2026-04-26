---
title: Red Team — VISION Round 1 — Argumentative Integrity
target: design/VISION.md
focus: Argumentative integrity of the five-problem spine
round: 1 of 3
date: 2026-04-24
frame: inference-framed (no field data)
status: complete
---

# Red Team: VISION Round 1 — Argumentative Integrity

## Scope

This critique evaluates whether the five-problem narrative in
`design/VISION.md` holds under skeptical scrutiny by a staff engineer
not predisposed to adopt. The six failure categories examined:
(a) overclaims, (b) weak justification, (c) hidden assumptions,
(d) missing problems, (e) sales gaps, (f) demoted-item leakage.

The document is correctly labeled inference-framed. That framing is
acknowledged throughout this critique; findings flag where language
overreaches that frame and asserts pain as fact.

Companion documents read for grounding: `proposals/api-1.0-baseline.md`,
`proposals/api-1.0-integrations.md`, `src/promptstrings/core.py`.

---

## Critical Findings — Argumentative Spine Breaks Under Scrutiny

### C1. Problem 1 overclaims on f-string failure modes (verified issue)

The doc asserts that f-strings, `str.format()`, and generic template
engines "all fail open in the directions that matter" and lists three
bullets, including: "A typo in a placeholder name fails the same way as
a missing variable: nothing tells the developer the template no longer
references the parameter they just renamed."

This is false for f-strings. An f-string is evaluated against the
enclosing local scope at the expression site. A typo in an f-string
variable reference produces a `NameError` immediately at the call site —
it is neither silent nor delayed. The conflation of f-strings,
`str.format()`, and template engines into a single "fail open"
characterization is factually imprecise. A staff engineer who knows
Python will notice this immediately and begin discounting the rest of the
problem framing.

Additionally, the `str.format()` "missing variable produces a `KeyError`
at a surprising depth" is partially false: vanilla `str.format()` with a
missing named argument raises `KeyError` immediately at the format call
site. The surprising-depth failure applies specifically to
`str.format_map()` with a custom `__missing__`, not to `str.format()`
itself.

The real, correct argument for f-string pain is different and stronger:
f-strings entangle template logic with call-site scope. The template
cannot be stored, reused across call sites, versioned, introspected, or
tested in isolation. The prompt schema is invisible. The doc does not
make this argument.

**Impact:** The opening problem — meant to produce immediate recognition
from any developer — may instead produce skepticism from a precise
reader, undermining trust in the subsequent problems.

**Fix:** Tighten the failure-mode description to distinguish f-string,
`str.format()`, and template-engine failure modes accurately. Remove the
claim that f-string typos produce silent failures. Add the structural
argument: f-strings entangle template logic with call-site scope,
eliminating testability, reusability, and schema visibility.

---

### C2. Problem 4 frames against the wrong opponent (verified issue)

The doc argues that multi-message prompts "collapse into ad-hoc string
concatenation" and that "the structure must be parsed back." It frames
the status quo as developers joining strings with heredoc separators.

This characterization does not match the dominant current practice.
Teams using OpenAI, Anthropic, or Google Gemini SDKs build message lists
as `list[dict]` directly — `{"role": "system", "content": "..."}`. This
is the documented, idiomatic, correct pattern in all major SDK tutorials.
These teams are not string-joining; their message structure is already
typed. The "must be parsed back" claim does not apply to them.

For dict-building teams, the correct argument is: a `list[dict]` is
provider-coupled. OpenAI and Anthropic have different message schemas.
`@promptstring_generator` returning `list[PromptMessage]` is
provider-agnostic; SDK-specific adapter packages handle the mapping. A
team with provider-coupled message dicts cannot switch providers without
rewriting message construction. The VISION does not make this argument.

**Impact:** The problem 4 framing will fail to resonate with teams
already using SDK dicts — which is likely the majority of the target
audience. The strongest justification for the multi-message decorator is
absent.

**Fix:** Acknowledge that structured `list[dict]` is the current
idiomatic SDK pattern. Reframe the pain as provider coupling, not
structure collapse. The new argument: `list[PromptMessage]` is a
provider-agnostic type; the dict format is a provider contract. Teams
that want provider portability or that write adapters and tooling need
a stable intermediate representation.

---

### C3. Problem 2 presents plumbing as solution (verified issue)

The problem statement correctly identifies the provenance pain. The
library's answer — provenance as a first-class field on `PromptMessage`
propagated unchanged from user-supplied `PromptSource` — is described as
solving the traceability problem.

It does not. It creates the channel through which a solution can flow.
Teams without a pre-existing prompt versioning scheme (no git-SHA
attachment, no registry version, no content hash pipeline) will have
`source: None` on every `PromptMessage`. The plumbing is present; the
water is absent. The VISION does not acknowledge this gap.

Additionally, `PromptSourceProvenance` fields are all `str | None` with
no enforcement that they are populated. The guarantee "provenance flows
unchanged" is vacuously true when provenance is `None`. A team that
installs the library without adopting a versioning discipline gains
nothing from the provenance feature.

**Impact:** A staff engineer evaluating Problem 2 will ask: "what does my
team actually have to do to get this audit trail?" The VISION does not
answer. The answer — you must build or adopt a versioning scheme and wire
it to `PromptSource` — should be stated.

**Fix:** Acknowledge that the library provides the propagation
infrastructure, not the versioning discipline. State explicitly that the
feature becomes useful in combination with a versioning scheme (git SHA,
registry version, content hash). Frame this positively: the library is
compatible with whatever scheme the team already has, and imposes none of
its own.

---

## Lower-Priority Findings — Weak but Defensible

### L1. Problem 3's promised DX is not yet in `core.py` (bounded concern)

The VISION presents the structured exception hierarchy — named attributes,
`to_dict()`, leaf classes `PromptUnusedParameterError` and
`PromptUnreferencedParameterError` — as the library's answer to
agent-illegible errors.

Current `core.py` raises `PromptStrictnessError` directly on both error
paths, with no leaf classes, no named attributes, and no `to_dict()`.
These are documented as 1.0 blockers in the baseline (C2 delta,
DX rubric R1, R4, R6). The VISION's answer for Problem 3 describes
future behavior, not current behavior.

This is bounded rather than critical because the document is correctly
labeled inference-framed and describes design intent, not current state.
However, the VISION makes no indication that Problem 3's answer is
entirely prospective. A reader comparing the VISION to `core.py` will
find a material gap with no explanation.

**Fix:** Add a short note to Problem 3's answer (or to the doc's framing
section) indicating that the exception hierarchy described is the 1.0
design target, with the current state noted. Alternatively, rely on the
doc hierarchy pointing to the baseline, which documents deltas
explicitly. No change required if the team accepts this gap as covered
by the inference-frame disclaimer.

### L2. Problem 3 stability claim contradicts baseline's known limitation (bounded concern)

The VISION states: "The error hierarchy is rooted in `PromptRenderError`
and grows only by adding leaves; the structure is stable across versions."

The baseline (Promise 5, inheritance note) explicitly acknowledges that
`PromptCompileError` inheriting from `PromptRenderError` is "a known
ergonomic limitation" and that restructuring to a common base `PromptError`
(with `PromptRenderError` and `PromptCompileError` as siblings) is "a
candidate for 2.0." A 2.0 restructuring of the hierarchy contradicts the
VISION's stability claim unless qualified.

**Fix:** Qualify the stability claim: "stable within 1.x." The doc
already uses version framing elsewhere; apply it here.

### L3. Problem 5 does not argue for cross-codebase consistency (bounded concern)

The observability problem is framed as "invisible to OTel traces unless
the developer manually instruments every call site." The library's answer
is a single `Observer` Protocol.

For a single-team, single-app deployment, the Observer Protocol offers
no advantage over a thin wrapper function. The real value is when
multiple teams share a logging schema, when library/tool authors want to
emit prompt-layer events to user-controlled sinks, or when eval-framework
adapter authors need a stable surface across client codebases. None of
this is stated.

**Fix:** Add one sentence naming the cross-codebase consistency
motivation: that the Observer Protocol provides a stable surface for
adapter authors and tool builders, not just a per-app convenience.

### L4. Problem 1's answer is asymmetric: generators get weaker strictness (bounded concern)

The VISION presents "Render is strict by default. Missing placeholders
raise. Unused parameters raise" as the answer to Problem 1. This is true
for `@promptstring`. For `@promptstring_generator`, strict is opt-in
(`strict=False` default) and the check is a best-effort substring
heuristic with known false negatives (baseline Promise 11).

A developer who reads Problem 1's answer and reaches for
`@promptstring_generator` does not get the guarantees described. The
asymmetry is documented in the baseline but the VISION does not flag it.

**Fix:** Add a qualifier to Problem 1's answer noting that the structural
guarantee applies to `@promptstring`; `@promptstring_generator` has an
opt-in, best-effort variant with different properties.

---

## Demoted-Item Leakage (Recommendations)

### D1. "No vendor lock-in" acts as a problem statement inside Design Properties (working criticism)

The Design Properties section for "No vendor lock-in" states: "It is the
property that makes adoption safe: a team that cannot or will not adopt
Pydantic, OTel, a specific LLM SDK, or a cloud-vendor template registry
can still adopt `promptstrings`." The phrase "cannot or will not adopt"
frames vendor coupling as a pain the team is experiencing — a problem
statement. The section header is "Design Properties (not user pains)" but
this language does problem-statement work.

If vendor coupling is real pain (and it is, especially in regulated
industries), it should be in the problem list. If it belongs in Design
Properties, the language should describe the property without asserting
what bad code looks like.

**Fix:** Either promote a sixth problem — "vendor coupling forces
all-or-nothing adoption decisions" — or rewrite the Design Properties
description to describe the property (zero third-party runtime deps,
adapter-package model) without asserting team pain.

### D2. Static introspection pain is named implicitly in the Audiences section but not in the problems (working criticism)

The Audiences section describes: "an agent can ask `<ps>.placeholders`
to know what a prompt requires before rendering." The implicit pain —
that without introspection, agents must render to discover parameters,
or must parse templates themselves — is never stated as a problem. If
this capability solves a real pain (and for agent-driven tooling, it
does), the pain belongs in the problem list or in Problem 3's answer.

**Fix:** Add one sentence to Problem 3's answer naming the introspection
benefit explicitly: structured exceptions enable reactive self-correction;
introspectable placeholders enable proactive code generation without a
render round-trip.

### D3. `PromptDepends` design property section asserts user pain (working criticism)

The DI section states: "Without them, enforcing strictness (problem 1)
would force every caller into one-shot dict assembly." This presents a
negative about existing code ("one-shot dict assembly is clumsy") inside
a section explicitly designated for non-pain design properties. The
assertion acts as a problem statement.

**Fix:** Reframe the rationale as design necessity ("The DI primitive
exists to make strictness ergonomic at the definition site, not an
assembly burden at the call site") without asserting that one-shot dict
assembly is felt as pain by users.

---

## Missing Problems

### M1. Testability of prompt code is absent from the problem list (speculative concern)

Prompt code written with f-strings or inline dicts is difficult to
unit-test in isolation: the template is entangled with call-site scope
and the full parameter environment must be instantiated to exercise the
template. A `Promptstring` is a first-class, inspectable, independently
testable object. A test can render it with a mock `PromptContext` and
assert on the output without constructing the full call stack.

This is a real, recurring pain for teams trying to add test coverage to
prompt code. It is absent from the VISION.

**Recommendation:** Consider adding testability as a sixth problem, or
fold it into Problem 1's answer as a downstream benefit of strict
rendering: "Because the template is a named object with a declared
parameter schema, it can be tested in isolation with a mock context."

### M2. The prompt-as-code framing is absent (speculative concern)

The strongest meta-argument for `promptstrings` is that it treats prompts
as code: first-class objects with schemas, strict validation, structured
errors, and a defined lifecycle. The VISION argues each symptom
individually but never names the underlying pathology: prompt logic is
currently unstructured data embedded in code, with no schema, no
interface contract, and no testability surface.

**Recommendation:** Add one paragraph in the introduction naming
"prompt-as-code" as the organizing frame for the five problems. Each
problem is a symptom of treating prompts as unstructured strings rather
than typed, versioned, inspectable objects.

---

## Inference Overreach (Minor)

The doc's inference-frame disclaimer appears once, in the Purpose
section, and does not cascade to specific claims. The following
statements assert pain or trends as fact rather than design-team
inference:

1. "This pain is increasing fast." (Problem 3) — asserted as market
   observation; should be framed as expectation.
2. "A class of bugs that a 2024 developer would just fix manually is,
   in 2026, a bug that an agent should be able to fix in a single
   round-trip." — historical contrast presented as settled; is
   prediction.
3. "Mature systems solve it with explicit prompt registries; most code
   loses provenance the moment the message string is built." (Problem 2)
   — "most code" is an empirical claim beyond the stated inference frame.

**Fix:** Add hedging language at each site ("we expect," "in the design
team's observation," "as agent tooling matures") or move the disclaimer
closer to the problem section with an explicit reminder that all
problem-statement language is inference-framed.

---

## Compact Ledger

**Target document:** `design/VISION.md`

**Focus used:** Argumentative integrity of the five-problem spine

**Main findings:**

1. [CRITICAL] C1 — Problem 1 overclaims f-string failure modes; real f-string typos raise `NameError` immediately, not silently; the structural argument (template entangled with scope) is stronger and missing
2. [CRITICAL] C2 — Problem 4 frames against the wrong opponent; dict-building teams already have structure; the missing argument is provider coupling and portability
3. [CRITICAL] C3 — Problem 2 presents provenance plumbing as provenance solution; the library only propagates what the user supplies; teams without a versioning discipline gain nothing
4. [MODERATE] L1 — Problem 3's promised DX (named attributes, leaf exceptions, `to_dict()`) does not yet exist in `core.py`; presented as current state without qualification
5. [MODERATE] L2 — Problem 3 stability claim contradicts baseline's stated 2.0 restructuring candidate for `PromptCompileError`
6. [MODERATE] L3 — Problem 5 does not argue for its strongest justification: cross-codebase consistency for adapter authors and tool builders
7. [MODERATE] L4 — Problem 1's answer is asymmetric; `@promptstring_generator` has opt-in, best-effort strictness; VISION presents the strong guarantee without qualification
8. [LOWER] D1 — "No vendor lock-in" design property acts as a problem statement; either promote to a sixth problem or clean the language
9. [LOWER] D2 — Static introspection pain is implied in the Audiences section but never stated as a problem or problem-answer component
10. [LOWER] D3 — DI design property section asserts user pain ("one-shot dict assembly") in a section explicitly designated as non-pain
11. [LOWER] M1 — Testability of prompt code is absent; `@promptstring` enabling isolated unit tests is a genuine and common pain
12. [LOWER] M2 — "Prompt-as-code" as an organizing frame is absent; each problem is argued as a symptom without naming the shared pathology

**Ordered fix list (repair round priority):**

1. Rewrite Problem 1's failure-mode bullets to be precise per failure class (f-string vs. `str.format()` vs. template engine). Remove the claim that f-string typos are silent failures. Add the structural entanglement argument.
2. Rewrite Problem 4 to acknowledge dict-based message construction as idiomatic current practice. Add the provider-coupling and portability argument as the primary justification.
3. Add an explicit acknowledgment to Problem 2 that the library provides propagation infrastructure, not a versioning discipline; reframe as "compatible with any scheme, imposes none."
4. Qualify Problem 1's answer to flag the asymmetry: structural strictness for `@promptstring`, opt-in best-effort for `@promptstring_generator`.
5. Qualify Problem 3's stability claim to "stable within 1.x."
6. Add one sentence to Problem 5 naming cross-codebase consistency as the primary motivation for the Observer Protocol.
7. Add hedging language to the three specific inference-overreach sites in Problems 2 and 3.
8. Clean demoted-item leakage: rewrite "No vendor lock-in" property description to describe the constraint without asserting user pain; decide whether vendor coupling belongs in the problem list.
9. Add the testability benefit to Problem 1's answer (or as a sixth problem).
10. Consider adding a "prompt-as-code" organizing paragraph to the introduction.
