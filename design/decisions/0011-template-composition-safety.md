# 0011 — Template composition safety

- **Status:** Accepted
- **Date:** 2026-04-27
- **Target version:** 1.3.0
- **Deciders:** Daniyar Supiyev
- **Supersedes:** —
- **Superseded by:** —

## Context

A natural usage pattern is composing multiple `@promptstring` functions: the
result of one prompt's `render()` call is passed as a parameter value to
another. This raises three questions that were previously unexamined:

1. **Injection safety** — does a rendered string that contains `{placeholder}`
   syntax get re-parsed when substituted into an outer template?
2. **DI correctness** — do `PromptDepends` / `AwaitPromptDepends` resolvers in
   both inner and outer prompts behave correctly when sharing a `PromptContext`?
3. **Silent DX failure** — what happens when a `_PromptString` object is passed
   as a parameter value instead of the result of `await render()`?

An audit across all render path combinations (docstring × docstring,
docstring × t-string, t-string × docstring, t-string × t-string,
`parse_trusted_template` × any) confirmed that questions 1 and 2 are already
safe by architectural design, but question 3 exposes a silent DX failure that
needs an explicit guard.

## Decision

### D1 — Second-parse injection does not exist; document this guarantee

`_render_static` produces its output via `str(resolved[expression])` followed
by `"".join(parts)`. The resulting string is never re-parsed as a template.
`_render_dynamic` is identical in structure: `str(item.value)` followed by a
join. No render path in the library performs a second parse on substituted
values.

This is an unconditional guarantee across all path combinations:

| Inner path | Outer path | Second-parse? |
|---|---|---|
| docstring | docstring | No |
| t-string | docstring | No |
| docstring | t-string | No |
| t-string | t-string | No |
| `parse_trusted_template` | any | No |

A user-controlled value containing `{identifier}` syntax passes through
literally and is never substituted.

No code change is required for D1. The guarantee is architectural.

### D2 — `PromptContext` is intentionally unscoped; document the naming implication

When inner and outer prompts share a `PromptContext` instance (e.g. passed
through a `PromptDepends` resolver), both resolver functions see the full flat
dict. There is no automatic scoping or namespace isolation between inner and
outer prompts.

This is expected behaviour — `PromptContext` is a simple immutable dict
wrapper. The risk is that if inner and outer prompts declare resolvers that read
the same key name with different intent, the inner resolver may silently consume
a value intended for the outer prompt.

**Mitigation:** use distinct key names when composing prompts that share a
context. No code change is required.

### D3 — Guard against passing a `Promptstring` object as a parameter value

When a `_PromptString` or `_PromptStringGenerator` object is passed as a
parameter value (i.e. the developer forgot `await prompt.render(ctx)`), both
`_render_static` and `_render_dynamic` currently produce a meaningless
`<_PromptString object at 0x...>` string without any error. Strict mode does
not catch this because the parameter name is present in the template and in
`resolved`.

Add an explicit guard in both render functions: before calling `str(value)`,
check whether `value` is an instance of the `Promptstring` Protocol and raise
`PromptRenderError` with an actionable message:

```
PromptRenderError: Parameter 'system' is a Promptstring object — did you
forget `await prompt.render(ctx)`?
```

This check fires regardless of strict mode. It is the only render-time
isinstance check on parameter values; no other type coercions are added.

### D4 — Document template composition as a supported pattern; add example

Add `examples/12_template_composition.py` demonstrating:
- the direct composition pattern (`await inner.render(ctx)` as a parameter)
- the DI composition pattern (`AwaitPromptDepends` resolver that renders inner)
- a note on shared-ctx key naming

## Alternatives considered

- **`_PromptString.__str__` raises `TypeError`** — rejected. `str()` raising is
  a violation of Python convention and would break any code that legitimately
  serialises a prompt object for debugging.

- **Warn instead of raise in D3** — rejected. A warning that produces a
  malformed prompt silently is worse than a hard failure. The developer's intent
  was clearly to get a rendered string; the right signal is an error.

- **Scope `PromptContext` per render call (D2)** — rejected for 1.x. Scoping
  would require a breaking change to `PromptContext` semantics (currently a
  flat immutable dict by ADR 0001 Promise 6). Deferred to post-1.x if needed.

- **Raise at decoration time if a parameter's type annotation is `Promptstring`
  or a subtype** — rejected. Type annotations are not always present, and
  static checking is better handled by mypy/pyright than by runtime enforcement
  at decoration time.

## Consequences

- **Positive:** Second-parse injection safety is now explicitly guaranteed and
  documented, not merely implied by implementation.
- **Positive:** Passing a `Promptstring` object instead of its rendered value
  becomes a hard, actionable error instead of a silent wrong result.
- **Positive:** Template composition is a documented first-class pattern with a
  runnable example.
- **Negative:** D3 adds one isinstance check per substituted parameter in both
  `_render_static` and `_render_dynamic`; negligible runtime cost.
- **Neutral:** `PromptContext` scoping is explicitly deferred; shared-ctx naming
  discipline is the documented mitigation.

## Notes

Audit methodology: seven live test scenarios were run across all render path
combinations before this ADR was written. All injection tests confirmed no
second-parse. The silent DX failure (D3) was discovered via test scenario 4
(passing a `_PromptString` object directly as a `PromptContext` value).
