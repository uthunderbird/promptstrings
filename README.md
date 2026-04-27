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
- **Dependency injection**: declare prompt parameters with `Annotated[T, PromptDepends(...)]`
  or `Annotated[T, AwaitPromptDepends(...)]` and resolve them from a `PromptContext` at
  render time.
- **Two render shapes**: a single string, or a list of `PromptMessage` objects
  for chat-style APIs.

## Install

```bash
pip install promptstrings
```

Requires Python 3.14+.

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

Declare resolver dependencies using `typing.Annotated`:

```python
from typing import Annotated
from promptstrings import promptstring, PromptDepends, AwaitPromptDepends, PromptContext

def current_user(ctx: PromptContext) -> str:
    return ctx.require("user_name")

async def load_profile(ctx: PromptContext) -> str:
    return await fetch_profile(ctx.require("user_id"))

@promptstring
def hello(
    user: Annotated[str, PromptDepends(current_user)],
    profile: Annotated[str, AwaitPromptDepends(load_profile)],
) -> None:
    """Hello, {user}. {profile}"""
```

Multiple `AwaitPromptDepends` resolvers run concurrently via `asyncio.gather`. Resolvers must be cancellation-safe.

## Integrations

### dishka

```
pip install promptstrings[dishka]
```

Use `DishkaContext` to pass a dishka `AsyncContainer`, and `From(Type)` as an `Annotated` marker to resolve from it:

```python
from typing import Annotated
from promptstrings import promptstring, PromptContext
from promptstrings.integrations.dishka import DishkaContext, From

@promptstring
def greet(user: Annotated[User, From(User)]) -> None:
    """Hello, {user.name}!"""

ctx = DishkaContext(container=my_container)
result = await greet.render(ctx)
```

### pydantic

```
pip install promptstrings[pydantic]
```

`PydanticPromptContext.from_model()` populates context values from a Pydantic v2 model:

```python
from pydantic import BaseModel
from promptstrings.integrations.pydantic import PydanticPromptContext

class Request(BaseModel):
    user: str
    topic: str

ctx = PydanticPromptContext.from_model(Request(user="Ada", topic="AI"))
result = await my_prompt.render(ctx)
```

Pass `dump_mode='json'` to serialize datetimes and other types to JSON-compatible values.

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

**Join semantics:** `render()` joins multiple messages with `"\n\n"` (double
newline). Within a single message, consecutive string yields are joined with
`"\n"`. Use `render_messages()` to get individual `PromptMessage` objects and
join them yourself.

## Type annotations

Use the `Promptstring` Protocol to annotate prompt objects in function
signatures — it is stable across 1.x and does not expose internal classes:

```python
from promptstrings import Promptstring, PromptContext

async def call_llm(prompt: Promptstring, ctx: PromptContext) -> str:
    messages = await prompt.render_messages(ctx)
    ...
```

## Dynamic templates (t-strings)

For prompts built at runtime — for example, from a function argument or
database-loaded string — return a Python 3.14 t-string (`t"..."`) annotated
`-> Template`:

```python
from string.templatelib import Template
from promptstrings import promptstring, PromptContext

@promptstring
def greet(name: str) -> Template:
    return t"Hello, {name}."

text = await greet.render(PromptContext({"name": "Ada"}))
```

The t-string path is injection-safe: Python evaluates all expressions before
the function returns; the framework never re-parses the resulting string.

For externally loaded template strings (database, config), use
`parse_trusted_template`:

```python
from string.templatelib import Template
from promptstrings import promptstring, parse_trusted_template, PromptContext

template_from_db = "You are an expert on {topic}."  # trusted, not user-supplied

@promptstring
def system(topic: str) -> Template:
    return parse_trusted_template(template_from_db)
```

> **Security:** only pass trusted strings to `parse_trusted_template`.
> User-controlled input containing `{param_name}` syntax will be substituted.

## Provenance

Attach provenance metadata to rendered messages by returning a `PromptSource`
with a `PromptSourceProvenance`. The `content` field of `PromptSource` is a
**literal string** — no placeholder substitution occurs. For dynamic content
with provenance, use `@promptstring_generator` and yield `PromptMessage`
objects directly:

```python
from promptstrings import promptstring_generator, Role, PromptMessage, PromptSourceProvenance

prov = PromptSourceProvenance(source_id="system-v2", version="2026-04-27")

@promptstring_generator
def system_prompt(topic: str):
    yield PromptMessage(
        role="system",
        content=f"You are an expert on {topic}.",
        source=prov,
    )
```

For a static template with provenance, use `PromptSource` with literal content:

```python
from promptstrings import promptstring, PromptSource, PromptSourceProvenance

@promptstring(strict=False)
def static_prompt() -> PromptSource:
    return PromptSource(
        content="You are a helpful assistant.",
        provenance=PromptSourceProvenance(source_id="assistant-v1"),
    )
```

## Observers

`Promptstrings` is a configuration carrier that attaches a shared `Observer`
to multiple prompt functions. Observers receive `RenderStartEvent`,
`RenderEndEvent`, and `RenderErrorEvent` objects for every render call — useful
for logging, metrics, and tracing.

```python
from promptstrings import Promptstrings, Observer, RenderStartEvent, RenderEndEvent, RenderErrorEvent

class LogObserver:
    def on_event(self, event: RenderStartEvent | RenderEndEvent | RenderErrorEvent) -> None:
        print(f"[{type(event).__name__}] {event.prompt_name}")

ps = Promptstrings(observer=LogObserver())

@ps.promptstring
def greet(name: str) -> None:
    """Hello, {name}."""

@ps.promptstring_generator
def chat(topic: str):
    yield Role("system")
    yield f"You are an expert on {topic}."
```

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
