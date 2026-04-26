# promptstrings

Strict prompt-template composition with provenance tracking and FastAPI-style
dependency injection. Pure standard library, zero runtime dependencies.

## Why

Prompt construction code tends to drift into ad-hoc string formatting that
silently swallows missing variables, hides where each fragment came from, and
makes it hard to know which parameters were actually consumed. `promptstrings`
gives you:

- **Strict rendering**: missing placeholders raise; unused parameters raise too
  (opt-in via `strict=True`, default for `@promptstring`).
- **Provenance**: each rendered message carries a `PromptSourceProvenance`
  describing where its template came from (id, version, hash, provider).
- **Dependency injection**: declare prompt parameters with `PromptDepends(...)`
  or `AwaitPromptDepends(...)` and resolve them from a `PromptContext` at
  render time.
- **Two render shapes**: a single string, or a list of `PromptMessage` objects
  for chat-style APIs.

## Install

```bash
pip install promptstrings
```

Requires Python 3.13+.

## Quickstart

```python
import asyncio
from promptstrings import promptstring, PromptContext

@promptstring
def greet(name: str) -> None:
    """Hello, {name}. Welcome to promptstrings."""

async def main() -> None:
    text = await greet.render(PromptContext(values={"name": "Ada"}))
    print(text)  # → "Hello, Ada. Welcome to promptstrings."

asyncio.run(main())
```

The docstring is the template. Placeholders use the minimal `{identifier}`
grammar — no format specs, no conversions, no surprises.

## Strictness

By default `@promptstring` is strict: every resolved parameter must appear in
the template, and every placeholder must be resolved. This prevents the
"silently dropped variable" class of prompt bugs.

```python
@promptstring
def example(name: str, unused: int = 42) -> None:
    """Hello {name}."""

await example.render(PromptContext(values={"name": "Ada", "unused": 1}))
# raises PromptStrictnessError: 'unused' was resolved but not consumed
```

Pass `strict=False` to opt out.

## Dependency injection

Use `PromptDepends` for sync resolvers and `AwaitPromptDepends` for async ones.

```python
from promptstrings import promptstring, PromptDepends, PromptContext

def current_user(ctx: PromptContext) -> str:
    return ctx.require("user_name")

@promptstring
def hello(user: str = PromptDepends(current_user)) -> None:
    """Hello, {user}."""
```

At most one `AwaitPromptDepends` per render is permitted.

## Generator form

For multi-message prompts (system + user, or alternating turns), use
`@promptstring_generator`. Yield `Role(...)` to switch role, yield strings to
append, yield `PromptMessage(...)` to emit a fully-formed message.

```python
from promptstrings import promptstring_generator, Role

@promptstring_generator
def conversation(topic: str):
    yield Role("system")
    yield f"You are an expert on {topic}."
    yield Role("user")
    yield f"Tell me about {topic}."
```

## Provenance

Return a `PromptSource(content=..., provenance=PromptSourceProvenance(...))`
from your function instead of relying on the docstring, and the `provenance`
field will be attached to every `PromptMessage` produced.

## Stability

Pre-1.0. The API is stable in practice (used internally by femtobot) but minor
breaks may occur before 1.0.

## Design and architecture

The functional vision and 1.0 contract are documented under
[`design/`](design/). Start here:

- **[`design/VISION.md`](design/VISION.md)** — single source of truth for
  *why* the library exists: the problems it solves and how its developer
  experience answers them. Updated in place, versioned via
  `vision_version`.
- **[`design/decisions/0001-api-and-dx-baseline-for-1.0.md`](design/decisions/0001-api-and-dx-baseline-for-1.0.md)**
  — the locked SemVer contract (13 promises, 12 non-promises,
  lifecycle map, DX rubric R1–R10). **The canonical contract.**
- **[`design/decisions/0002-integration-seams-for-1.0.md`](design/decisions/0002-integration-seams-for-1.0.md)**
  — extension surface for 1.0: `Promptstrings` configuration carrier,
  `Observer` Protocol, `PromptContext.extras`, and per-vendor adapter
  model. **The canonical contract for integration.**
- *(historical proposals preserved for the red-team trace and
  rationale: [`design/proposals/api-1.0-baseline.md`](design/proposals/api-1.0-baseline.md),
  [`design/proposals/api-1.0-integrations.md`](design/proposals/api-1.0-integrations.md))*
- **[`design/glossary.md`](design/glossary.md)** — canonical
  vocabulary used across all design docs.
- **[`design/README.md`](design/README.md)** — directory map and
  conventions for adding decisions, proposals, and DX deep-dives.

## License

MIT.
