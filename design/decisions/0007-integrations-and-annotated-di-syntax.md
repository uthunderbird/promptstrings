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

### Integration design (from /swarm sessions, 2026-04-27)

Two integrations were designed:

**`promptstrings[dishka]`** — `DishkaContext` as a drop-in subclass of `PromptContext`
paired with a `From(type_)` helper. `DishkaContext` carries a typed `container` field
and hides it in `extras` under a private key via `__post_init__`. `From(type_)` returns
an `AwaitPromptDepends` resolver that reads the container from `extras` using the same
private key. The two are inseparable: `From()` without `DishkaContext` leaks the key;
`DishkaContext` without `From()` gives no DX benefit. No pre-resolve step — dishka
resolvers run inside the standard `_resolve_dependencies` gather pass. This pattern is
symmetric across DI frameworks: `promptstrings[fastdepends]` would expose
`FastDependsContext + Inject(type_)` with an identical structure.

**`promptstrings[pydantic]`** — `PydanticPromptContext` as a drop-in subclass of
`PromptContext`. A `from_model(model, *, dump_mode='python')` classmethod populates
`values` from `model.model_dump(mode=dump_mode)`. Requires **Pydantic v2 only** —
`model_dump()` and `model_dump(mode='json')` are v2 APIs; Pydantic v1's `.dict()` is
not supported and will not be. `ValidationError` is not wrapped into `PromptRenderError`
— it is a construction-time error, not a render-time error.

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

### D2 — `DishkaContext` + `From()` integration

Each DI-framework extra exposes exactly two symbols: a typed context subclass and a
resolver factory. They are inseparable — the context hides the private key, the factory
reads it. This pattern is symmetric across all DI-framework extras.

```python
# src/promptstrings/integrations/dishka.py
from __future__ import annotations
from dataclasses import dataclass
from typing import Any, TypeVar
from dishka import AsyncContainer
from promptstrings import PromptContext, AwaitPromptDepends

T = TypeVar('T')

_CONTAINER_KEY = '_promptstrings_dishka_container'  # private, not exported


@dataclass(frozen=True)
class DishkaContext(PromptContext):
    """PromptContext carrying a dishka AsyncContainer.

    Pass this instead of PromptContext when using dishka for DI.
    Use From(SomeType) in Annotated markers to resolve from the container.
    """
    container: AsyncContainer | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, 'extras', {**self.extras, _CONTAINER_KEY: self.container})


def From(type_: type[T]) -> AwaitPromptDepends:
    """Resolve a parameter from the active dishka container.

    Usage: Annotated[SomeType, From(SomeType)]
    Requires the render context to be a DishkaContext; raises KeyError otherwise.
    """
    async def resolver(ctx: PromptContext) -> T:
        container: AsyncContainer = ctx.extras[_CONTAINER_KEY]
        return await container.get(type_)
    return AwaitPromptDepends(resolver)
```

**DX:**

```python
from typing import Annotated
from promptstrings import promptstring
from promptstrings.integrations.dishka import DishkaContext, From

@promptstring
def greet(
    name: str,
    user: Annotated[CurrentUser, From(CurrentUser)],
) -> None:
    """Hello, {name}. Your role is {user}."""

ctx = DishkaContext(values={"name": "Ada"}, container=container)
text = await greet.render(ctx)
```

**How it works:** `From(CurrentUser)` returns an `AwaitPromptDepends` resolver.
`_resolve_dependencies` picks it up via the standard Annotated path (D1, step 2) and
collects it into the `asyncio.gather` pass. No pre-resolve step, no `declared_parameters`
inspection, no `get_type_hints` call in the extra. The extra has zero knowledge of
`_resolve_dependencies` internals.

**Error behavior:** if `DishkaContext` is not used but `From()` resolvers are present,
`ctx.extras[_CONTAINER_KEY]` raises `KeyError` at render time with a clear key name.
No wrapping — the `KeyError` propagates as-is. This is intentional: using `From()`
without `DishkaContext` is a programming error, not a runtime condition.

**Symmetric pattern for other DI frameworks:**

```python
# promptstrings[fastdepends] — identical structure, different container API:
_KEY = '_promptstrings_fastdepends_container'

@dataclass(frozen=True)
class FastDependsContext(PromptContext):
    container: object = None
    def __post_init__(self) -> None:
        object.__setattr__(self, 'extras', {**self.extras, _KEY: self.container})

def Inject(type_: type[T]) -> AwaitPromptDepends:
    async def resolver(ctx: PromptContext) -> T:
        return await ctx.extras[_KEY].resolve(type_)
    return AwaitPromptDepends(resolver)
```

Each DI-framework extra: one file, two exports (`XxxContext` and a resolver factory),
one private key constant. Core is unaware of any of them.

### D3 — `PydanticPromptContext` subclass with `from_model()` classmethod

**Pydantic v2 only.** `PydanticPromptContext` uses `model.model_dump()` and
`model.model_dump(mode='json')` — both are Pydantic v2 APIs introduced in v2.0.
Pydantic v1's `.dict()` method is explicitly not supported. The `pyproject.toml` pin
(`pydantic>=2.0`) enforces this at install time. No compatibility shim for v1 will
be added.

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

`ValidationError` from Pydantic v2 is not caught or wrapped — it propagates as-is.
A `TypeError` is raised if the argument is not a `pydantic.BaseModel` instance.

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
pydantic = ["pydantic>=2.0,<3.0"]
```

The upper bound `<3.0` on pydantic is intentional — Pydantic v3 may change
`model_dump()` semantics. When v3 ships, a conscious decision and test pass is
required before widening the pin.

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
| T8 | `From(SomeType)` resolver called with a plain `PromptContext` (no `DishkaContext`) raises `KeyError` with `_CONTAINER_KEY` in the message | Pins the error behavior for missing container; documents that `From()` without `DishkaContext` is a programming error | D2 |
| T9 | `DishkaContext.__post_init__` merges container into extras; existing extras entries are preserved | Verifies the `{**self.extras, _KEY: container}` merge is non-destructive | D2 |
| T10 | `PydanticPromptContext.from_model(not_a_BaseModel)` raises `TypeError` | D3 error contract | D3 |
| T11 | `PydanticPromptContext.from_model(model, dump_mode='json')` serializes `datetime`/`UUID` to strings | D3 known caveat; documents expected serialization behavior | D3 |
| T12 | `from pydantic.v1 import BaseModel; PydanticPromptContext.from_model(v1_model)` raises `TypeError` or `AttributeError` | Explicitly guards against Pydantic v1 models being passed to a v2-only API | D3 |

T1–T7 must pass before D2 is written. T12 ensures that Pydantic v1 compat shims
(e.g. `pydantic.v1` which ships inside Pydantic v2) do not silently work — v1 models
lack `model_dump()` and the failure must be explicit, not silent.

## Alternatives Considered

- **`DishkaPromptContext.resolve(fn, container)` pre-resolve classmethod.** Rejected
  in favour of `DishkaContext + From()`. Pre-resolve requires `get_type_hints` on
  `fn` from inside the extra-package boundary (where `fn._hints` is not accessible),
  walking `declared_parameters` and separately calling `container.get()` for each
  parameter. This duplicates logic that `_resolve_dependencies` already does, and it
  cannot reuse the hints cached at decoration time. The `From()` pattern delegates
  resolution entirely to the existing gather pass with no duplication.

- **Thin `From()` wrapper without a typed context class.** Rejected: without
  `DishkaContext`, the private `_CONTAINER_KEY` string must appear in user code
  (`PromptContext(extras={'_promptstrings_dishka_container': container})`), breaking
  encapsulation and making the key a de-facto public API. Typed context + private key
  is the correct split.

- **Protocol for `PromptContext` in core.** Rejected: frozen dataclass subclass
  satisfies mypy via LSP without adding a new public symbol to core. Protocol would
  grow over time and create maintenance burden.

- **`dishka` hook in `_resolve_dependencies`.** Rejected: couples core to an
  optional dependency. `From()` resolvers run inside the standard `AwaitPromptDepends`
  gather path — core is unaware of dishka.

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
- `DishkaContext + From()` enables full dishka DI with zero pre-resolve step and no
  `PromptDepends` in function signatures. The pattern is symmetric — any DI framework
  gets a one-file extra with two exports.
- `PydanticPromptContext` gives validated, model-driven prompt construction with one
  import. Pydantic v2-only pin is explicit and enforced at install time.
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
- `DishkaContext.container` field is typed `AsyncContainer | None`; passing a sync
  `Container` raises `KeyError` or `AttributeError` inside `From()` resolvers at
  render time — no compile-time guard.
- Pydantic v1 models passed to `PydanticPromptContext.from_model()` raise
  `AttributeError` (no `model_dump` method) — not a custom error. T12 pins this.

## Notes

- Integration design sessions: 2026-04-27, conducted via `/swarm` (two sessions —
  initial design and DI architecture revision).
- `Annotated` syntax requires Python 3.11+ for `get_type_hints(include_extras=True)`
  — already satisfied by the `>=3.14` requirement.
- The `DishkaContext + From()` pattern was chosen over `DishkaContext.resolve(fn,
  container)` after the second design session concluded that pre-resolve duplicates
  `_resolve_dependencies` logic and cannot reuse `fn._hints` across the extra boundary.
- Pydantic v2 pin rationale: `model_dump()` / `model_dump(mode='json')` are v2-only
  APIs. Pydantic v1 shipped inside Pydantic v2 as `pydantic.v1`; T12 guards against
  v1 compat models being silently accepted.
- Future: `integrations/opentelemetry.py` could expose an `OtelContext` subclass
  carrying a tracer span in `extras` and an `Observer` that emits spans — identical
  pattern to `DishkaContext`.
