# 0007 — Integrations and Annotated DI Syntax

- **Status:** Accepted
- **Date:** 2026-04-27
- **Deciders:** Daniyar Supiyev
- **Supersedes:** ADR 0001 (partially — PromptDepends default-value syntax becomes silent deprecated)
- **Superseded by:** —

## Context

After 1.0.0 release, two integration packages were designed (`promptstrings[dishka]`,
`promptstrings[pydantic]`) and a review of the dependency injection syntax identified
that the existing default-value pattern for `PromptDepends` has known ergonomic
drawbacks compared to the `typing.Annotated` pattern adopted by FastAPI (0.95+),
dishka, and Pydantic v2.

### Problems with the default-value pattern

```python
# Current (default-value pattern)
def greet(user: User = PromptDepends(get_user)) -> None:
    """Hello, {user}."""
```

1. **Occupies the default slot** — the parameter appears optional to static analysers
   even though it is always resolved at render time.
2. **Type checkers see the wrong type** — `user` infers as `User | PromptDepends`
   without explicit annotation, causing mypy noise.
3. **Inconsistent with the ecosystem** — FastAPI, dishka, and Pydantic v2 all moved
   to `Annotated` as their primary DI marker syntax.

### `Annotated` pattern

```python
from typing import Annotated
from promptstrings import promptstring, PromptDepends

def get_user(ctx: PromptContext) -> User: ...

@promptstring
def greet(user: Annotated[User, PromptDepends(get_user)]) -> None:
    """Hello, {user}."""
```

`Annotated` carries the resolver as metadata on the type, leaving the default slot
free and giving type checkers an unambiguous `user: User`.

### Integration design (from /swarm session, 2026-04-27)

Two integrations were designed:

**`promptstrings[dishka]`** — `DishkaPromptContext` as a drop-in subclass of
`PromptContext`. Parameters are pre-resolved from a dishka `AsyncContainer` via
`DishkaPromptContext.resolve(fn, container)`, which uses `declared_parameters` for
parameter names and `get_type_hints(fn, include_extras=True)` for annotation access,
calling `container.get(bare_type)` for each parameter not already in `values` (where
`bare_type` is the first argument to `Annotated[T, ...]` for `Annotated` types, or the
annotation itself for plain non-`Annotated` types). Dishka
resolves plain type annotations and dishka `Inject()` markers; parameters carrying
`PromptDepends` or `AwaitPromptDepends` in `Annotated` metadata are skipped by
`resolve()` and handled by `_resolve_dependencies` as usual.

**`promptstrings[pydantic]`** — `PydanticPromptContext` as a drop-in subclass of
`PromptContext`. A `from_model(model, *, dump_mode='python')` classmethod populates
`values` from `model.model_dump(mode=dump_mode)`. `ValidationError` is not wrapped
into `PromptRenderError` — it is a construction-time error, not a render-time error.

## Decision

### D1 — `Annotated` as primary DI syntax; default-value as silent deprecated

`_resolve_dependencies` is updated to check `get_type_hints(fn, include_extras=True)`
for `Annotated` metadata before checking `parameter.default`. Resolution priority:

1. `Annotated[T, PromptDepends(resolver)]` — sync resolver
2. `Annotated[T, AwaitPromptDepends(resolver)]` — async resolver
3. `parameter.default` is `PromptDepends` or `AwaitPromptDepends` — resolved as
   before (silent deprecated path, not documented)
4. `name in context.values` — direct value lookup
5. `parameter.default` is `inspect.Parameter.empty` → raise `PromptRenderError`; otherwise use `parameter.default`

The default-value path (step 3) continues to work but is not mentioned in
documentation, README, or examples. No deprecation warning is emitted — the library
has no external users at this point, so silent deprecated is sufficient. A warning
can be added in a future release when the pattern is fully removed.

**Step ordering invariant:** Steps 4 and 5 must remain in this order after any loop
restructure. Step 4 (`context.values`) before step 5 (`parameter.default`) means a
caller-supplied value can shadow a parameter's Python default — this is existing
behavior and correct. When restructuring `_resolve_dependencies` to accommodate steps
1–2, care must be taken not to accidentally swap steps 4 and 5. No existing test pins this ordering,
and no proposed test in this ADR covers value-lookup semantics. If the loop is
restructured, add an explicit assertion that `context.values` lookup takes priority
over `parameter.default` for a parameter that has both.

**`_dep_params` recomputation:** `_PromptString.__init__` and
`_PromptStringGenerator.__init__` compute `_dep_params` by checking
`isinstance(param.default, (PromptDepends, AwaitPromptDepends))`. After the Annotated
migration, parameters declared as `Annotated[T, PromptDepends(f)]` have
`param.default = inspect.Parameter.empty`, so the existing check misses them. Both
`__init__` implementations must be updated to additionally detect `PromptDepends` and
`AwaitPromptDepends` in `Annotated` metadata via
`get_type_hints(fn, include_extras=True)`. A parameter belongs to `_dep_params` if it
carries a `PromptDepends` or `AwaitPromptDepends` instance in either its default slot
or its `Annotated` metadata.

**Atomicity requirement:** The `_dep_params` update and the `_resolve_dependencies`
update described in this section are a single atomic unit — they must be implemented
and committed together. If `_resolve_dependencies` is updated to resolve `Annotated`
parameters but `_dep_params` is not updated, strict-mode promptstrings will raise
`PromptUnusedParameterError` for every `Annotated[T, PromptDepends(f)]` parameter
that is not also a template placeholder. This failure is silent — no compile-time
error, no test failure against the existing suite. Do not ship one without the other.

**`get_type_hints` error contract:** The `get_type_hints(fn, include_extras=True)` call
happens at decoration time (in `__init__`). If it raises `NameError` (forward
reference not resolvable in the function's module globals) or `AttributeError`, the
exception is re-raised immediately — decoration fails fast rather than producing a
silently broken promptstring. Because the hints dict is cached after successful
decoration, no `NameError` can occur at render time.

**`asyncio.gather` preservation (ADR 0001 Promise 9):** `_resolve_dependencies` uses a
two-pass approach to preserve concurrent resolution of async deps for both syntax paths:

1. *Hints pass* — walk all parameters using the `hints` dict passed in by the caller
   (after D1 is implemented: computed at decoration time and stored as `self._hints`,
   then passed explicitly to `_resolve_dependencies`), collecting sync resolvers
   for immediate execution and async resolvers into a deferred list.
2. *Gather pass* — after all sync resolvers have run, pass the deferred list to
   `asyncio.gather(*(resolver() for resolver in async_resolvers))`.

Annotated `AwaitPromptDepends` parameters (step 2 in the priority list) follow the same
gather path as the existing default-slot `AwaitPromptDepends` parameters (step 3). The
gather optimization is not broken by the Annotated syntax path.

**Public documentation** shows only the `Annotated` form. The default-value form
is preserved for internal continuity.

### D2 — `DishkaPromptContext` subclass with `resolve()` classmethod

**Implementation ordering constraint:** D2 may not be implemented until D1 is complete
and T1–T7 pass. `DishkaPromptContext.resolve()` skips parameters carrying `PromptDepends`
or `AwaitPromptDepends` in `Annotated` metadata, delegating them to `_resolve_dependencies`
via the Annotated path. This skip logic depends on D1's Annotated resolution being correct.
If D1 is partially broken, D2 will either double-resolve parameters or miss them entirely,
with no warning at definition time.

`DishkaPromptContext` is a `frozen=True` dataclass subclass of `PromptContext`:

```python
@dataclass(frozen=True)
class DishkaPromptContext(PromptContext):
    container: AsyncContainer | Container | None = None

    @classmethod
    async def resolve(
        cls,
        fn: Promptstring,
        container: AsyncContainer,
        *,
        values: dict[str, Any] | None = None,
        extras: dict[str, Any] | None = None,
    ) -> DishkaPromptContext:
        ...
```

`resolve()` uses `fn.declared_parameters` (where `fn` is a `Promptstring`-Protocol
object — the decorated wrapper, not the raw callable) for parameter names and presence only.
It calls `get_type_hints(fn, include_extras=True)` independently to access annotations
and `Annotated` metadata — `inspect.Parameter.annotation` does not surface `Annotated`
extras under `from __future__ import annotations` (PEP 563 postponed evaluation, as
used in `core.py`) and must not be used for this purpose. `resolve()` cannot reuse `fn._hints`
because `_hints` is a private implementation attribute of `_PromptString` and is not
exposed on the `Promptstring` Protocol; `resolve()` only has access to the Protocol's
public surface (`declared_parameters`, `render`, etc.). For each parameter not already in
`values`, `resolve()` reads the hint, skips it if it carries a `PromptDepends` or
`AwaitPromptDepends` marker (those are handled by `_resolve_dependencies`), honours
dishka's own `Inject()` marker if present, and otherwise calls
`await container.get(bare_type)` for plain type annotations.

**`Container` vs `AsyncContainer` error contract:** `DishkaPromptContext.container` is
typed `AsyncContainer | Container | None` to allow the field to exist on the dataclass,
but `resolve()` accepts only `AsyncContainer`. If a caller constructs
`DishkaPromptContext(container=Container(...))` and calls `resolve()`, the mismatch
surfaces at runtime when `await container.get(...)` is reached — the sync `Container`
does not support `await`, and the error propagates as `TypeError` or `AttributeError`
from the dishka internals. No additional wrapping is performed in this release. A
future version may add an explicit guard with a descriptive `PromptRenderError`. Until
then, callers must pass an `AsyncContainer` to `resolve()`.

**dishka + Annotated:** when a parameter is `Annotated[User, PromptDepends(...)]`,
`resolve()` skips it (it will be resolved by `_resolve_dependencies` via the
`Annotated` path). When a parameter is `Annotated[User, Inject()]` (dishka's own
marker), `resolve()` honours the dishka marker and calls `container.get(User)`.
Plain type annotations with no marker → resolved by `container.get(annotation)`.

**`resolve()` construction pattern:** `resolve()` is purely functional. It never
mutates the incoming `values` dict. It constructs and returns a new
`DishkaPromptContext` as:

```python
return cls(
    values={**(values or {}), **resolved},
    extras=extras,
    container=container,
)
```

The `values` parameter is a seed — entries already present are preserved unchanged,
and resolved entries are merged on top. Callers that pass no `values` get a fresh
instance populated solely by container resolution.

This makes dishka the complete DI layer: container registration replaces all
`PromptDepends` declarations. `DishkaPromptContext.resolve()` is the single
call-site.

**DX:**

```python
from promptstrings import promptstring
from promptstrings.integrations.dishka import DishkaPromptContext

@promptstring
def greet(name: str, user: CurrentUser) -> None:
    """Hello, {name}. Your role is {user}."""

ctx = await DishkaPromptContext.resolve(greet, container)
text = await greet.render(ctx)
```

### D3 — `PydanticPromptContext` subclass with `from_model()` classmethod

`PydanticPromptContext` is a `frozen=True` dataclass subclass of `PromptContext`:

```python
@dataclass(frozen=True)
class PydanticPromptContext(PromptContext):
    @classmethod
    def from_model(
        cls,
        model: BaseModel,
        *,
        dump_mode: str = "python",
        extras: dict[str, Any] | None = None,
    ) -> PydanticPromptContext:
        ...
```

`dump_mode='python'` is the default. Callers use `dump_mode='json'` when
JSON-serializable representations of `datetime`, `UUID`, or `Enum` fields are needed
in the rendered prompt.

`ValidationError` from Pydantic is not caught or wrapped — it propagates as-is.
A `TypeError` is raised if the argument is not a `BaseModel` instance.

**DX:**

```python
from pydantic import BaseModel
from promptstrings import promptstring
from promptstrings.integrations.pydantic import PydanticPromptContext

class GreetInput(BaseModel):
    name: str
    language: str = "en"

@promptstring
def greet(name: str, language: str) -> None:
    """Hello, {name}. Language: {language}."""

ctx = PydanticPromptContext.from_model(GreetInput(name="Ada"))
text = await greet.render(ctx)
```

### D4 — Code lives in `src/promptstrings/integrations/`

```
src/promptstrings/
    __init__.py
    core.py
    integrations/
        __init__.py      # empty
        dishka.py
        pydantic.py
```

Optional extras in `pyproject.toml`:

```toml
[project.optional-dependencies]
dishka = ["dishka>=1.0"]
pydantic = ["pydantic>=2.0"]
```

The integrations are not imported by `promptstrings.__init__` — they must be
imported explicitly from `promptstrings.integrations.dishka` /
`promptstrings.integrations.pydantic`. This keeps the zero-dependency guarantee
intact for the base package.

### D5 — README and documentation update

The README is updated to:

1. **DI syntax section:** show only `Annotated` form; remove default-value examples.
2. **New "Integrations" section:** document `[dishka]` and `[pydantic]` with
   install instructions and minimal DX examples.
3. **`PromptDepends` / `AwaitPromptDepends`:** documented only in `Annotated` form.

## Test Requirements

D1 is not complete until T1–T7 pass. D2 and D3 are not complete until T8–T10 pass.
The existing test suite contains zero `Annotated` test cases; all new behavior paths
introduced by this ADR are uncovered without these additions.

| # | Test case | What regression it prevents | Mandatory for |
|---|-----------|---------------------------|---------------|
| T1 | `Annotated[T, PromptDepends(f)]` resolves correctly | Basic D1 path | D1 |
| T2 | `Annotated[T, AwaitPromptDepends(f)]` is collected into the gather pass | D1 async path; gather optimization not broken | D1 |
| T3 | `Annotated[T, PromptDepends(f)]` parameter is in `_dep_params`; no spurious `PromptUnusedParameterError` in strict mode (the parameter must not appear as a template placeholder, to specifically exercise the `_dep_params` exemption path rather than the placeholder-membership path) | C2 regression — atomicity of `_dep_params` + `_resolve_dependencies` update | D1 |
| T4 | Default-value `PromptDepends` still works after D1 | Silent deprecated path preserved | D1 |
| T5 | Parameter with both `Annotated` metadata and default-value `PromptDepends` resolves via `Annotated` (priority step 1 before step 3) | Priority list ordering | D1 |
| T6 | `get_type_hints` raises `NameError` at decoration → decoration raises immediately | D1 fail-fast error contract | D1 |
| T7 | `get_type_hints` raises `AttributeError` at decoration → decoration raises immediately | D1 fail-fast error contract | D1 |
| T8 | `DishkaPromptContext(container=Container(...)).resolve(...)` propagates `TypeError` or `AttributeError` (no wrapping) | Pins the `Container` vs `AsyncContainer` error surface; detects if dishka changes exception type | D2 |
| T9 | `PydanticPromptContext.from_model(not_a_BaseModel)` raises `TypeError` | D3 error contract | D3 |
| T10 | `PydanticPromptContext.from_model(model, dump_mode='json')` serializes `datetime`/`UUID` to strings | D3 known caveat; documents expected serialization behavior | D3 |

T1–T7 must pass before D2 is written (see implementation ordering constraint in D2).
T8 pins the current error behavior so that a future dishka version change surfaces
as a test failure rather than a silent contract break.

## Alternatives Considered

- **`dishka()` wrapper function returning `AwaitPromptDepends`.** Rejected: this
  reinvents `PromptDepends` with a different name and does not leverage dishka's
  container registration. The pre-resolve approach gives full dishka DI semantics.

- **Protocol for `PromptContext` in core.** Rejected: frozen dataclass subclass
  satisfies mypy via LSP without adding a new public symbol to core. Protocol would
  grow over time and create maintenance burden.

- **`dishka` hook in `_resolve_dependencies`.** Rejected: couples core to an
  optional dependency. Pre-resolve in `DishkaPromptContext.resolve()` keeps core
  unmodified.

- **`ValidationError` wrapped into `PromptRenderError`.** Rejected: validation
  happens at model construction time, not at render time. Wrapping would hide the
  origin and make error handling harder.

- **Separate packages (`promptstrings-dishka`, `promptstrings-pydantic`).** Rejected:
  optional extras in one package are simpler to maintain and version together.
  Separate packages would require coordinated releases and version matrix testing.

- **Emit deprecation warning for default-value `PromptDepends`.** Rejected: no
  external users exist at this point. Silent deprecated is sufficient; a warning
  can be added in a future release when the pattern is fully removed.

## Consequences

**Positive:**
- `Annotated` syntax is type-safe: `user: Annotated[User, PromptDepends(f)]` gives
  mypy an unambiguous `User` type at call sites.
- Consistent with FastAPI, dishka, Pydantic v2 — lower learning curve for users
  familiar with those frameworks.
- `DishkaPromptContext` enables full dishka DI without any `PromptDepends` in
  function signatures.
- `PydanticPromptContext` gives validated, model-driven prompt construction with
  one import.
- Core is unchanged — zero-dependency guarantee holds.
- Integration structure (`integrations/`) is a clear extension point for future
  integrations (e.g. `integrations/opentelemetry.py`).

**Negative:**
- `_resolve_dependencies` becomes more complex: Annotated metadata extraction via a
  hints dict (the *hints pass* in the two-pass structure described in the
  `asyncio.gather preservation` block above). To avoid per-render string evaluation for
  PEP 563 annotations, the resolved hints dict (`get_type_hints(fn, include_extras=True)`)
  is computed at decoration time. After D1 is implemented: `_PromptString.__init__` and
  `_PromptStringGenerator.__init__` call `get_type_hints` and store the result as
  `self._hints`. `_resolve_dependencies` remains a module-level function (not a
  method); it receives the hints dict as an explicit `hints` parameter. Call sites in
  `_render_messages_impl` on both classes pass `self._hints` to
  `_resolve_dependencies` — no `get_type_hints` call occurs at render time. Performance
  impact of the decoration-time call is negligible; the render-time path has no added
  cost beyond a dict lookup. The `NameError` guarantee holds because `get_type_hints`
  is called in `__init__`, not at render time — a forward-reference failure surfaces at
  decoration, not at the first render.
- `declared_parameters` (public API) is used by `DishkaPromptContext.resolve()` —
  this tightens the stability contract on that attribute.
- `dump_mode='python'` with `datetime`/`UUID` fields: string representation in
  templates may surprise users. Documented as a known caveat.

**Neutral:**
- Default-value `PromptDepends` continues to work — no migration required for
  internal users.
- `integrations/__init__.py` is empty — no re-exports. Each integration is an
  explicit import.
- `DishkaPromptContext.container` field is typed as `AsyncContainer | Container | None`
  for flexibility; `resolve()` currently only accepts `AsyncContainer`.

## Notes

- Integration design session: 2026-04-27, conducted via `/swarm`.
- `Annotated` syntax requires Python 3.11+ for `get_type_hints(include_extras=True)`
  — already satisfied by the `>=3.14` requirement.
- dishka's `Inject()` marker in `Annotated` metadata: `DishkaPromptContext.resolve()`
  should check for it explicitly rather than treating all `Annotated` metadata as
  dishka markers.
- Future: `integrations/opentelemetry.py` could add a `PromptContext` subclass that
  carries a tracer span in `extras` and an `Observer` that emits spans.
