# 0009 — `response_schema` property for structured output

- **Status:** Accepted
- **Date:** 2026-04-27
- **Deciders:** Daniyar Supiyev
- **Supersedes:** —
- **Superseded by:** —

## Context

LLM frameworks (instructor, litellm, OpenAI SDK structured outputs) accept a
`response_model` / `response_format` argument that tells the model what type to
return. Users who annotate their prompt function with a return type (`-> MyModel`)
currently have to repeat that type at the call site:

```python
@promptstring
def extract(text: str) -> InvoiceModel:
    """Extract invoice data from: {text}"""

# MyModel appears twice: once in the decorator, once at the call site
result = client.chat.completions.create(
    response_model=InvoiceModel,             # ← duplicated
    messages=await extract.render_messages(ctx),
)
```

`promptstrings` is designed to be the single point of truth for a prompt's
full specification. The expected response type is part of that specification,
yet it is currently not surfaced by the library. The return annotation is
already available on the decorated function and is partially parsed at
decoration time (to detect `None`, `...`, `Template`, `PromptSource`), but the
information is discarded rather than exposed.

## Decision

Add a `response_schema: Any` read-only attribute to both `_PromptString` and
`_PromptStringGenerator`, and include it in the `Promptstring` Protocol.

**Semantics:**

- Set once at decoration time from the function's resolved return annotation.
- Returns `None` for all promptstrings-internal return types: `None`, `...`
  (Ellipsis), `str`, `Template`, `PromptSource`. These signal template-path
  behaviour, not an output schema.
- Returns the raw annotation object (`type`, `GenericAlias`, or any other
  value) for all other return annotations — including `MyModel`,
  `list[MyModel]`, `int`, and custom dataclasses. The library does not
  validate or inspect the value; it is the LLM framework's responsibility.
- `response_schema` is `None` when the return annotation is absent or
  unresolvable.

With this property the call site becomes:

```python
result = client.chat.completions.create(
    response_model=extract.response_schema,  # ← single source of truth
    messages=await extract.render_messages(ctx),
)
```

**Type annotation:** `Any` — because valid values include `type[T]`,
`types.GenericAlias` (`list[MyModel]`), plain `type` (`int`, `str`), and
potentially other annotation forms. Using `type[Any]` would be incorrect for
generic aliases; `Any` is the honest annotation.

**Protocol:** `response_schema` is added to `Promptstring` as an append-only
extension (permitted by ADR 0001 Promise 2 "append-only in 1.x"). Existing
structural implementations that lack this attribute will no longer satisfy
`isinstance(x, Promptstring)` — this is the expected cost of append-only
growth, not a break of the locked contract.

## Alternatives considered

- **No library change — user reads `fn.__wrapped__.__annotations__['return']`
  manually** — rejected. Bypasses the Protocol abstraction entirely; breaks
  if the decorated function's internal structure changes; requires the user to
  know which attribute to read and handle the special-type exclusions
  themselves.

- **`response_schema: type[Any] | None`** — rejected. `type[Any]` does not
  cover `list[MyModel]` (a `GenericAlias`, not a `type`) or other valid
  annotation forms. Using `type[Any]` would be incorrect for callers that pass
  generic schemas to instructor or litellm.

- **Pydantic-specific `response_model` property** — rejected. Coupling core
  to Pydantic is inconsistent with the zero-dependency principle (ADR 0001
  Promise 13). The raw annotation approach works for any framework and any
  class, not just `BaseModel` subclasses.

- **`response_type` as the attribute name** — considered. `response_schema`
  is preferred because LLM framework APIs consistently use "schema" or
  "response_model" terminology, making the mapping more obvious to integrators.

## Consequences

- **Positive:** Single source of truth for prompt specification including
  expected output type. Framework-agnostic: works with instructor, litellm,
  OpenAI structured outputs, and any future framework.

- **Positive:** Zero runtime overhead — value computed once at decoration time
  from already-resolved `self._hints`. No new imports, no third-party
  dependencies.

- **Positive:** Enables writing truly generic `call_llm(prompt: Promptstring,
  ctx: PromptContext)` helpers that route structured output without knowing
  the concrete prompt class.

- **Negative:** Soft Protocol break for custom `Promptstring` implementations
  that lack `response_schema`. Acceptable under the "append-only" contract;
  documented in ADR 0001.

- **Neutral:** `response_schema` is `None` for all docstring-only prompts
  without an explicit return type. Callers should check for `None` before
  passing to a framework.

## Notes

Internal return types that yield `response_schema = None`:

| Return annotation | `response_schema` |
|---|---|
| absent / `None` | `None` |
| `...` (Ellipsis) | `None` |
| `str` | `None` |
| `Template` | `None` |
| `PromptSource` | `None` |
| `MyModel` | `MyModel` |
| `list[MyModel]` | `list[MyModel]` |
| `int`, `dict`, etc. | as-is |
