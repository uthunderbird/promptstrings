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

See runnable examples in [`examples/`](examples/) — one file per concept,
runnable with `python examples/01_basic_render.py`.

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

## Three kinds of prompt, three sets of guarantees

Which guarantees you get depends on where the prompt text comes from. The library
recognises three shapes, selected by what the decorated function returns. They
are not interchangeable, and the differences are structural rather than
incidental.

| | **Owned-static**<br>docstring | **Owned-dynamic**<br>`-> Template` | **Delegated**<br>`-> PromptSource` |
|---|---|---|---|
| Who renders it | the library | the library | **you** |
| `placeholders` known at decoration | **yes** | no | no |
| Strict mode (missing / unused) | yes, before render | **yes**, at render | **no** |
| `response_schema` | **yes** | no | no |
| Provenance | no | no | **yes** |
| Works with `@promptstring_generator` | yes | yes | **no** |

Read the table as a set of trades:

- **Owned-static is the strongest** and should be the default. Placeholders are
  known before any model call, so a missing or unused parameter is caught at the
  cheapest possible moment.
- **Owned-dynamic keeps strict mode.** If a template arrives from a database or a
  prompt-management system, `parse_trusted_template` still gives you
  missing-parameter and unused-parameter checking — you only lose
  *decoration-time* introspection, because the text does not exist yet.
- **Delegated gives rendering away entirely.** Return a `PromptSource` and any
  engine works — Jinja2, Mustache, plain concatenation — with no library support
  and no version coupling. The library never parses what you return, so strict
  mode over placeholders is not merely unimplemented here, it is impossible. In
  exchange this is the only path that carries provenance.

Two consequences worth knowing before you pick:

**You cannot have both strictness and provenance on one prompt.** The owned paths
check placeholders and set no provenance; the delegated path carries provenance
and checks nothing. Choose per prompt.

**Structured output is owned-static only.** `response_schema` is derived from the
return annotation, and `-> Template` / `-> PromptSource` are exactly the
annotations that select the other two shapes. A Jinja2-rendered prompt cannot
also declare a typed response schema on the same function.

A fourth shape does not exist: a function with no docstring annotated `-> str`
raises `PromptCompileError` at decoration rather than rendering anything.

See [`examples/13_prompt_classes.py`](examples/13_prompt_classes.py) for all
three side by side.

## Dependency injection

Use `PromptDepends` when a parameter needs to be resolved from application
state (authenticated user, loaded config, traced span) rather than passed
directly by the caller.

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

Multiple `AwaitPromptDepends` resolvers run concurrently. If one raises, the rest are cancelled before the exception propagates — resolvers can use `try/finally` for cleanup.

## Structured output

When a prompt function is annotated with a user-defined return type, the
`response_schema` property exposes that type — no need to repeat it at the
call site. Works with any structured-output framework (instructor, litellm,
OpenAI structured outputs).

```python
from pydantic import BaseModel
from promptstrings import promptstring

class Invoice(BaseModel):
    vendor: str
    amount: float

@promptstring
def extract(text: str) -> Invoice:
    """Extract invoice data from: {text}"""

messages = await extract.render_messages(ctx)
# Single source of truth — Invoice is not repeated here:
result = client.chat(response_model=extract.response_schema, messages=...)
```

`response_schema` is `None` for internal return types (`None`, `...`, `str`,
`Template`, `PromptSource`) and when no return annotation is present.

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
def greet(username: Annotated[str, From(User)]) -> None:
    """Hello, {username}!"""

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

When the template lives in a file, `provenance_from_file` derives the identity
and a content hash for you, so the boilerplate above does not have to be repeated
per prompt:

```python
from promptstrings import promptstring, PromptSource, provenance_from_file

HERE = pathlib.Path(__file__).parent

@promptstring(strict=False)
def system_prompt(topic: str) -> PromptSource:
    template = HERE / "prompts" / "system.jinja2"
    return PromptSource(
        content=render_however_you_like(template, topic=topic),
        provenance=provenance_from_file(
            template,
            source_id="prompts/system.jinja2",  # keep the identity repo-relative
            version="2026-07-27",
        ),
    )
```

`hash` is `sha256` over the file's raw bytes, with no newline normalisation —
normalising would hide a real difference in what was sent to the model. `version`
is never assigned by the library. Pass `source_id` explicitly whenever the path
you read from is absolute, since an absolute path is machine-specific and would
make the same template compare unequal across checkouts.

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
    def on_render_start(self, event: RenderStartEvent) -> None:
        print(f"[start] {event.prompt_name}")

    def on_render_end(self, event: RenderEndEvent) -> None:
        print(f"[end] {event.prompt_name} ({event.elapsed_ns // 1_000_000}ms)")

    def on_render_error(self, event: RenderErrorEvent) -> None:
        print(f"[error] {event.prompt_name}: {event.error}")

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

Stable. The library follows SemVer from 1.0 — breaking changes require a major
version bump. The full API contract is documented in
[`design/decisions/0001`](design/decisions/0001-api-and-dx-baseline-for-1.0.md).

## Design

The API contract (stability guarantees, 13 promises, DX rubric) is documented
in [`design/decisions/0001`](design/decisions/0001-api-and-dx-baseline-for-1.0.md).
Full design documentation lives in [`design/`](design/).

## License

MIT.

## Who builds this

Built by Daniyar Supiyev. I consult on AI agent systems — building them, and
fixing the ones that misbehave in production — at
[Forbidden Fundamentals](https://forbiddenfundamentals.com).
