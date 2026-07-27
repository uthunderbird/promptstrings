# 0012 — Modular architecture and delegated rendering

- **Status:** Proposed
- **Date:** 2026-07-27
- **Target version:** 1.4.0 (module split), seams as noted per decision
- **Deciders:** Daniyar Supiyev
- **Supersedes:** retires ADR 0002 non-promise N-5; conditionally amends ADR 0002 Promise I-2 (held, see D5). Full table in "Revisions to ADR 0002"
- **Superseded by:** —
- **Method:** Swarm Mode design session. Named experts: Armin Ronacher (Jinja2/Flask, evangelist/analogist), Hynek Schlawack (API minimalism, devil's advocate), Brett Cannon (packaging/SemVer, completer-finisher), Raymond Hettinger (Python idiom, reframer), Charity Majors (observability, implementer). Findings F4–F12 are tool-grounded; see "Grounding". Hardened by four independent cold adversarial reviews; see "Notes".

## Context

`core.py` is 1,401 lines with **43 top-level bindings**, counted from the AST:
21 classes, 14 functions, and 8 module-level assignments. The classes are five
errors, two Protocols (`Observer`, `Promptstring`), three Observer events, seven
public data types, the no-op observer, two render engines (`_PromptString` 243
lines, `_PromptStringGenerator` 212), and the `Promptstrings` configuration
carrier. Every count in this ADR uses this same 43-binding census; where a table
below claims to partition the file, it partitions all 43.

The size itself is tolerable; the problem is that the file has no internal
boundaries, so there is no unit whose responsibility can be stated in one
sentence — which is what documentation needs.

Separately, five integration directions were requested: Jinja2 as the renderer,
Phoenix/Langfuse for prompt observability, the same tools for prompt management,
OpenTelemetry spans inside prompt generators, and interop with LLM frameworks
(pydantic-ai, OpenAI, openai-agents).

ADR 0002 had already rejected four of these seams: N-1 (no OTel in core), N-3 (no
`DependencyResolver`), N-4 (no `TemplateLoader`), N-7 (no plugin registry). Their
rationales differ — N-3 and N-4 rest on **lock-too-early** (do not fix a call
shape before real consumers exist), N-1 on vendor-neutrality and the
adapter-package model, and N-7 is stated without one. This ADR revisits all four
with the consumers now identified, and finds each still standing — two of them (N-1, N-4) for reasons
ADR 0002 did not anticipate, and two (N-3, N-7) for their original ones.

**Owner constraints locked before this design iterated:**
- The 1.0 contract is not sacred; a 2.0 with breaking changes is permitted if the
  design requires it.
- Protocols are preferred over abstract base classes.
- This pass produces design only. No code changes.

## Decision

### D1 — The diagnosis is missing module boundaries, not classless functions

The request framed the module-level functions as a design smell —
functions that belong to no class. That framing is rejected for Python.

Module-level functions are idiomatic (`itertools`, `os.path`, `json` are
function-only modules). Wrapping `_parse_docstring` or `_render_static` in a
class to give them an owner would produce single-method stateless classes, which
is a function with extra syntax, and would make both reading and documentation
worse.

The observation behind the request is nonetheless correct. All **14** module-level
functions are not one heap; they are **four cohesive groups with no boundary
between them**:

| Group | Functions | n |
|---|---|---|
| Signature introspection | `_get_param_type_hints`, `_annotated_markers`, `_response_schema_from_hints`, `_has_dynamic_return_annotation` | 4 |
| Template grammar and rendering | `_parse_docstring`, `parse_trusted_template`, `_render_static`, `_render_dynamic`, `_placeholders_from_template`, `_is_unrendered_prompt`, `_compile_at_decoration` | 7 |
| Dependency resolution | `_resolve_dependencies`, `_maybe_await` | 2 |
| Observability plumbing | `_fire_observer` | 1 |

`_compile_at_decoration` is the function that most sharply straddles two of these
groups (`_resolve_dependencies` also reaches across, calling `_annotated_markers`,
but its home is not in doubt):
it calls `_has_dynamic_return_annotation` (introspection) *and* `_parse_docstring`
(templates). It is assigned to the template group because its **output** is a
compiled `Template` and its failure mode is `PromptCompileError` — it consumes
introspection rather than belonging to it. This is the sharpest test of the
`introspection` / `templates` boundary defended in D8a, so it is named here
rather than left implicit.

The remedy is module boundaries, not class membership. Everything below follows
from that correction: if the OO justification were kept, it would pull in classes
the design does not need.

### D2 — Three classes of prompt: owned-static, owned-dynamic, delegated

These distinctions already exist in the implementation but have never been named,
and naming them is the load-bearing move of this ADR.

**Owned-static prompts** — a docstring, parsed at decoration time under the
`{identifier}` grammar of ADR 0005. Placeholders are known before any render, so
`placeholders` is populated and strict mode can reject missing and unused
parameters *before* any model call. This is the library's differentiator (VISION
problem 1, design property "static introspection").

**Owned-dynamic prompts** — the function returns a `Template`, either a t-string
or the output of the public `parse_trusted_template`. The library still renders
this itself and still enforces strict mode, but at render time rather than
decoration time, so `placeholders` is empty while missing-parameter and
unused-parameter checks both still fire. Provenance is `None` on this path.

**Delegated prompts** — the function returns a `PromptSource`. The library never
parses it (ADR 0006 D1: literal passthrough). `placeholders` is necessarily empty,
strict mode over placeholders is impossible in principle rather than merely
unimplemented, and this is the only path that carries provenance.

**Three classes, not two.** An earlier draft of this ADR called the distinction
two-way and treated `-> Template` as delegated. That was wrong:
`_has_dynamic_return_annotation` routes on `PromptSource` **or** `Template`, and
the two branches behave differently in exactly the properties this ADR is about.
The middle class matters because `parse_trusted_template` is public and is the
natural landing point for a prompt loaded from a database or a prompt-management
system — precisely the case D5 and ADR 0002's N-4 discuss.

A fourth shape does *not* exist: a docstring-less function annotated `-> str`
routes nowhere and raises `PromptCompileError` at decoration.

```python
# Owned-static — strict before render, introspectable at decoration
@promptstring
def greet(name: str) -> str:
    """Hello {name}"""

greet.placeholders            # frozenset({'name'})

# Owned-dynamic — library still renders and still strict-checks, at render time
@promptstring
def from_store(name: str) -> Template:
    return parse_trusted_template(load_from_db("greeting"))

from_store.placeholders       # frozenset() — not known until render

# Delegated — the function renders; the library types, injects, and observes
_env = jinja2.Environment(loader=jinja2.FileSystemLoader("prompts"))

@promptstring
def system_prompt(usr: User) -> PromptSource:
    text = _env.get_template("system.jinja2").render(usr=usr)
    return PromptSource(content=text, provenance=provenance_from_file("prompts/system.jinja2"))

system_prompt.placeholders    # frozenset() — by construction
```

The example is written out in full deliberately. Jinja2 has no module-level
`render(path, **kw)`; and returning the bare `str` that `_env...render()` produces
would satisfy the runtime — `_resolve_source` accepts a plain `str` — while
failing `mypy` against the `-> PromptSource` annotation that
`_has_dynamic_return_annotation` requires in order to route the function to the
delegated path at all. Wrapping in `PromptSource` is not decoration: it is what
makes the annotation true *and* what gives provenance somewhere to live (D4).

**The three classes MUST be documented as carrying different guarantees.** The
predictable failure is a user writing a delegated prompt and expecting strict
checks that cannot exist there. The distinction is not a limitation to hide; it
is the contract.

Most of what the library offers besides rendering — typed parameters, dependency
injection, observer events, error legibility — applies to all three classes. That is
what "typed stub" means concretely: the library is a typed, DI-aware, observable
wrapper around prompt text, and rendering is one pluggable part of it rather than
its centre.

**But the guarantees are not otherwise symmetric, and the asymmetries run in both
directions.** An earlier draft of this ADR claimed they did apply identically;
that was false, and the exceptions are structural rather than incidental:

| Capability | Owned-static (docstring) | Owned-dynamic (`-> Template`) | Delegated (`-> PromptSource`) |
|---|---|---|---|
| `placeholders` at decoration | **yes** | no — not known until render | no — never parsed |
| strict mode (missing / unused) | yes, before render | **yes**, at render | **no** — impossible in principle |
| `response_schema` | **yes** | no | no |
| provenance | no | no | **yes** |
| available on `@promptstring_generator` | yes | yes | **no** |

Three of those cells are the ones worth stating aloud:

- **`response_schema` is unavailable outside owned-static.**
  `_response_schema_from_hints` returns `None` for `str`, `Template`, and
  `PromptSource`, and the latter two are exactly the annotations that select the
  other two classes. So a user cannot have both a Jinja2-rendered prompt and a
  typed response schema on one `@promptstring`. That is a real cost of D3, not a
  detail, and this ADR does not fix it.
- **Provenance exists only on the delegated path.** Both owned paths set
  `provenance = None` unconditionally. The library's answer to VISION problem 2 is
  therefore reachable only by returning a `PromptSource` — which is what makes D4
  worth having rather than optional polish.
- **Strict mode survives into owned-dynamic.** Only full delegation gives it up.
  A user who wants an external template *and* strict checking has a middle option:
  load the text, hand it to `parse_trusted_template`, and return the `Template`.
  They trade provenance for strictness. Neither this ADR nor the code lets them
  have both, and that trade should be documented rather than discovered.

The `response_schema` exclusion is the sharp one: structured output is unavailable
in delegated mode *by the same mechanism* that enables delegated mode. A user
cannot have both a Jinja2-rendered prompt and a typed response schema on the same
`@promptstring`. That is a real cost of D3, not a detail, and it is not fixed by
this ADR.

**Delegation does not exist for `@promptstring_generator`.** The generator engine
accepts only `Role`, `PromptMessage`, `str`, and `Template` yields and raises
`PromptRenderError("Unsupported promptstring generator yield type")` for anything
else — a generator cannot yield or return a `PromptSource`. Consequently D4
(file-backed provenance) and D5 (`handle`) are unreachable from generators, whose
`RenderEndEvent` hardcodes `provenance=None`.

This is uncomfortable, because the vendors D5 is grounded on produce
**multi-message** chat prompts — the shape the generator engine exists for. So the
scope of this ADR's delegated model must be stated exactly: **it is designed and
argued for `_PromptString` only.** Extending delegation to the generator engine is
a real piece of work (a `PromptSource` yield type, provenance per message, and a
decision about whether provenance is per-message or per-render) and is
deliberately **not** decided here.

`[HELD — owner decision]` Whether to extend delegation to generators before or
after the split. The recommendation is after: it is a feature with its own design
questions, while the split is a zero-behaviour-change refactor, and bundling them
would make the refactor unverifiable by the "moves code, does not edit logic"
gate in D9.

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

**Consequence:** requested seam 1 requires **no new Protocol and no new type**. It
is not free of API surface: D4 adds one public helper function for the provenance
this path would otherwise lose. The precise claim is "no abstraction layer, one
convenience function," and the running total of new public surface across this ADR
is stated in D5a.

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
def provenance_from_file(
    path: str | os.PathLike[str],
    *,
    version: str | None = None,
    provider_name: str | None = None,
) -> PromptSourceProvenance: ...
```

- `source_id` is `PurePath(path).as_posix()` — **not** `str(path)`, and not
  resolved to an absolute path. Absolute paths are machine-specific, and
  `str(path)` on Windows yields backslash separators, so the same template in the
  same repository would produce different `source_id`s on different developers'
  machines. That defeats the one property this helper exists to provide.
- `hash` is `"sha256:" + sha256(file_bytes).hexdigest()` over the **raw bytes**.
  Fixing the algorithm and the encoding is the point: a provenance hash that
  differs between machines is not provenance. The `sha256:` prefix matches the
  format already used in the ADR 0007 examples.

  Raw bytes means **no newline normalisation**, which is a deliberate trade with a
  cost: a repository checked out with `core.autocrlf=true` on Windows hashes
  differently from the same commit on Linux. Normalising would hide a real
  difference in what was sent to the model, so the hash stays byte-exact and the
  cross-platform caveat is documented instead.
- `version` is a parameter, not something the caller patches in afterwards. An
  earlier draft omitted it and told the caller to supply `version` separately,
  which would have meant a `dataclasses.replace()` at every call site — exactly
  the by-hand work this helper exists to remove.

**Trust boundary.** `provenance_from_file` is the only code in the package that
touches the filesystem, and the path comes from the caller. It reads the whole
file to hash it, so a caller who passes a path they do not control has an
unbounded read and follows symlinks. The helper does no validation: the path is
caller-supplied and caller-trusted, the same posture the library takes toward
resolver callables. That is a deliberate position, not an oversight, and it is
stated so a reviewer can disagree with it. It also means the helper should not be
called per-render on a hot path — it is a decoration-time or startup-time
convenience.

Pure stdlib (`hashlib`, `pathlib`); no template engine is imported. **Home
module:** `types.py`, beside `PromptSourceProvenance` which it constructs. It is
the only file-reading code in the package, which is worth noting in review; if a
second such helper ever appears, they belong together elsewhere.

This is a convenience over an existing type, not a new seam — but it *is* new
public surface, counted in D5a.

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
    handle: Any = field(default=None, compare=False, repr=False, hash=False)  # new
```

**The field modifiers are load-bearing, not style.** `PromptSource` is
`@dataclass(frozen=True)`, so `__eq__`, `__hash__`, and `__repr__` are generated
over every field. A plain `handle: Any = None` was verified to change all three:
`hash(PromptSource("x", None, {"a": 1}))` raises `TypeError: unhashable type:
'dict'` where the two-field version hashes fine, two renders of identical text
compare unequal when different vendor objects ride along, and `repr()` leaks the
vendor object into logs and assertion diffs. With `compare=False, repr=False,
hash=False` the field stops affecting equality, hashing, and repr.

It is **not** fully inert, and the difference matters: `dataclasses.asdict()`
still returns `handle`, because `field()` has no asdict exclusion. Verified. So
the library's own repr is protected, while any third-party observer that runs
`asdict()` on the event and ships the result to a vendor will carry the handle
with it. At that boundary the discipline is a convention, not a mechanism.

The `PromptContext.extras` precedent (ADR 0002 I-3) does **not** transfer
unexamined: `extras` defaults to a `dict`, so `PromptContext` is unhashable —
`hash()` raises `TypeError`. (It does have value equality; an earlier draft
claimed otherwise and that was wrong. Unhashability alone carries the argument.)
The discipline sentence was free there and is not free here.

**Discipline:** the library never reads, interprets, or enumerates `handle`; with
the modifiers above it also never serialises it. It carries it and exposes it on
`RenderEndEvent`. `handle` is deliberately `Any`: typing it would be the
lock-too-early mistake this ADR otherwise avoids.

**This amends a numbered Promise, not a non-promise.** `RenderEndEvent` is defined
verbatim in ADR 0002 **Promise I-2** as an exact four-field frozen dataclass.
Exposing `handle` on it widens a 1.0 promise, which the revisions table below now
records. The amendment is append-only and keyword-safe:

```python
@dataclass(frozen=True)
class RenderEndEvent:
    prompt_name: str
    elapsed_ns: int
    message_count: int
    provenance: PromptSourceProvenance | None
    handle: Any = field(default=None, compare=False, repr=False, hash=False)  # new
```

Existing observers keep working; existing positional construction keeps working
because the new field is last and defaulted.

**Bounded, and honestly so.** Two things are *not* established here:

1. **The caller-side path.** `render()` returns `str` and `render_messages()`
   returns `PromptMessage`; neither carries `handle`. Only the Observer sees it.
   Langfuse's own mechanism (`propagate_attributes(prompt=...)`, SDK ≥ 4.14) is a
   context manager wrapping the generation call, so an observer *can* set it — but
   this was not validated end to end.
2. **Whether the field is necessary at all.** In delegated mode the user's own
   function constructed the vendor prompt object, so the user already holds it and
   can pass it to their own generation call with no library involvement. `handle`
   earns its place only if the linkage should work *without* the call site knowing
   about it.

`[HELD — owner decision]` D5 ships only if (2) is answered yes. Until then it is a
recommendation with a validated shape, not a committed change. The recommendation
is to **defer D5 to the adapter ADR** and build a real Langfuse adapter first: a
field added for a linkage nobody has performed is exactly the lock-too-early
mistake this ADR credits ADR 0002 for avoiding.

### D5a — Total new public surface

| Item | Kind | Status |
|---|---|---|
| `provenance_from_file` | new function | proposed (D4) |
| `PromptSource.handle` | new field on existing type | held (D5) |
| `RenderEndEvent.handle` | new field on existing type, amends Promise I-2 | held (D5) |

If D5 is deferred as recommended, this ADR's entire net public surface change is
**one helper function**. The split itself (D8–D9) adds nothing.

### D6 — OpenTelemetry needs no change; N-1 stands

Requested seam 4 — spans inside a prompt generator — **already works**, and this
was verified rather than assumed.

The library resolves concurrent async dependencies with
`asyncio.ensure_future(...)` followed by
`asyncio.wait(..., return_when=FIRST_EXCEPTION)` — deliberately **not**
`asyncio.gather`, per ADR 0008 (gather leaves siblings running). `ensure_future`
creates a Task, and task creation copies the current context; `asyncio.wait`
itself spawns nothing and is not a propagation mechanism.

Verified against those exact primitives: a contextvar set before dependency
resolution is visible inside every concurrently-resolved resolver. An adapter that
opens a span in `on_render_start` and activates it therefore becomes the parent of
any span opened inside a resolver or generator body, automatically.

ADR 0002's N-1 (core does not import `opentelemetry`) and N-10 (the Observer is
not invoked from resolver tasks) both stand. N-10 restricts where *Observer
callbacks* fire; it does not restrict span nesting, which rides on contextvars.

**Known residuals, recorded not solved:**

- The library emits no spans for its *own* phases — one aggregate `elapsed_ns`
  cannot say which of six resolvers spent the time. Closing it means changing the
  Observer contract or emitting spans from core, and neither is justified by a
  named consumer today.
- The propagation test covers task creation. **Not** tested: a synchronous
  observer holding an OTel context across the `await` boundary between
  `on_render_start` and `on_render_end` (attach/detach spanning suspension is
  where OTel context leaks between concurrent renders), and sync resolvers
  dispatched to a thread executor. An adapter author must validate both; this ADR
  claims nesting works, not that every OTel usage pattern is safe.

### D7 — LLM-framework interop needs no adapters

Requested seam 5 needs no library change, but "requires nothing" was too strong.

pydantic-ai's extension point is a function returning `str`
(`@agent.system_prompt def f(ctx) -> str`). Its `ctx` is a `RunContext`, not a
`PromptContext`, so the call site is `await prompt.render(PromptContext({...}))`
with a small mapping step — not a bare pass-through. OpenAI's chat format is a
list of `{role, content}`; `render_messages()` returns `PromptMessage`, which has
three fields (`role`, `content`, `source`) and an unconstrained `role: str`, so
conversion is a dict comprehension that drops `source` and trusts the role value.

Both costs are one line at the call site. That is the actual claim: **small and
call-site-local, not zero.**

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
- **It costs nothing.** Still one `isinstance` per substituted value — the same
  guard ADR 0011 D3 introduced, unchanged in kind and count. (The measurements in
  ADR 0011 D5 priced *container-walking*, not this check; they are not evidence
  for this bullet and are not cited as such.)
- **What it changes is enumerable, and none of it is contract.** Inserting a base
  is not a no-op, so the honest form is a list rather than an appeal to what is
  already visible. Changed: `__bases__`, `__base__`, `__mro__` (from
  `(_PromptString, object)` to `(_PromptString, _PromptObject, object)`), and
  `isinstance(p, _PromptObject)` becomes `True`. Unchanged and verified: the
  object's five public attributes (`declared_parameters`, `placeholders`,
  `render`, `render_messages`, `response_schema`), and `isinstance(p, Promptstring)`
  against the public Protocol. The engines are plain classes — no `@dataclass`, no
  `__slots__` — so there is no dataclass, slots, or pickle-protocol interaction,
  and `Promptstring` is a data Protocol where `runtime_checkable` `isinstance`
  remains legal.

  Note what is *not* being cited: ADR 0001 places `type(promptstring)` — the
  **decorator object** — outside the contract, which says nothing about
  `type(p)` for a decorated prompt. The argument stands on the enumeration above,
  not on that clause. The one population that could observe a difference is
  anyone subclassing an engine, which no promise supports and no code in this
  repository does.

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

This table is a **complete assignment of all 43 existing top-level bindings**,
plus the one new `_PromptObject` marker (44 rows) — not a prose
summary — an executor should not have to re-derive where anything goes. Line
figures are measured definition bodies and exclude each module's imports and
docstring, which is why they sum to less than 1,401.

| Module | Responsibility (one sentence) | Bindings | body lines |
|---|---|---|---|
| `errors.py` | The exception hierarchy and its field schema (ADR 0003). | `PromptRenderError`, `PromptCompileError`, `PromptStrictnessError`, `PromptUnusedParameterError`, `PromptUnreferencedParameterError` | 234 |
| `types.py` | Public data types, the `Promptstring` Protocol, and the private `_PromptObject` marker. | `_PromptObject` (new), `Promptstring`, `PromptMessage`, `Role`, `PromptSourceProvenance`, `PromptSource`, `PromptContext`, `Resolver`, `PromptDepends`, `AwaitPromptDepends` | 104 |
| `observability.py` | The `Observer` Protocol, its three events, the no-op default, and exception-swallowing dispatch. | `RenderStartEvent`, `RenderEndEvent`, `RenderErrorEvent`, `Observer`, `_NoOpObserver`, `_observer_logger`, `_fire_observer` | 89 |
| `introspection.py` | Reading a decorated function's signature, type hints, and `Annotated` markers. | `_INTERNAL_RETURN_TYPES`, `_get_param_type_hints`, `_annotated_markers`, `_response_schema_from_hints`, `_has_dynamic_return_annotation` | 92 |
| `templates.py` | The owned-prompt grammar: parsing, placeholder extraction, compilation, and the two render functions. | `_MISSING`, `_parse_docstring`, `parse_trusted_template`, `_placeholders_from_template`, `_is_unrendered_prompt`, `_render_static`, `_render_dynamic`, `_compile_at_decoration` | 157 |
| `resolution.py` | Resolving declared parameters from a `PromptContext`, including concurrent async resolvers. | `_maybe_await`, `_resolve_dependencies` | 87 |
| `prompts.py` | The single-message prompt engine (`_PromptString`). | `_PromptString` | 243 |
| `generators.py` | The multi-message generator engine (`_PromptStringGenerator`). | `_strict_heuristic_logger`, `_PromptStringGenerator` | 213 |
| `factory.py` | The `Promptstrings` configuration carrier and the module-level decorator bindings. | `Promptstrings`, `_default`, `promptstring`, `promptstring_generator` | 71 |

Two placements deserve their reasons stated, because they were the only genuinely
ambiguous ones:

- **`_compile_at_decoration` → `templates.py`.** It calls into both introspection
  and templates (see D1). It goes with templates because its output is a compiled
  `Template` and its failure mode is `PromptCompileError`; it *consumes*
  introspection rather than belonging to it. The resulting edge
  `templates → introspection` runs downward and creates no cycle.
- **`_MISSING` → `templates.py`.** It is an identity sentinel, so placement is a
  correctness decision, not formatting: `_parse_docstring` constructs it and
  `_PromptString` tests `i.value is _MISSING` to detect `parse_trusted_template`
  output. One definition site, imported by `prompts.py`; the edge is `prompts →
  templates`, downward, which is the allowed direction.

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
units. An earlier draft argued this from strict-mode mechanism — structural in
one engine, substring-heuristic in the other. That argument is **wrong** and is
retracted: the generator computes `all_structured` and takes the structural path
when its yields are all `Template`s with resolvable identifier expressions,
falling back to the heuristic only for `str` and mixed yields. The two engines
share the mechanism.

The surviving reasons are weaker and are stated as such:

1. The engine classes are 243 and 212 lines and have no call edge between them — the only two
   symbols of that size in the file that are mutually independent.
2. Their *yield contracts* genuinely differ: one produces a single string from one
   template; the other consumes a stream of `Role` / `PromptMessage` / `str` /
   `Template` yields and does not support `PromptSource` at all (D2). That
   difference is what makes delegation available to one and not the other, so it
   is a real behavioural boundary rather than a stylistic one.

This is the weakest boundary in the table. Merging them into one ~460-line
`prompts.py` is a defensible alternative and would not violate any layer rule.

**Recorded objection (Schlawack, not resolved in this ADR's favour):** four of
nine modules are under 100 lines, and `factory.py` at 71 lines holding four
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

`promptstrings.core` is retained as a re-export module for anyone outside the
repository who imported from it directly. Versions 1.0.0, 1.1.0 and 1.2.0 are
published on PyPI; adoption is unknown, and unknown is not zero.

**The shim re-exports all 43 bindings, not a chosen subset.** Re-exporting only
the public 21 plus the two engines would break the very population the shim exists
for — an outside debugger or test reaching for `_render_static`, `_MISSING`, or
`_resolve_dependencies`. Since the shim is mechanical, completeness is free.

Two shim properties the repository's own tooling forces, which a naive
`from .errors import X` would fail:

- `pyproject.toml` sets `mypy strict = true`, hence `no_implicit_reexport`, so
  downstream typed code doing `from promptstrings.core import X` fails unless the
  shim declares its own `__all__` (or uses `X as X`). The shim therefore carries
  an `__all__` listing all 43 names.
- `ruff` selects `F`, so unused re-exports trip `F401`. The `__all__` declaration
  resolves this too.

**What the shim cannot preserve, stated plainly:** re-export does not preserve
monkeypatch targets. `monkeypatch.setattr("promptstrings.core._render_static", ...)`
currently changes library behaviour; after the split the library resolves that
name in `templates.py` and the patch becomes a silent no-op. Anyone patching
internals must retarget to the defining module. This is a real break for a real
(if small) population, and no gate below detects it — it is accepted and
documented, not solved.

**Pickle:** pickled instances embed the defining module, verified —
`pickle.dumps(PromptRenderError("x"))` currently emits `promptstrings.core`. Old
pickles keep loading through the shim, but pickles produced *after* the split
cannot be loaded by any released version (1.0.0–1.2.0, or a locally built 1.3.0).
For mixed-version workers this is a genuine
wire-format change. The precise claim is therefore: **no source-level break;
pickle payload module paths change.**

**Acceptance gates for the split.** Gates 5–7 compare against a **baseline that
must be captured before any file is touched** (see Execution, step 0); after the
split, `core.py` no longer holds the definitions to compare with. Each gate names
one property and can fail on its own.

| # | Gate | Mechanism |
|---|---|---|
| 1 | All 21 public names import from `promptstrings`, and `promptstrings.__all__` is unchanged | compare against the baseline `__all__` |
| 2 | `import promptstrings` raises no `ImportError` | plain import in a fresh interpreter |
| 3 | All **43** pre-split names import from `promptstrings.core` | iterate the baseline name list |
| 4a | Tests pass | `make test` |
| 4b | Types clean | `make typecheck` |
| 4c | Lint clean | `make lint` |
| 4d | All twelve examples run | the loop CI already uses |
| 4e | A built wheel installs and imports in a clean virtualenv | `uv build`, then `uv venv` + `uv pip install <wheel>` + import check |
| 5 | Import-surface equivalence: names reachable from `promptstrings` and `promptstrings.core` equal the baseline sets | committed script |
| 6 | The split moves code, it does not edit logic | AST source-text comparison, with the three exceptions below |
| 7 | No cross-module cycle | committed script |

**Gates 5, 6 and 7 require committed scripts, not ad-hoc ones.** An earlier draft
named a verification script that existed only in a scratch directory, which is not
a gate. Concretely: one script captures the baseline and checks gates 1/3/5,
another does the AST comparison for gate 6, and gate 7 is the F7 dependency
analysis generalised from symbols to modules — it must report the module-level
import graph and assert it is a DAG. Gate 7 is not redundant with gate 2: a
successful import proves no *runtime* cycle, while a layering violation can import
fine and still be a violation.

**Gate 6's three permitted deltas.** Byte-identity cannot hold universally,
because the cycle fix in D8 *is* an edit to three definitions. The exception list
is exactly:

1. `_is_unrendered_prompt` — body becomes `isinstance(value, _PromptObject)`.
2. `class _PromptString` — gains `_PromptObject` as a base.
3. `class _PromptStringGenerator` — gains `_PromptObject` as a base.

Plus, mechanically and for every moved definition: `import` statements change,
since each module imports what it uses. Gate 6 therefore compares **definition
bodies excluding the module preamble**, and asserts that the only body deltas are
the three above. Any fourth delta fails the gate and belongs in its own commit.

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

## Execution

Everything an engineer needs to perform the split is D8 (the marker), D8a (the
module table), and D9 (the shim and the gates). This section is the order to do
it in; the rest of the ADR is the reasoning behind it and is not required reading
to execute.

**Step 0 — capture the baseline. Before touching any file.**
Gates 1, 3, 5 and 6 all compare against pre-split state that stops existing once
the split begins. Commit a script that records, from the current `core.py`:
the 43 top-level binding names, `promptstrings.__all__`, the set of names
reachable from `promptstrings` and `promptstrings.core`, and each definition's
source text keyed by name. `git show` can recover this later, but a committed
baseline makes the gates runnable by anyone, not just in this working tree.

**Step 1 — create the nine modules per the D8a table.** Move definitions
unchanged. Add `_PromptObject` to `types.py`, apply D8's three permitted deltas,
and nothing else.

**Step 2 — make `core.py` the shim.** Re-export all 43 names with an explicit
`__all__` (required by `mypy strict` / `no_implicit_reexport` and by `ruff` F401).

**Step 3 — leave `promptstrings/__init__.py` alone except for its import source.**
Its `__all__` does not change; only the modules it imports from.

**Step 4 — run all seven gates.** Any failure stops the split rather than being
patched around.

Steps 0–4 are the whole split, and they change no behaviour. The following are
**separate** pieces of work with their own commits, deliberately not bundled:

**Step 5 — add `provenance_from_file` (D4)** to `types.py`, extending
`promptstrings.__all__` to 22 names and the shim's list to 44. Note that this
means gate 1 ("`__all__` unchanged") is scoped to steps 0–4; it is intentionally
violated here, by a change with its own justification.

**Step 6 — document the owned/delegated distinction (D2)** in the README and as a
new example, including the asymmetry table.

**Not scheduled:** D5 (`handle`) is held pending the owner decision, and
delegation for the generator engine is a feature with its own design questions.
Neither belongs in the split.

## Revisions to ADR 0002

| Clause | Outcome | Reason |
|---|---|---|
| **N-1** no OTel in core | **Stands** | Spans nest correctly via contextvars without core importing `opentelemetry` (D6, grounded). |
| **N-3** no `DependencyResolver` Protocol | **Stands** | No consumer named; `PromptDepends(callable)` still fits every case examined. |
| **N-4** no `TemplateLoader` Protocol | **Stands, reinforced** | Langfuse and Phoenix own rendering as well as storage, so a loader would sit at the wrong boundary (D5, grounded). |
| **N-7** no plugin registry | **Stands** | Nothing in this design needs named-backend lookup. |
| **N-10** Observer not invoked from resolver tasks | **Stands** | Restricts callback location, not span nesting (D6). |
| **N-5** no bundled Pydantic adapters | **Formally retired** | Already contradicted in practice: ADR 0007 D4 placed adapters in `src/promptstrings/integrations/` and anticipated `integrations/opentelemetry.py`. This ADR records the supersession that ADR 0007 made without stating. |
| **Promise I-2** `RenderEndEvent` four-field shape | **Amended if and only if D5 ships** | D5 appends a defaulted, non-comparing `handle` field. This is a **promise-level** change, not a non-promise revision. It is held pending the D5 decision; if D5 is deferred as recommended, I-2 is untouched. |

Two clarifications an earlier draft got wrong:

- **The "lock-too-early" rationale was not ADR 0002's single reason.** ADR 0002
  uses that phrase once, about `TemplateLoader` and `DependencyResolver` (N-3,
  N-4). N-1 rests on vendor-neutrality and the adapter-package model; N-7 is
  stated without a rationale. The accurate result is narrower and still holds:
  **the lock-too-early reasoning behind N-3 and N-4 survived contact with the
  actual consumers**, and the other non-promises stand for their own reasons.
- **The headline count.** Four of the five requested seams need no new Protocol
  and no new type. Seam 1 costs one helper function (D4); the fifth is a held
  proposal for two defaulted fields, one of which amends Promise I-2 (D5, D5a).

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
  not file count; recorded as an open objection in D8a.

- **Converting the module-level functions into classes** — rejected (D1).
  Un-idiomatic for Python and would worsen the documentation problem it aims to
  fix.

## Consequences

**Positive:**
- Every module has a one-sentence responsibility, which is the documentation
  precondition the request was actually about.
- The split ships with zero breaking changes and does not consume the 2.0 budget.
- Four of five requested integrations need no new Protocol or type; three of them
  work today with no library change at all, and the fourth costs one helper
  function. Users are not blocked waiting on adapter work.
- Naming the owned/delegated distinction converts a hidden inconsistency into a
  stated contract.

**Negative:**
- Nine modules is more navigation surface than one file; the benefit is
  conditional on the responsibilities staying single-sentence.
- If D5 ships, `handle: Any` is untyped by design and can become a dumping
  ground if the documented discipline is not enforced in review. Note also that
  `repr=False` protects the library's own repr, not a third-party observer that
  runs `asdict()` on the event and ships it to a vendor — the discipline is a
  convention at that boundary, not a mechanism.
- The library still cannot show where render time goes internally (D6 residual).
- Monkeypatch targets under `promptstrings.core` silently stop working (D9); no
  gate detects this.
- Pickles produced after the split cannot be read by any earlier version (D9).
- Delegated mode remains unavailable on `@promptstring_generator`, and
  `response_schema` remains unavailable in delegated mode at all (D2). Both are
  named, neither is fixed here.

**Neutral:**
- Work order: see the "Execution" section, which is the executor-facing summary
  of D8, D8a and D9.
- Follow-on ADRs anticipated: a Langfuse adapter contract (which is what would
  settle D5 by building the linkage before adding the field), delegation for the
  generator engine, and — only if a consumer appears — internal-phase spans.

## Grounding

Claims marked as grounded were verified during the session rather than reasoned:

- **F4** — contextvar propagation into concurrent resolver tasks was confirmed by
  executing the primitives the library actually uses — `asyncio.ensure_future`
  followed by `asyncio.wait(..., FIRST_EXCEPTION)` — against a contextvar set on
  the parent task. Propagation comes from task creation. This is what retires the
  proposed Observer change (D6). An earlier version of this finding tested
  `asyncio.gather` and `create_task`; the library uses neither for resolvers, and
  ADR 0008 records gather being rejected deliberately. The conclusion was
  unaffected, the evidence was not, and it was re-run.
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
- **F8** — `type(p).__mro__` is `(_PromptString, object)`; the object's public
  attributes are exactly five and unrelated to the marker; `isinstance(p,
  Promptstring)` holds; the engines are plain classes with no `@dataclass` or
  `__slots__`. What the marker changes is enumerated in D8; none of it is
  contract.
- **F9** — `from .core import (...)` appears in exactly one file in the
  repository (`__init__.py`); no test or example imports `promptstrings.core`.
- **F10** — appending a plain `handle: Any = None` to the frozen `PromptSource`
  dataclass was executed and shown to change `__hash__` (raises `TypeError` for an
  unhashable handle where the current type hashes fine), `__eq__`, and `__repr__`.
  This is why D5 specifies `compare=False, repr=False, hash=False` rather than a
  bare field.
- **F11** — the generator engine raises `PromptRenderError("Unsupported
  promptstring generator yield type")` for anything outside `Role`,
  `PromptMessage`, `str`, `Template`; `_response_schema_from_hints` returns `None`
  for `str`, `Template`, and `PromptSource`. Together these establish the D2
  asymmetry table.
- **F12** — the file census: 21 classes + 14 functions + 8 module-level
  assignments = 43 bindings, of which exactly two are Protocols (`Observer`,
  `Promptstring`).

## Notes

Method caveat, recorded for honesty: the expert team was capped at five, and the
Reframer slot was required by a contested diagnosis, so no independent Synthesizer
was seated — synthesis was carried by the Moderator. Same-session synthesis is
weaker than an independent pass.

The seam results (D2–D7) rest on F4–F6 and F10–F11; the decomposition (D8–D8a)
rests on F7–F9 and F12. All are tool-grounded and independently re-checkable, and
re-running the F7 analysis against the split package is acceptance gate 7.

**Review state, stated exactly.** Eight cold adversarial passes were run against
this document by readers with no access to the reasoning that produced it: six
single-angle attacks (central claim; factual accuracy; implementability; contract
preservation; internal coherence; usability as an instruction), one coverage
audit, and one regression sweep. Every P0 and P1 they raised is repaired here, and
the final regression sweep confirmed the load-bearing claims — seam count,
decomposition, cycle break, compatibility — survive independent verification.

The coverage audit nonetheless returned **INCOMPLETE**. It named sixteen
defect-classes that the attacked angles would never probe, clustered in two
regions: consequences this ADR does not model (security, performance,
portability, rollback), and the lifecycle wrapper (SemVer and deprecation policy,
decision rights, effort realism, communication plan, documentation-tooling
surface, form hygiene, decision erosion). Two of the highest-value ones were
addressed directly rather than by another pass — the trust boundary and
cross-platform behaviour of `provenance_from_file`, the second of which turned up
a real defect: `str(path)` would have produced different provenance on Windows,
defeating the helper's only purpose.

So: **the polish bar is not claimed as reached.** "Zero P0/P1" here means no cold
reader found a must-fix or should-fix *on the angles attacked*, which is a
narrower statement than "the document is sound." The residual coverage gap is
listed above rather than closed, and a reviewer who wants the strongest remaining
attack should start with security posture and the shim's deprecation lifetime,
neither of which this ADR decides.

The reviews found, and this version repairs:
a false claim that owned and delegated prompts carry identical guarantees
(`response_schema` and provenance both break the symmetry, and delegation does not
exist for generators at all); a wrong file census; a module table that partitioned
35 of 43 bindings and silently omitted the one function straddling a boundary; a
grounding that tested asyncio primitives the library does not use; a
`prompts`/`generators` boundary justified by a mechanism difference that does not
exist; a `handle` field described as inert that would have changed hashing and
equality; an amendment to a numbered Promise recorded as if it were a non-promise
revision; an acceptance gate naming a script that was never committed; a gate
requiring byte-identical definitions that the cycle fix itself would violate; and
a two-class prompt taxonomy that is actually three, because `-> Template` returns
are still rendered and strict-checked by the library.

One finding was **rejected** on checking: the claim that 1.3.0 is published on
PyPI confused the version in `pyproject.toml` with the released one — PyPI carries
1.0.0, 1.1.0, and 1.2.0, as stated.

What remains *not* grounded is boundary placement. The graph proves which splits
are **possible** (acyclic), not which are **best**. Three claims are the weakest
in this ADR and the right targets for further review:

1. `prompts` / `generators` as separate modules — its original justification was
   refuted and the replacement is weaker (D8a).
2. `factory` deserving its own 71-line module — an appeal to a future that has
   not happened.
3. `introspection` and `templates` staying apart — an appeal to release history,
   with `_compile_at_decoration` sitting on the seam.

Two decisions are **held for the owner** and the ADR is not complete without them:
whether D5 ships at all or defers to an adapter ADR (D5), and whether delegation
is extended to the generator engine before or after the split (D2).

Companion ADRs: [`0001`](0001-api-and-dx-baseline-for-1.0.md) (the 1.0 contract),
[`0002`](0002-integration-seams-for-1.0.md) (integration seams, partially revised
here), [`0006`](0006-injection-safety-and-template-source-boundaries.md)
(passthrough semantics that make delegation safe),
[`0007`](0007-integrations-and-annotated-di-syntax.md) (the `integrations/`
location this ADR formalises).
