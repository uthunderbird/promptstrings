# 0012 — Modular architecture and delegated rendering

- **Status:** Proposed
- **Date:** 2026-07-27
- **Target version:** 1.4.0 (module split), seams as noted per decision
- **Deciders:** Daniyar Supiyev
- **Supersedes:** partially revises ADR 0002 non-promises (see "Revisions to ADR 0002")
- **Superseded by:** —
- **Method:** Swarm Mode design session. Named experts: Armin Ronacher (Jinja2/Flask, evangelist/analogist), Hynek Schlawack (API minimalism, devil's advocate), Brett Cannon (packaging/SemVer, completer-finisher), Raymond Hettinger (Python idiom, reframer), Charity Majors (observability, implementer). Findings F4–F6 are tool-grounded; see "Grounding".

## Context

`core.py` is 1,401 lines with 34 top-level definitions: five error classes, three
Protocols, four public data types, two render engines (`_PromptString` 245 lines,
`_PromptStringGenerator` 214 lines), a configuration carrier, and fifteen
module-level functions. The size itself is tolerable; the problem is that the
file has no internal boundaries, so there is no unit whose responsibility can be
stated in one sentence — which is what documentation needs.

Separately, five integration directions were requested: Jinja2 as the renderer,
Phoenix/Langfuse for prompt observability, the same tools for prompt management,
OpenTelemetry spans inside prompt generators, and interop with LLM frameworks
(pydantic-ai, OpenAI, openai-agents).

ADR 0002 had already rejected four of these seams (N-1 no OTel in core, N-3 no
`DependencyResolver`, N-4 no `TemplateLoader`, N-7 no plugin registry) under a
single rationale: **lock-too-early** — do not fix a call shape before real
consumers exist. This ADR revisits those rejections with the consumers now
identified, and finds that the rationale mostly still holds, for a reason ADR
0002 did not anticipate.

**Owner constraints locked before this design iterated:**
- The 1.0 contract is not sacred; a 2.0 with breaking changes is permitted if the
  design requires it.
- Protocols are preferred over abstract base classes.
- This pass produces design only. No code changes.

## Decision

### D1 — The diagnosis is missing module boundaries, not classless functions

The request framed the fifteen module-level functions as a design smell —
functions that belong to no class. That framing is rejected for Python.

Module-level functions are idiomatic (`itertools`, `os.path`, `json` are
function-only modules). Wrapping `_parse_docstring` or `_render_static` in a
class to give them an owner would produce single-method stateless classes, which
is a function with extra syntax, and would make both reading and documentation
worse.

The observation behind the request is nonetheless correct. Those fifteen
functions are not one heap; they are **four cohesive groups with no boundary
between them**:

| Group | Functions |
|---|---|
| Signature introspection | `_get_param_type_hints`, `_annotated_markers`, `_response_schema_from_hints`, `_has_dynamic_return_annotation` |
| Template grammar and rendering | `_parse_docstring`, `parse_trusted_template`, `_render_static`, `_render_dynamic`, `_placeholders_from_template`, `_is_unrendered_prompt` |
| Dependency resolution | `_resolve_dependencies`, `_maybe_await` |
| Observability plumbing | `_fire_observer` |

The remedy is module boundaries, not class membership. Everything below follows
from that correction: if the OO justification were kept, it would pull in classes
the design does not need.

### D2 — Two classes of prompt: owned and delegated

This distinction already exists in the implementation but has never been named,
and naming it is the load-bearing move of this ADR.

**Owned prompts** — a docstring or t-string, parsed under the `{identifier}`
grammar of ADR 0005. Placeholders are known at decoration time, so `placeholders`
is populated and strict mode can reject missing and unused parameters *before*
any model call. This is the library's differentiator (VISION problem 1, design
property "static introspection").

**Delegated prompts** — the decorated function produces the text itself and
returns it. The library never parses it (ADR 0006 D1: `PromptSource` is a literal
passthrough). `placeholders` is necessarily empty, and strict mode over
placeholders is impossible in principle, not merely unimplemented.

```python
# Owned — strict, introspectable
@promptstring
def greet(name: str) -> str:
    """Hello {name}"""

greet.placeholders            # frozenset({'name'})

# Delegated — the function renders; the library types, injects, and observes
@promptstring
def system_prompt(ctx: Context, usr: User) -> PromptSource:
    return jinja2.render("path/to/prompt.jinja2", ctx=ctx, usr=usr)

system_prompt.placeholders    # frozenset() — by construction
```

**The two classes MUST be documented as carrying different guarantees.** The
predictable failure is a user writing a delegated prompt and expecting strict
checks that cannot exist there. The distinction is not a limitation to hide; it
is the contract.

Everything the library offers *besides* rendering — typed parameters, dependency
injection, provenance, observer events, `response_schema`, error legibility —
applies identically to both classes. That is what "typed stub" means concretely:
the library is a typed, DI-aware, observable wrapper around prompt text, and
rendering is one pluggable part of it rather than its centre.

### D3 — No `Renderer` Protocol

Rejected on its own merits, not for budget reasons.

A Protocol wide enough to cover both Jinja2 and the `{identifier}` grammar would
have to abstract environments, loaders, autoescaping, async rendering, custom
filters, and undefined-handling. Any such Protocol is either leaky or so narrow
that nothing interesting passes through it. Flask, whose author participated in
this session, does not hide Jinja2 behind an abstraction — it uses it and exposes
`app.jinja_env`.

The delegated model (D2) dissolves the problem instead of abstracting it: when
the function returns text, the question "which engine rendered this" never
reaches the library. Jinja2, Mustache, an LLM-generated template, or string
concatenation all work with no library support and no version coupling.

**Consequence:** requested seam 1 requires no new API surface.

### D4 — Provenance for file-backed templates is the real gap in delegated mode

What the delegated path *does* lack is ergonomics for the thing the library is
supposed to be good at. Today, recording where a template came from requires:

```python
return PromptSource(
    content=rendered,
    provenance=PromptSourceProvenance(
        source_id="path/to/prompt.jinja2", version=..., hash=...,
    ),
)
```

Nobody writes that by hand on every prompt, so provenance — VISION problem 2 —
is silently lost exactly where external templates make it most valuable.

Add a helper that derives provenance from a template file:

```python
def provenance_from_file(path: str | os.PathLike, *, provider_name: str | None = None)
    -> PromptSourceProvenance: ...
```

`source_id` is the path, `hash` is a content hash, `version` is left to the
caller. Pure stdlib; no template engine is imported. This is a convenience over
the existing type, not a new seam.

### D5 — `PromptSource` gains an opaque `handle` for vendor trace linkage

This is the only genuinely new integration requirement found, and it is grounded
rather than anticipated.

Langfuse and Phoenix prompt management both own storage *and* rendering
(`prompt.compile(**vars)`, `prompt.format(variables=...)`), so the delegated model
already covers fetching and rendering — confirming ADR 0002's N-4 rejection of
`TemplateLoader` rather than overturning it.

Linking a render to a trace, however, requires passing the vendor's *prompt
object* to the LLM generation call. A function that returns only text has
discarded that object, and `PromptSource` can carry only typed provenance
strings.

```python
@dataclass(frozen=True)
class PromptSource:
    content: str
    provenance: PromptSourceProvenance | None = None
    handle: Any = None          # new
```

**Discipline, identical to `PromptContext.extras` (ADR 0002 I-3):** the library
never reads, interprets, enumerates, or serialises `handle`. It carries it and
exposes it on `RenderEndEvent` so an observer-based adapter can perform the
linkage. `handle` is deliberately `Any`: typing it would be the lock-too-early
mistake this ADR otherwise avoids.

**Bounded:** the caller-side ergonomics of Langfuse's `propagate_attributes`
context manager were not validated end to end in this pass. The field is the
minimal enabling shape; the adapter contract belongs in a separate ADR alongside
a real adapter.

### D6 — OpenTelemetry needs no change; N-1 stands

Requested seam 3 — spans inside a prompt generator — **already works**, and this
was verified rather than assumed.

`asyncio.gather`, `create_task`, and `asyncio.wait` each copy the current context
into the spawned task. A contextvar set before dependency resolution is therefore
visible inside every resolver, including the concurrent ones. An adapter that
opens a span in `on_render_start` and activates it becomes the parent of any span
opened inside a resolver or generator body, automatically.

ADR 0002's N-1 (core does not import `opentelemetry`) and N-10 (the Observer is
not invoked from resolver tasks) both stand. N-10 restricts where *Observer
callbacks* fire; it does not restrict span nesting, which rides on contextvars.

**Known residual, recorded not solved:** the library still emits no spans for its
*own* phases — one aggregate `elapsed_ns` cannot say which of six resolvers spent
the time. This is a real observability limitation and is expected to return as a
feature request. It is out of scope here because closing it means either changing
the Observer contract or emitting spans from core, and neither is justified by a
named consumer today.

### D7 — LLM-framework interop requires nothing; no adapters

Requested seam 4 does not exist as a task. pydantic-ai's extension point is a
function returning `str` (`@agent.system_prompt def f(ctx) -> str`), satisfied by
`await prompt.render(ctx)` inside it. OpenAI's chat format is a list of
`{role, content}`, and `render_messages()` already returns `PromptMessage` with
exactly those fields; conversion is a dict comprehension.

Shipping `to_openai()` / `to_pydantic_ai()` helpers would add public surface,
vendor coupling, and a maintenance obligation to save one line. Rejected.

### D8 — Module decomposition

Nine modules. Dependencies flow one way, top to bottom; there are no cycles.

| Module | Responsibility (one sentence) | ~lines |
|---|---|---|
| `errors.py` | The exception hierarchy and its field schema (ADR 0003). | 150 |
| `types.py` | Public data types and the `Promptstring` Protocol: `PromptMessage`, `Role`, `PromptSource`, `PromptSourceProvenance`, `PromptContext`, `PromptDepends`, `AwaitPromptDepends`. | 150 |
| `observability.py` | The `Observer` Protocol, its three events, the no-op default, and exception-swallowing dispatch. | 110 |
| `introspection.py` | Reading a decorated function's signature, type hints, and `Annotated` markers. | 90 |
| `templates.py` | The owned-prompt grammar: parsing, placeholder extraction, and the two render functions. | 160 |
| `resolution.py` | Resolving declared parameters from a `PromptContext`, including concurrent async resolvers. | 90 |
| `prompts.py` | The single-message prompt engine (`_PromptString`). | 250 |
| `generators.py` | The multi-message generator engine (`_PromptStringGenerator`). | 220 |
| `factory.py` | The `Promptstrings` configuration carrier and the module-level decorator bindings. | 80 |

Dependency order: `errors` → `types` → {`observability`, `introspection`,
`templates`} → `resolution` → {`prompts`, `generators`} → `factory`.

`errors.py` and `types.py` are leaves and import nothing from the package, which
is what makes the graph acyclic and each module independently documentable.

**Recorded objection (Schlawack, not resolved in this ADR's favour):** nine
modules averaging 145 lines may navigate worse than one 1,401-line file, and
splitting by count rather than by meaning is a real failure mode. The defence is
that the split is by responsibility — each row above states its responsibility in
one sentence without conjunctions, which is the falsifiable test — not by size.
If any module cannot keep a one-sentence responsibility as the library grows, the
split was wrong there and should be revisited rather than patched.

**Recorded risk (Hettinger):** `prompts.py` and `generators.py` remain the two
largest units. They are engines with genuinely cohesive responsibility, but if
either grows past roughly 300 lines it is a signal that a further boundary is
hiding inside it.

### D9 — Public import paths do not change; `core.py` becomes a shim

All 21 public names continue to be importable as `from promptstrings import X`,
because `__init__.py` re-exports them regardless of which module now defines
them. The split is therefore **not a breaking change** and does not need the 2.0
latitude the owner granted.

`promptstrings.core` is retained as a thin re-export module for one minor-release
cycle, for anyone who imported from it directly. Versions 1.0.0, 1.1.0 and 1.2.0
are published on PyPI; adoption is unknown, and unknown is not zero.

**This decouples the two halves of the request.** D8/D9 (the split) can be
executed immediately at zero compatibility cost. D5 (the `handle` field) is
additive and can ship separately. Nothing here requires 2.0.

### D10 — Protocols over ABCs, restated

The codebase already follows this: `Observer`, `Promptstring`, and the
resolver-callable shape are all Protocols or plain callables. This ADR adds no
abstract base classes and introduces exactly one new structural type
(none — D5 adds a field, not a Protocol). The `Promptstring` Protocol remains the
documented extension surface (ADR 0001 Promise 2), which is why the D3 guard of
ADR 0011 is nominal rather than structural.

## Revisions to ADR 0002

| Non-promise | Outcome | Reason |
|---|---|---|
| **N-1** no OTel in core | **Stands** | Spans nest correctly via contextvars without core importing `opentelemetry` (D6, grounded). |
| **N-3** no `DependencyResolver` Protocol | **Stands** | No consumer named; `PromptDepends(callable)` still fits every case examined. |
| **N-4** no `TemplateLoader` Protocol | **Stands, reinforced** | Langfuse and Phoenix own rendering as well as storage, so a loader would sit at the wrong boundary (D5, grounded). |
| **N-7** no plugin registry | **Stands** | Nothing in this design needs named-backend lookup. |
| **N-10** Observer not invoked from resolver tasks | **Stands** | Restricts callback location, not span nesting (D6). |
| **N-5** no bundled Pydantic adapters | **Formally retired** | Already contradicted in practice: ADR 0007 D4 placed adapters in `src/promptstrings/integrations/` and anticipated `integrations/opentelemetry.py`. This ADR records the supersession that ADR 0007 made without stating. |

The headline result is that ADR 0002's lock-too-early reasoning **survived
contact with the actual consumers**. Four of the five requested seams need no new
Protocol; the fifth needs one opaque field.

## Alternatives considered

- **A `Renderer` Protocol with pluggable backends** — rejected (D3). No abstraction
  spans Jinja2 and the `{identifier}` grammar without leaking; the delegated model
  removes the need.

- **Jinja2 as the default renderer, own renderer removed** — rejected. It would
  discard static placeholder introspection and with it strict mode, which is the
  library's answer to VISION problem 1. The delegated model gives Jinja2 users
  everything they asked for while leaving the strict path intact for those who
  want it.

- **`TemplateLoader` Protocol for prompt-management systems** — rejected, now with
  evidence rather than caution: the vendors render as well as store.

- **Extending `Observer` with per-resolver events** — rejected for now (D6). It
  would be a contract change justified only by a limitation no named consumer has
  hit, and the requested use case is already satisfied.

- **`to_openai()` / `to_pydantic_ai()` adapters** — rejected (D7). Public surface
  and vendor coupling to save one line.

- **Three or four larger modules instead of nine** — considered seriously
  (Schlawack). Rejected because the boundary test is one-sentence responsibility,
  not file count; recorded as an open objection in D8.

- **Converting the fifteen module functions into classes** — rejected (D1).
  Un-idiomatic for Python and would worsen the documentation problem it aims to
  fix.

## Consequences

**Positive:**
- Every module has a one-sentence responsibility, which is the documentation
  precondition the request was actually about.
- The split ships with zero breaking changes and does not consume the 2.0 budget.
- Four of five requested integrations are available today with no library change;
  users are not blocked waiting on adapter work.
- Naming the owned/delegated distinction converts a hidden inconsistency into a
  stated contract.

**Negative:**
- Nine modules is more navigation surface than one file; the benefit is
  conditional on the responsibilities staying single-sentence.
- `handle: Any` is untyped by design and can become a dumping ground if the
  documented discipline is not enforced in review.
- The library still cannot show where render time goes internally (D6 residual).

**Neutral:**
- Work order: (1) split per D8 with `__init__.py` unchanged and `core.py` as a
  shim; (2) verify the full gate — tests, mypy, ruff, all examples, clean-venv
  wheel install; (3) add `provenance_from_file` (D4); (4) add `PromptSource.handle`
  and the `RenderEndEvent` field (D5); (5) document the owned/delegated
  distinction in README and a new example. Steps 1–2 are independent of 3–5.
- Follow-on ADRs anticipated: a Langfuse adapter contract (validating D5
  end to end), and — only if a consumer appears — internal-phase spans.

## Grounding

Claims marked as grounded were verified during the session rather than reasoned:

- **F4** — contextvar propagation into concurrent resolver tasks was confirmed by
  executing `asyncio.gather`, `create_task`, and `asyncio.wait` against a
  contextvar set on the parent task. All three propagated. This is what retires
  the proposed Observer change (D6).
- **F5** — pydantic-ai's dynamic system-prompt seam is a function returning `str`;
  OpenAI's chat format is `{role, content}`, already the shape of `PromptMessage`.
- **F6** — Langfuse exposes `get_prompt().compile(**vars)` and links traces by
  passing the prompt object to the generation; Phoenix exposes
  `prompts.create()` with tagged versions and `.format(variables=...)`, over
  f-string or Mustache templates.

## Notes

Method caveat, recorded for honesty: the expert team was capped at five, and the
Reframer slot was required by a contested diagnosis, so no independent Synthesizer
was seated — synthesis was carried by the Moderator. Same-session synthesis is
weaker than an independent pass. The largest single result (four of five seams
needing no change) rests on F4–F6, which are tool-grounded and independently
re-checkable; the module map in D8 is not grounded in the same sense and is the
part most worth attacking in review.

Companion ADRs: [`0001`](0001-api-and-dx-baseline-for-1.0.md) (the 1.0 contract),
[`0002`](0002-integration-seams-for-1.0.md) (integration seams, partially revised
here), [`0006`](0006-injection-safety-and-template-source-boundaries.md)
(passthrough semantics that make delegation safe),
[`0007`](0007-integrations-and-annotated-di-syntax.md) (the `integrations/`
location this ADR formalises).
