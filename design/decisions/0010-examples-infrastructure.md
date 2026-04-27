# 0010 — Examples infrastructure

- **Status:** Accepted
- **Date:** 2026-04-27
- **Target version:** 1.3.0
- **Deciders:** Daniyar Supiyev
- **Supersedes:** —
- **Superseded by:** —

## Context

The library ships no runnable examples. Users who want to understand
real-world usage have only the README snippets and the unit-test suite,
neither of which is written as pedagogical material. Three gaps follow
from this:

1. **Discoverability** — the path from "installed the library" to "saw it
   do something useful" is unclear.
2. **Integration coverage** — scenarios involving `PydanticPromptContext`,
   `DishkaContext`, `Observer`, and `response_schema` are tested in unit
   tests but never shown end-to-end.
3. **Rot** — any examples added ad-hoc without CI verification become
   stale without anyone noticing.

The decision must answer four questions jointly: where examples live, what
format they take, what environment they require, and how they are verified.

## Decision

Add an `examples/` directory at the repository root containing numbered
self-contained Python scripts, a `utils/` subdirectory with a
`FakeLLMClient`, a new `examples` optional-dependency group, and a
dedicated CI job.

### Directory layout

```
examples/
  utils/
    fake_llm.py
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

Numbers encode recommended reading order, not execution dependency.
Each numbered file is self-contained (imports only from `promptstrings`
and `examples/utils/`).

### Example catalogue

| File | Primary concept |
|------|-----------------|
| `01_basic_render.py` | `@promptstring`, `PromptContext`, `render()` / `render_messages()` |
| `02_prompt_source.py` | `-> PromptSource` dynamic source, `PromptSourceProvenance` |
| `03_dependency_injection.py` | `PromptDepends` default-value form |
| `04_annotated_di.py` | `Annotated[T, PromptDepends(…)]` — primary DI syntax (ADR 0007) |
| `05_generator.py` | `@promptstring_generator`, multi-turn yield |
| `06_structured_output.py` | `-> MyModel` + `response_schema` + instructor-style call via `FakeLLMClient` |
| `07_pydantic_context.py` | `PydanticPromptContext.from_model()` as context source |
| `08_dishka_integration.py` | `DishkaContext` + `From()` for container-resolved dependencies |
| `09_observer.py` | `Promptstrings` config + `Observer` for render-event tracing |
| `10_response_schema.py` | `response_schema` as single source of truth across multiple prompt functions |

### FakeLLMClient

`examples/utils/fake_llm.py` exports `FakeLLMClient`:

- Constructed with a `response: str | BaseModel`.
- `chat(messages)` and `async_chat(messages)` return `response`
  regardless of input.
- Zero external dependencies beyond stdlib and `promptstrings`.

Examples that demonstrate an LLM call use `FakeLLMClient` by default. A
single comment in each such file names the real client to substitute.

### Optional-dependency group

```toml
[project.optional-dependencies]
examples = [
    "pydantic>=2.0,<3.0",
    "dishka>=1.0",
]
```

The `dev` group acquires `promptstrings[examples]` so that
`uv sync --all-extras` gives a complete development environment.

Users install and run examples with:

```bash
uv pip install "promptstrings[examples]"
python examples/01_basic_render.py
```

### CI job

A new `examples` job in `.github/workflows/workflow.yml`, dependent on
`test`, runs every numbered entry-point file:

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

### Conventions

1. Every numbered file exits 0 and prints at least one line showing the
   rendered result.
2. `FakeLLMClient` is the default LLM stand-in; a comment marks the swap
   point.
3. File names describe the use-case or concept, not the API class name.
4. Each file opens with a two-line module docstring: what it demonstrates
   and what to change for production use.
5. No numbered file imports from another numbered file.

## Alternatives considered

- **Jupyter notebooks** — rejected. Not runnable in CI; not demonstrable
  with a single shell command; requires a kernel installation that exceeds
  the library's dependency surface.

- **`tests/examples/` directory** — rejected. Mixes pedagogical scripts
  with the unit-test suite; pytest fixtures and output formatting obscure
  the usage intent; test files are not naturally discoverable by users
  browsing the repo.

- **`examples/` without CI** — rejected. Without automated verification,
  examples accumulate silent rot. Every past project that held examples
  outside CI has demonstrated this failure mode within months.

- **No dedicated `examples` extra; absorb into `dev`** — rejected.
  Leaves the install instruction for users ambiguous ("install dev
  dependencies to run examples?") and inflates the development
  environment with user-facing optional deps that are orthogonal to
  test infrastructure.

## Consequences

- **Positive:** Single entry point for new users — one `pip install` and
  one `python` command per concept.
- **Positive:** Every integration scenario (dishka, pydantic, observer,
  response_schema) has a verified end-to-end path.
- **Positive:** CI catches example rot on every push to main.
- **Negative:** Ten new files to maintain; each API change that affects
  the public surface may require updating one or more examples.
- **Neutral:** CI build time increases by one job (expected: <30 s).
- **Neutral:** `examples` extra must be kept in sync with the integration
  extras (`dishka`, `pydantic`).

## Notes

Exploratory discussion and rejected-alternatives detail:
`design/proposals/examples-infrastructure.md`.
