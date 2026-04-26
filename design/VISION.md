---
title: promptstrings — VISION
status: living
vision_version: 0.4
created: 2026-04-26
updated: 2026-04-26
---

# promptstrings — VISION

## Purpose and audiences

This is the **single source of truth for the functional vision** of
`promptstrings`. It describes what problems the library exists to solve
and how its developer experience answers them. It is a living document:
it is updated in place as the vision evolves, not superseded.

What this doc is:
- a problem-statement and DX-answer pairing,
- the *why* that motivates every promise in
  [`api-1.0-baseline.md`](proposals/api-1.0-baseline.md) and
  [`api-1.0-integrations.md`](proposals/api-1.0-integrations.md),
- versioned via `vision_version` in the frontmatter; substantive changes
  bump it and append to the *Revision history* at the bottom.

What this doc is not:
- not a contract — the SemVer contract is in the baseline and
  integrations proposals;
- not a roadmap;
- not an enumeration of API promises.

**Primary audience.** The working developer currently in pain with
prompt-handling code in production: someone who has shipped two or
three LLM features, has had at least one prod incident traceable to a
prompt bug, and is now evaluating whether to keep building prompts
inline or adopt something. Reading the first three problems should
produce recognition: *"this is the bug I shipped last month."*

**Secondary audience.** The staff engineer or architect making an
adoption decision; the LLM-agent code-generator that will read and
write code that uses this library; the contributor or adapter author
needing to ground deeper design work.

The problem framing in this document is **inferred from design
intent**, not derived from external user telemetry. Where the doc says
"typical prompt code does X," it means *typical in the design team's
experience and in the patterns visible in widely-shared LLM-app code*,
not "X% of surveyed users." When real-world adoption produces field
data, this document gets a version bump and the language tightens.

## The problems we're solving

The organizing frame for all five problems is **prompt-as-code**. The
underlying pathology — the **prompt-as-string pathology** — is that
prompts are treated as unstructured strings embedded in logic: they
have no schema, no interface contract, no testability surface, and no
versioning discipline. Each of the five problems below is a symptom of
that treatment. The library's answer in each case is to make the prompt
a typed, versioned, inspectable, testable object.

Five problems, ordered by acuity. The first three form the
above-the-fold set — readers who scan only the first three
justifications get an independent reason to adopt for each.
Each one independently justifies the library; together they form a
narrative from *today's pain* through *operational maturity* to
*tomorrow's bet*.

### 1. Prompt construction entangled with call-site scope

The root problem with ad-hoc prompt code is structural: when a prompt
is written as an f-string, the template lives at the call site and
cannot be stored, reused across call sites, versioned, introspected, or
tested in isolation. The prompt schema — what parameters the template
requires — is invisible until you run the code.

The failure modes follow from this structural entanglement. They differ
by approach — each with a distinct way of letting a bug hide:

- **f-strings**: a typo in a variable reference raises `NameError`
  immediately at the call site — the failure is not silent. But the
  template is inseparable from the scope that encloses it, so it cannot
  be tested in isolation, reused in a different context, or introspected
  without running the code. An unused variable disappears with no
  warning: the caller resolved and fetched it, and the template ignored
  it.
- **`str.format()` and `str.format_map()`**: a missing named argument
  raises `KeyError` at the format call site. An unused argument
  disappears silently. A typo in a placeholder (`{naem}` vs `{name}`)
  fails the same way as a missing key. The template is at least
  separable from its call site, but strictness is the caller's
  responsibility — the standard library enforces nothing.
- **Generic template engines**: failure behavior varies; unused
  variables typically vanish silently and missing variables may produce
  empty interpolations or literal `{name}` strings that the LLM
  incorporates verbatim.

Because the template is entangled with the call site or left
unenforced, the bug surfaces only when the LLM produces nonsense
output. The cause is far from the symptom; the fix is in code reviewed
weeks ago.

#### The library's answer

A `@promptstring`-decorated function is a
first-class object with a declared parameter schema. The template is
separated from the call site at decoration time, which makes it
testable in isolation with a mock `PromptContext`, reusable across call
sites, and introspectable without rendering. Strictness is structural and on by default. A template placeholder
with no resolved value raises `PromptRenderError` at render time via
`PromptContext.require()` — this is the missing-value channel. A
resolved parameter that the template does not consume raises
`PromptUnusedParameterError` via the strict-mode check — this is the
unused-parameter channel. The two channels are distinct: each names a
different class of mistake. Errors in both channels fire
at render time, before any caller-side LLM call. The class
of "silently dropped variable" bugs ceases to exist as a runtime
failure mode; it becomes an immediate, named exception.

#### Asymmetry note

The structural guarantee — every resolved parameter
name is tested against the template's placeholder set — applies to
`@promptstring`. For `@promptstring_generator`, strict checking is
opt-in (`strict=True`) and uses a best-effort heuristic with known
limitations; see baseline Promise 11.

→ Anchored by baseline Promise 11 (strict-mode failures raise before
any LLM call) and the `PromptUnusedParameterError` /
`PromptUnreferencedParameterError` leaves under Promise 5.

### 2. Provenance is unrecoverable after rendering

Once a prompt has been rendered into a string and shipped to the LLM,
typical code retains no audit trail of *which template version
produced this output*. When an output goes wrong — a regression, a
compliance flag, a surprising response — answering "what did we
actually send, and what version of the prompt was active at that
moment?" requires `git blame` archaeology and clock arithmetic against
deploy timestamps.

This is the kind of pain that is invisible at design time and acute
the first time something goes wrong in production. Mature systems
solve it with explicit prompt registries; much prompt code loses
provenance the moment the message string is built.

#### The library's answer

Provenance is a first-class field on every
`PromptMessage`. A decorated function that returns a `PromptSource`
(the typed wrapper carrying the rendered template and its provenance
metadata) with `provenance=PromptSourceProvenance(source_id, version,
hash, provider_name)` causes that provenance to flow, unchanged, to
every message produced from that render. Downstream observers, logs, eval
collectors, and audit systems can trace any rendered output back to
the exact template that produced it. The library never authors
provenance — it does not synthesize hashes, does not assign versions
— so the user's existing versioning scheme (git SHA, content hash,
registry version, anything) is respected.

#### Important scope boundary

The library provides the propagation
infrastructure, not the versioning discipline. A team without a
pre-existing versioning scheme — no git-SHA attachment, no registry
version, no content-hash pipeline — will have `source: None` on
every `PromptMessage`. The provenance feature becomes useful only in
combination with a scheme that populates `PromptSourceProvenance`.
It is compatible with whatever versioning scheme the team already
uses. Users who have or will adopt a versioning discipline get a
first-class audit channel; users who have not yet adopted one gain
nothing from this feature until they do.

→ Anchored by baseline Promise 12 (provenance flows unchanged) and
integrations Promise I-2's `RenderEndEvent.provenance` field (the
render-completion event that carries provenance to attached observers).

### 3. Errors are illegible to agents

This is the "no interface contract" limb of the organizing pathology: without a structured contract, failures have no structure either.

When a prompt-related error fires in production, a developer debugging
it faces a stringly-typed `RuntimeError("something went wrong with
placeholders")` that names no specific symbol and requires a
debugger round-trip — or re-running with print statements — to learn
which placeholder was at fault. The error is a dead end: it does not
name the offending key, cannot be compared against the function's
parameter list, and cannot be acted on without running the code again.

This pain intensifies as agent tooling becomes part of the debugging
workflow. A developer using Cursor, Copilot, Claude Code, or a custom
runtime agent to repair a prompt bug is already in an agentic loop —
the same developer, with an AI co-pilot, hit by the same stringly-typed
dead end. LLM-agent code-generation tools succeed or fail based on
whether they can read errors and self-correct. A stringly-typed error defeats this: the
agent cannot extract which placeholder was wrong, cannot compare it
against the function's parameter list, and cannot generate a fix without
another run.

As agent tooling matures, a class of bugs that a developer would have
fixed manually is increasingly a bug that an agent should be able to
fix in a single round-trip — but only if the error structure supports
it.

#### The library's answer

The 1.0 contract commits to every public
exception class carrying named, picklable attributes plus a `to_dict()`
method returning a JSON-safe payload. In 1.0, `PromptUnusedParameterError`
will expose `exc.unused_parameters` and `exc.resolved_keys` as named
attributes (each a tuple of strings), not buried in the message string.
`PromptUnreferencedParameterError` will expose the parallel
`exc.unreferenced_parameters` and `exc.resolved_keys`. An agent
catching one of these exceptions can read the offending symbol
mechanically, write a fix, and ship it without a debugger.

The current implementation (`core.py`) raises `PromptStrictnessError`
directly on both error paths, with no leaf classes, no named
attributes, and no `to_dict()`. These are 1.0 blockers tracked in the
baseline (C2 delta, DX rubric R1, R4, R6); the hierarchy above
describes the 1.0 design target.

In 1.0, the error hierarchy will be rooted in `PromptRenderError` and
grow only by adding leaves; the structure is stable within the 1.x
line.

Structured exceptions enable reactive self-correction. For the
complementary capability — proactive code generation without a render
round-trip, enabled by the `placeholders` and `declared_parameters`
attributes — see *Static introspection of placeholders and parameters*
in the Design Properties section below.

→ Anchored by baseline Promise 5 (error hierarchy + `to_dict()`) and
DX rubric R1, R6 (the falsifiable DX rubric in the baseline).

### 4. Multi-message prompt construction is provider-coupled

Teams using OpenAI, Anthropic, or Google Gemini SDKs typically build
multi-message prompts as `list[dict]` — `{"role": "system", "content":
"..."}`. This is the documented, idiomatic pattern in all major SDK
tutorials. The structure is explicit and typed at the dict level.

The problem is provider coupling: a `list[dict]` is a provider
contract, not a stable intermediate representation. OpenAI and
Anthropic have different message schemas. Moving from one provider to
another requires rewriting every message-construction site. Teams that
share prompt-construction code across providers, write adapters, or
build tooling on top of message structure need a type that sits above
any one SDK's dict schema. Similarly, a role marker embedded in a dict
key is invisible to introspection tools and eval collectors unless they
know the specific provider's schema.

There is also a segment of code that takes the older approach: a
heredoc with `"### system\n"` separators or string concatenation, where
the structure was real at construction time but was collapsed into a
single string. For that code, the problem is that re-parsing is
required for any downstream inspection or transformation.

#### The library's answer

`@promptstring_generator` returns a
`list[PromptMessage]` — a provider-agnostic intermediate type. The
decorated generator yields `Role(...)` markers and content;
`render_messages` preserves `role`, `content`, and `source` end to end.
Because `list[PromptMessage]` sits above any one provider's dict schema,
adapter authors or user code can map it to whatever the downstream
provider expects — without touching prompt-construction code. The
library does not ship those mappings: no LLM transports are included in
the 1.0 contract (baseline Non-promise 8), and no provider dict-
conversion packages are promised. The library's contribution is the
stable, typed intermediate; the adaptation step belongs to the caller or
to a separately proposed adapter. A team that swaps providers rewrites
the mapping, not the prompt-construction code. Single-message rendering
remains available via `@promptstring`; the choice is at decoration time,
not buried in output handling.

→ Anchored by baseline Promise 1 (two decorators) and the
`PromptMessage` minimum schema declared in Promise 2.

### 5. Prompt code is invisible to observability stacks

This is the "no testability surface" limb of the organizing pathology: a prompt with no structured interface produces no structured events, leaving the observability layer blind.

A failing render today is invisible to OTel traces, structlog logs,
eval-framework collectors, and SRE dashboards unless the developer
manually instruments every call site. Even when the developer does
instrument, the instrumentation is per-application, per-call,
per-stack — there is no shared shape that observers can rely on
across codebases.

This is the lowest-acuity problem on the list, not because it is
unimportant but because it lands later in the adoption arc — a pain
that becomes acute only after the others are mostly handled and the
team is asking "why is our prompt layer the only thing not in the
dashboards?" But when it does become acute, it stays acute, and
tearing out a library to switch to one with structured observability
is expensive.

#### The library's answer

A single `Observer` Protocol with three
structured events (`RenderStartEvent`, `RenderEndEvent`,
`RenderErrorEvent`) is the only observability seam in the library.
The library itself does not import OpenTelemetry, structlog, or any
specific transport — it emits structured events to whichever
`Observer` the user attaches to a `Promptstrings()` instance.
External adapter packages (`promptstrings-otel`,
`promptstrings-structlog`, eval-framework adapters) provide
ready-made observers.

The library never makes "transport choices" for the user. Adapter
authors map structured events to their transport; the library stays
uncommitted.

The primary value of the `Observer` Protocol extends beyond per-app
convenience: it provides a stable surface for adapter authors and tool
builders that works identically across client codebases. An OTel
adapter written once works for any team that attaches it; an eval
collector that consumes `RenderEndEvent` fields works without knowing
how individual apps were built. Cross-codebase consistency is the
protocol's strongest justification.

→ Anchored by integrations Promise I-2 (Observer + events).

## Design properties

These are not user pains. They are properties of the design that
support the answers above and shape what the library promises. They
appear in this section, not in the problem list, because framing them
as user pains would overstate the case.

### **(design property)** Prompt-time dependency injection

The library exports `PromptDepends(callable)` and
`AwaitPromptDepends(callable)` as the only injection primitives.
The DI primitive exists to make strictness ergonomic at the definition
site: parameter resolution becomes a per-call declaration rather than
an assembly burden carried elsewhere. `PromptDepends` is a thin enough
primitive that external adapters (Dishka, fast-depends, custom
containers) wrap it without library cooperation.

This is not a user pain — most prompt code today does not feel
"missing dependency injection." It is a design choice that makes
problem 1's structural enforcement composable with whatever DI
framework the user already has.

### **(design property)** Static introspection of placeholders and parameters

Every `Promptstring` exposes `placeholders: frozenset[str]` and
`declared_parameters: Mapping[str, inspect.Parameter]` as attributes,
knowable without rendering and without running an event loop. This
falls out of the strict-rendering choice: the library has to compute
the placeholder set anyway in order to enforce strictness; making it
public costs nothing.

The capability serves the same audiences problem 3 serves — agents
generating code, tooling builders writing CI lints, and humans
auditing prompt schemas — but it is not a standalone pain. It is a
free byproduct of the rendering discipline.

### **(design property)** No vendor lock-in

The `promptstrings` runtime core has zero third-party dependencies
and never imports any third-party library at module top level.
Vendor-specific integration adapters — Pydantic serialization, Dishka
/ fast-depends DI helpers, OTel observers, structlog observers,
eval-framework adapters, prompt-management-system adapters — live in
separate distributions named `promptstrings-<vendor>`. They are
**not** shipped as pip extras of the core package.

This is a constraint, not a feature. It is the property that keeps the
adoption surface bounded: teams adopt the core library independently of
any specific Pydantic version, OTel SDK, LLM provider, or cloud-vendor
template registry. Each adapter is an opt-in addition, not a bundled
dependency.

→ Anchored by baseline Promise 13 (pure stdlib runtime core +
adapter-packages model).

## Audiences in detail

Two audiences with different reading paths and different success
criteria. The library is designed so the same surface serves both
without compromise; this section names what each gets.

### Humans

Humans read by scanning code, reading docstrings, encountering errors
during development, and consulting reference docs when stuck. The
library serves them by:

- making the failure modes named: every problem above maps to a named
  exception or a clear error path;
- making the API guessable: `@promptstring` looks like FastAPI's
  decorator-based DX that many Python developers already know,
  reducing learning cost;
- keeping the surface small: two decorators, one Protocol, a handful
  of types — small enough to learn in one sitting.

### LLM agents

Agents read by introspecting types, signatures, and structured error
attributes. They serve as code generators and code modifiers; they
benefit from libraries that make the right code easy to produce by
analogy. The library serves them by:

- typed exception attributes (problem 3): an agent reading a stack
  trace can extract `exc.unused_parameters` programmatically;
- introspectable promptstrings (design property): an agent can ask
  `<ps>.placeholders` to know what a prompt requires before
  rendering;
- a `runtime_checkable` `Promptstring` Protocol: an agent can write
  `isinstance(x, Promptstring)` for diagnostic code;
- consistent surface shape: the same idiom that solves problem 1
  (decorator with strict default) is the idiom that solves problem 4
  (decorator-generator); an agent that has seen the first can produce
  the second by analogy.

The two audiences converge on the same library because the choices
that serve agents (precise types, structured errors, introspectable
state) also serve humans (clearer code, better stack traces, IDE
autocomplete that actually helps). The doc treats this convergence as load-bearing. Any future design
change that improves agent-DX at the cost of human-DX, or vice versa,
should be flagged in this document as a tension before being made.

## Relationship to other docs

This VISION is the apex of the design hierarchy:

```
        VISION (this doc)              — the why
            │
            ▼
    proposals/api-1.0-baseline.md      — the contract
    proposals/api-1.0-integrations.md  — the extension surface
            │
            ▼
    decisions/                         — accepted ADRs (0001 baseline,
                                         0002 integration seams, 0003
                                         error-class field schema, 0004
                                         generator strict-mode; future
                                         ADRs numbered 0005…)
            │
            ▼
    dx/, agent-dx/                     — DX deep-dives per audience
    glossary.md                        — shared vocabulary
```

A proposal that wants to add or remove a problem from this VISION
must:
1. amend this document directly (it is living, not append-only),
2. bump `vision_version` in the frontmatter,
3. record the change in the *Revision history* below,
4. update the affected baseline / integrations promises if needed.

A proposal that does not change the problem set may freely change
baseline and integrations content without touching VISION.

## What this document does not answer

Things this VISION does **not** answer, and where to find or open
that conversation:

- *Exact API signatures and SemVer commitments.* Live in baseline /
  integrations proposals.
- *Implementation deltas needed to ship 1.0.* Live in baseline §
  Promotion to ADR.
- *Per-vendor adapter package design.* Lives in
  `dx/integration-patterns.md` (when written) and in each adapter
  package's own ADR.
- *Field-data evidence of user pain.* Not yet collected; this VISION
  is inference-framed. Bumping to `vision_version: 1.0` requires at
  least one external adopter's confirmed pain on at least the
  above-the-fold problems.

## What success looks like for VISION 1.0

The five problems above are five facets of one diagnosis: prompt code
treated as unstructured strings cannot be tested, traced, typed, or
corrected — by humans or by agents. The prompt-as-code frame is the
answer to all five at once. A developer who adopts `promptstrings`
gets a typed, versioned, inspectable object in place of an f-string; a
team gets an audit channel, structured errors, a provider-agnostic
intermediate, and an observability seam — each independently useful,
all coherent under the same organizing discipline. VISION 1.0 is
reached when at least one external adopter confirms that this framing
matches their pain. Until then, this document is inference-framed and
honest about it.

## Revision history

| Version | Date | Summary |
|---|---|---|
| 0.1 | 2026-04-26 | Initial draft. Five problems (silent variable drift; lost provenance; agent-illegible errors; multi-message structure collapse; observability blind spot) ordered acuity-then-trust. Three demoted design properties (prompt-time DI, static introspection, no vendor lock-in). Two-audience framing (humans + LLM agents). Inference-framed; no field data. |
| 0.2 | 2026-04-26 | Round 1 argumentative-integrity repair. C1: Problem 1 reframed from "silent variable drift" to structural entanglement argument; f-string NameError clarified; asymmetry note added; testability benefit added. C2: Problem 4 reframed from string-collapse to provider-coupling; list[dict] idiomatic practice acknowledged; provider-agnostic PromptMessage as the answer. C3: Problem 2 answer now explicitly states that the library provides propagation infrastructure only; provenance feature scoped to teams who have or will adopt a versioning discipline. L1: Problem 3 answer reframed as "1.0 contract commits to" for exception hierarchy, leaf classes, and to_dict(), with current core.py state noted. L2: stability claim qualified to "within the 1.x line." L3: Problem 5 cross-codebase consistency motivation added. L4: already addressed by C1 asymmetry note. Inference-overreach hedging applied at three sites (Problems 2 and 3). D1: No-vendor-lock-in property rewritten to remove pain-asserting language. D2: Static introspection proactive-generation benefit added to Problem 3 answer. D3: DI design property rewritten to describe design necessity without asserting user pain. M1: Testability benefit folded into Problem 1 answer. M2: Prompt-as-code organizing paragraph added before the problem list. |
| 0.3 | 2026-04-26 | Round 2 internal-consistency and cross-document repair. F1: corrected 0.2 revision date from 2026-04-24 to 2026-04-26. F2: replaced "definition time" with canonical glossary term "decoration time" in P1 answer. F3: disambiguated the two error channels in P1 (missing-placeholder → `PromptRenderError` via `require()`; unused resolved parameter → `PromptUnusedParameterError` via strict mode). F4: replaced "named tuple fields" with "named attributes (each a tuple of strings)" in P3 answer. F5: rewrote P4 answer to scope the library's contribution to the provider-agnostic `list[PromptMessage]` intermediate; removed claim that provider dict-conversion adapters are shipped or contracted (baseline Non-promise 8). R1: rewrote P3 opening to lead with developer-in-pain framing (debugger round-trip) before the agent-illegibility amplifier. R2: added explicit pathology-bridge sentences to P3 ("no interface contract" limb) and P5 ("no testability surface" limb). R3: removed static introspection capability description from P3 answer; replaced with a pointer to Design Properties as the canonical home. |
| 0.4 | 2026-04-26 | Round 3 reader-experience repair. G1: replaced "60-second-reader" claim with structural "first three form the above-the-fold set" language in both Purpose section and problems intro. I1: added "What success looks like for VISION 1.0" closing section; renamed "Open questions deliberately not in this doc" to "What this document does not answer" (F2). D1: prefixed Design Properties `###` headings with "(design property)" to visually distinguish from problem headings. D2: converted bold-label paragraph headers ("The library's answer," "Asymmetry note," "Important scope boundary") to `####` headings for outline-tool navigability. C1: split three-idea compound sentence in P1 answer into three sentences (strictness default; missing-value channel; unused-parameter channel). B1: removed duplicate provenance-authoring claim in P2 scope boundary. B2: removed 2.0 restructuring candidate sentence from P3 answer. A2: added agentic-loop bridge sentence in P3 to explain why the primary audience is already affected by agent-tooling errors. H1: added gloss "(the falsifiable DX rubric in the baseline)" to DX rubric R1, R6 anchor. B3: removed redundant "auto-emits zero spans" sentence in P5 (kept "never makes transport choices"). F1: renamed "Purpose & audience" to "Purpose and audiences." C2: split 43-word convergence paragraph sentence at "load-bearing." E1: added parenthetical definition of PromptSource on first use in P2. H2: added gloss to RenderEndEvent.provenance anchor in P2. A1: smoothed entry into P1 failure-mode taxonomy. A3: softened P4→P5 tonal descent with "not because it is unimportant but because it lands later in the adoption arc." B4: removed "In the design team's experience/expectation" inline hedges from P2 and P3. C3: shortened both pathology-bridge openers. E2: named the "prompt-as-string pathology" explicitly in the organizing paragraph. |
