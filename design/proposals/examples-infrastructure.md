---
title: Examples infrastructure
status: proposed
created: 2026-04-27
updated: 2026-04-27
---

# Examples infrastructure

Design document for where examples live, how they are structured, what
environment they require, and how they are verified.

## Problem

The library has no runnable examples. Users who want to understand
real-world usage have only the README snippets and the test suite, neither
of which is written as pedagogical material. Without a verified example
corpus, usage patterns rot quietly and integration scenarios go untested.

## Constraints

- Examples must not enter the wheel (`src/promptstrings` only in
  `packages`).
- Examples must not require a live LLM API key to run in CI.
- Examples must not inflate the mandatory install footprint.
- Each example must be runnable with a single command and exit 0.

## Decision summary

See ADR 0010 for the authoritative record. This document is the exploratory
companion.

---

## Directory structure

```
examples/
  utils/
    fake_llm.py        # FakeLLMClient — deterministic OpenAI-compatible mock
  01_basic_render.py
  02_prompt_source.py
  03_dependency_injection.py
  04_annotated_di.py
  05_generator.py
  06_structured_output.py
  07_pydantic_context.py
  08_dishka_integration.py
  09_observer.py
  10_response_schema.py
```

Files are numbered to communicate recommended reading order, not to imply
execution dependency. Each file is self-contained.

## Example catalogue

| File | Primary concept demonstrated |
|------|------------------------------|
| `01_basic_render.py` | `@promptstring`, `PromptContext`, `render()` / `render_messages()` |
| `02_prompt_source.py` | `-> PromptSource` dynamic source, `PromptSourceProvenance` |
| `03_dependency_injection.py` | `PromptDepends` (default-value form, deprecated path) |
| `04_annotated_di.py` | `Annotated[T, PromptDepends(…)]` — primary DI syntax |
| `05_generator.py` | `@promptstring_generator`, multi-turn yield |
| `06_structured_output.py` | `-> MyModel` + `response_schema` + instructor-style call via `FakeLLMClient` |
| `07_pydantic_context.py` | `PydanticPromptContext.from_model()` as context source |
| `08_dishka_integration.py` | `DishkaContext` + `From()` for container-resolved deps |
| `09_observer.py` | `Promptstrings` config + `Observer` for render-event tracing |
| `10_response_schema.py` | `response_schema` as single source of truth across multiple prompt functions |

## FakeLLMClient contract

`examples/utils/fake_llm.py` exports one class: `FakeLLMClient`.

- Accepts a `response: str | BaseModel` at construction.
- Exposes a `chat(messages)` method that returns `response` regardless of
  input.
- Optionally exposes `async_chat(messages)` for async examples.
- Zero external dependencies — only stdlib + `promptstrings`.

When an example uses a real LLM call shape, it does so through
`FakeLLMClient`. A one-line comment in each such example names the real
client to substitute for production use.

## Environment

A new `examples` optional-dependency group in `pyproject.toml`:

```toml
[project.optional-dependencies]
examples = [
    "pydantic>=2.0,<3.0",
    "dishka>=1.0",
]
```

The `dev` dependency group gains `promptstrings[examples]` so that
`uv sync --all-extras` gives a complete development environment.

Install for running examples:

```bash
uv pip install "promptstrings[examples]"
python examples/01_basic_render.py
```

## CI

A dedicated `examples` job in `.github/workflows/workflow.yml`, dependent
on `test`:

```yaml
examples:
  runs-on: ubuntu-latest
  needs: test
  steps:
    - uses: actions/checkout@v5
    - uses: astral-sh/setup-uv@v6
    - run: uv python install 3.14
    - run: uv sync --all-extras
    - run: |
        for f in examples/[0-9]*.py; do
          uv run python "$f"
        done
```

The glob `examples/[0-9]*.py` targets numbered entry-point files and
excludes `examples/utils/`.

## Conventions

1. Every numbered file in `examples/` exits 0 and prints at least one line
   of output showing the rendered result.
2. `FakeLLMClient` is the default LLM stand-in; a comment marks where to
   swap in a real client.
3. File names describe the task or concept, not the API class.
4. Each file opens with a two-line docstring: what it demonstrates and
   what to change for production use.
5. No file imports from another example file (only from `examples/utils/`).

## Rejected alternatives

- **Jupyter notebooks** — not runnable in CI; not demonstrable via
  a single shell command in README.
- **`tests/examples/` directory** — mixes pedagogical material with the
  test suite; degrades readability of both.
- **No CI for examples** — silent rot; rejected unanimously.
- **Single environment, no extra** — leaves the install instruction
  ambiguous for users who only want to run examples.
