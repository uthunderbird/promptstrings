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
`DishkaPromptContext.resolve(fn, container)`, which reads `declared_parameters`
(public API) and calls `container.get(annotation)` for each parameter not already
in `values`. Dishka replaces `PromptDepends` entirely — the two are not used
together.

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
5. `parameter.default` is not empty — use default value
6. Raise `PromptRenderError`

The default-value path (step 3) continues to work but is not mentioned in
documentation, README, or examples. No deprecation warning is emitted — the library
has no external users at this point.

**Public documentation** shows only the `Annotated` form. The default-value form
is preserved for internal continuity.

### D2 — `DishkaPromptContext` subclass with `resolve()` classmethod

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

`resolve()` iterates `fn.declared_parameters`, skips parameters already in `values`
and parameters without annotations, and calls `await container.get(annotation)` for
the rest.

**dishka + Annotated:** when a parameter is `Annotated[User, PromptDepends(...)]`,
`resolve()` skips it (it will be resolved by `_resolve_dependencies` via the
`Annotated` path). When a parameter is `Annotated[User, Inject()]` (dishka's own
marker), `resolve()` honours the dishka marker and calls `container.get(User)`.
Plain type annotations with no marker → resolved by `container.get(annotation)`.

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
- `_resolve_dependencies` becomes more complex: `get_type_hints` call + Annotated
  metadata extraction on every render. Performance impact is negligible for prompt
  use cases but is a real change.
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
