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

### D8 — The one real dependency cycle, and how it is broken

The symbol-level dependency graph of `core.py` was computed from its AST rather
than estimated: 43 top-level definitions, 90 edges. Docstrings and bare string
literals are excluded, because prose mentioning a symbol and
`getattr(fn, "__name__", "promptstring")` both produce false edges that
manufacture cycles which do not exist.

The clean graph contains **exactly one strongly connected component**:

```
_render_static  ─┐
                 ├─► _is_unrendered_prompt ─► _PromptString ────┐
_render_dynamic ─┘                        └─► _PromptStringGenerator
        ▲                                                       │
        └───────────────────────────────────────────────────────┘
```

This is the ADR 0011 D3 guard: the renderer must recognise the library's own
prompt objects, and those objects use the renderer. In a single file it was
invisible. It is a **layer inversion** — the template layer, which should know
only about strings and `Template`, currently knows about the engine layer above
it. Any split that separates rendering from the engines hits it immediately.

A second consequence: `_is_unrendered_prompt` needs *both* engine classes, so if
`prompts.py` and `generators.py` are separate modules, neither can host the guard
without importing the other.

**Decision: a private marker base class.** `types.py` defines

```python
class _PromptObject:
    """Private marker: an object this library produced and that has no
    rendered form. Not public API; do not subclass outside this package."""
```

Both engines inherit it. The guard becomes `isinstance(value, _PromptObject)` and
lives in `templates.py`, depending only on `types.py`. The cycle disappears.

Why this rather than the alternatives:

- **It keeps the check nominal, which ADR 0011 D3 requires.** The check must not
  test the public `Promptstring` Protocol, because that Protocol is the
  documented extension surface (ADR 0001 Promise 2) and a structural check would
  break third-party implementations. A private marker base is nominal by
  construction, and the public Protocol is untouched.
- **It costs nothing.** Still one `isinstance` per substituted value, on the
  hot path measured in ADR 0011 D5.
- **It does not leak.** Verified: `type(p).__mro__` is already
  `['_PromptString', 'object']`, so a private name is already observable there;
  ADR 0001 explicitly places `type(promptstring)` outside the contract; the
  object's public attributes are unchanged; and `isinstance(p, Promptstring)`
  against the public Protocol still holds.

Rejected alternatives:

- **Move the guard into the engines** (validate values before calling the
  renderer). Feasible — all four call sites of `_render_static` /
  `_render_dynamic` are inside the engines — but on the t-string path the engine
  would have to scan `tpl.interpolations` before rendering, adding a second pass
  over the interpolations to buy what the marker gives for free.
- **Function-level (deferred) import.** Hides the cycle instead of removing it,
  and `_render_static` runs once per interpolation per render, so it would put a
  `sys.modules` lookup on the hottest path in the library.
- **Keep both engines in one module.** Removes the second consequence but not the
  layer inversion, and merges two engines whose strict-mode mechanisms are
  genuinely different (ADR 0004).

### D8a — Module decomposition

Nine modules. With the cycle broken by D8, the module graph is acyclic.

| Module | Responsibility (one sentence) | ~lines |
|---|---|---|
| `errors.py` | The exception hierarchy and its field schema (ADR 0003). | 234 |
| `types.py` | Public data types, the `Promptstring` Protocol, and the private `_PromptObject` marker. | 95 |
| `observability.py` | The `Observer` Protocol, its three events, the no-op default, and exception-swallowing dispatch. | 85 |
| `introspection.py` | Reading a decorated function's signature, type hints, and `Annotated` markers. | 95 |
| `templates.py` | The owned-prompt grammar: parsing, placeholder extraction, compilation, and the two render functions. | 145 |
| `resolution.py` | Resolving declared parameters from a `PromptContext`, including concurrent async resolvers. | 90 |
| `prompts.py` | The single-message prompt engine (`_PromptString`). | 245 |
| `generators.py` | The multi-message generator engine (`_PromptStringGenerator`). | 215 |
| `factory.py` | The `Promptstrings` configuration carrier and the module-level decorator bindings. | 72 |

Dependency layers, top depending only on those below it:

```
factory
prompts, generators
resolution, templates
observability, introspection
types
errors
```

`errors.py` imports nothing from the package; `types.py` imports only `errors`.
Those two leaves are what make the graph acyclic and each module independently
documentable.

**Why `introspection` and `templates` are not merged** (Schlawack proposed it;
both "read the decorated function"). They change for different reasons, and the
release history shows it: template grammar changes with ADR 0005 syntax
decisions, while introspection changed in 1.2.0 for `response_schema` (ADR 0009)
and in ADR 0007 for `Annotated` DI. Different change drivers, different modules.

**Why `prompts` and `generators` are separate** despite being the two largest
units: their strict-mode mechanisms are not variants of one thing. `_PromptString`
checks placeholders structurally; `_PromptStringGenerator` uses a substring
heuristic (ADR 0004). Two mechanisms, two ADRs, two modules.

**Recorded objection (Schlawack, not resolved in this ADR's favour):** four of
nine modules are under 100 lines, and `factory.py` at 72 lines holding four
definitions is a file a reader opens once and never again. The criterion applied
here is not size but *whether the module has a reason to change independently of
its neighbour* — `factory` does, since the configuration carrier changes when
cross-cutting hooks are added (ADR 0002's constructor-additivity rule) and that
is independent of the engines. If a module cannot keep a one-sentence
responsibility as the library grows, the boundary was wrong and should be
revisited rather than patched.

**Recorded observation (Hettinger):** `errors.py` at 234 lines is the
second-largest module, which is surprising for a five-class hierarchy. The bulk
is the `to_dict()` contract and field schema of ADR 0003. It changes for the same
reason the errors do, so it stays — but it is the module most likely to be
hiding a further boundary.

**Recorded risk (Cannon):** once `__init__.py` imports from nine modules, an
error in the layer graph surfaces as an `ImportError` on importing the package
rather than as a subtle degradation. That is the correct failure mode, but it
makes the import test in D9 non-optional.

### D9 — Public import paths do not change; `core.py` becomes a shim

All 21 public names continue to be importable as `from promptstrings import X`,
because `__init__.py` re-exports them regardless of which module now defines
them. The split is therefore **not a breaking change** and does not need the 2.0
latitude the owner granted.

Migration is confined to the package: `from .core import (...)` occurs in exactly
one place, `__init__.py`. No test and no example imports from
`promptstrings.core` — verified by search, not assumed.

`promptstrings.core` is retained as a thin re-export module, for anyone outside
the repository who imported from it directly. Versions 1.0.0, 1.1.0 and 1.2.0 are
published on PyPI; adoption is unknown, and unknown is not zero. The shim
re-exports the private engine names as well (`_PromptString`,
`_PromptStringGenerator`), since those are what an outside debugger or test would
have reached for.

**Acceptance gates for the split** — it is done only when all of these hold:

1. `from promptstrings import X` succeeds for all 21 public names, and `__all__`
   is byte-identical to its current value.
2. `import promptstrings` raises no `ImportError` — the layer graph is only
   validated at import time (Cannon's risk in D8a).
3. `from promptstrings.core import X` still works for the 21 public names and for
   the two private engine classes.
4. The full gate is green: tests, mypy, ruff, all twelve examples, a built wheel
   installed into a clean virtualenv.
5. The independent verification script written for 1.3.0 still returns 21/21.
6. No module's public behaviour changes: the split moves code, it does not edit
   logic. Any behavioural change discovered mid-split is a separate commit.

**This decouples the two halves of the request.** D8/D8a/D9 (the split) can be
executed immediately at zero compatibility cost. D5 (the `handle` field) is
additive and can ship separately. Nothing here requires 2.0.

### D10 — Protocols over ABCs, and the one deliberate exception

Every *extension surface* in this library is a Protocol or a plain callable:
`Observer`, `Promptstring`, and the `PromptDepends` resolver shape. This ADR adds
no new extension surface and therefore no new Protocol; D5 adds a field, not a
type.

`_PromptObject` (D8) is a base class, not a Protocol, and that is a deliberate
exception rather than an oversight. The reasoning is the same one ADR 0011 D3
used to reject a structural check:

- A Protocol is the right tool when you want to admit *anyone* who matches the
  shape. Here the requirement is the exact opposite — the guard must fire for
  **only** this library's own objects and must **not** fire for third-party
  implementations of `Promptstring`, which may define a meaningful `__str__` and
  legitimately substitute as text.
- Structural typing cannot express "mine, specifically." Nominal typing can, and
  a private base class is the minimal nominal marker Python offers.

So the rule is preserved in substance: Protocols for anything users implement,
nominal types only for identity the library asserts about its own objects.
`_PromptObject` is private, documented as not-for-subclassing, carries no
methods, and adds no public attributes.

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
- **F7** — the symbol-level dependency graph was computed from the AST of
  `core.py`: 43 definitions, 90 edges, exactly one strongly connected component
  (D8). An earlier run of the same analysis reported thirteen cyclic symbols;
  that was an artefact of counting docstring prose and bare string literals as
  references, and the design was not allowed to proceed on it. The corrected
  analysis excludes both.
- **F8** — `type(p).__mro__` already exposes the private `_PromptString`, the
  object's public attributes are five names unrelated to the marker, and
  `isinstance(p, Promptstring)` holds — so `_PromptObject` changes nothing
  observable that the contract covers.
- **F9** — `from .core import (...)` appears in exactly one file in the
  repository (`__init__.py`); no test or example imports `promptstrings.core`.

## Notes

Method caveat, recorded for honesty: the expert team was capped at five, and the
Reframer slot was required by a contested diagnosis, so no independent Synthesizer
was seated — synthesis was carried by the Moderator. Same-session synthesis is
weaker than an independent pass.

The seam results (D3–D7) rest on F4–F6; the decomposition (D8–D8a) rests on
F7–F9. All are tool-grounded and independently re-checkable, and the analysis
script that produced F7 is worth re-running after the split to confirm the module
graph matches the design.

What remains *not* grounded is the boundary placement itself: the graph proves
which splits are **possible** (acyclic), not which are **best**. The argument
that `introspection` and `templates` change for different reasons is an appeal to
release history, and the argument that `factory` deserves its own module is an
appeal to a future that has not happened. Those two are the weakest claims in
this ADR and the right targets for review.

Companion ADRs: [`0001`](0001-api-and-dx-baseline-for-1.0.md) (the 1.0 contract),
[`0002`](0002-integration-seams-for-1.0.md) (integration seams, partially revised
here), [`0006`](0006-injection-safety-and-template-source-boundaries.md)
(passthrough semantics that make delegation safe),
[`0007`](0007-integrations-and-annotated-di-syntax.md) (the `integrations/`
location this ADR formalises).
