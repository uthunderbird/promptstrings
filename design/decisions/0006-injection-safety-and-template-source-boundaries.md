# 0006 — Injection Safety and Template Source Boundaries

- **Status:** Accepted
- **Date:** 2026-04-27
- **Deciders:** Daniyar Supiyev
- **Supersedes:** ADR 0001 (partially — P0-6 dynamic PromptSource re-parse promise)
- **Superseded by:** —

## Context

A structured red-team review of `promptstrings` identified four security and
correctness failures in the framework's render paths. This ADR specifies the
architectural decisions that close each finding.

### Red-Team Findings

**FINDING-1 (P0) — Second-parse injection via `PromptSource` content.**
Any `str` returned by a `@promptstring` function, or any `PromptSource.content`
string, was passed to `_parse_docstring` at render time. If that string
contained `{param_name}` where `param_name` is a resolved parameter,
`_render_static` substituted the parameter's value — even if the developer
intended to display the placeholder literally.

Concrete exploit:

```python
@promptstring(strict=False)
def build_prompt(user_query: str, api_key: str) -> str:
    return f"Query: {user_query}"

ctx = PromptContext({"user_query": "{api_key}", "api_key": "sk-secret"})
# Returned "Query: sk-secret" — api_key injected via user-controlled input
```

The ADR 0005 injection safety claim ("second-parse injection does not occur")
was true only for the docstring and `-> Template` paths. It was false for the
`-> str` and `-> PromptSource` paths.

**FINDING-2 (P1) — Runtime source override silently discards compile-time
guarantees.** A function with a docstring (eagerly compiled at decoration time)
that returned a non-None value at runtime caused `_resolve_source` to discard
the compiled template and use the returned value. The compile-time
`isidentifier()` guard, format-spec guard, and conversion guard were
irrelevant to the actual render. Strict-mode and `placeholders` reflected the
docstring, but the runtime render used a different path with different guards.

**FINDING-3 (P1) — Structural strict-mode false positives for non-identifier
t-string expressions.** The generator structural strict-mode check compared
`Interpolation.expression` values against `resolved` parameter names. For
`{name.upper()}`, expression = `"name.upper()"`, which is not in `resolved`.
Any t-string with method calls, attribute access, or compound expressions
triggered a spurious `PromptUnreferencedParameterError`.

**FINDING-4 (P1) — Raw `KeyError` breaks the error contract.** When a
placeholder expression had no matching resolved parameter, `_render_static`
raised `KeyError` — not `PromptRenderError`. The library's error contract
(all render failures are `PromptRenderError` subclasses) was broken.

### Injection Safety Model (Pre-Fix)

ADR 0005 described `Template` as making injection safety "explicit by type."
That claim held for the docstring and `-> Template` paths only. The framework
had three render paths; ADR 0005 correctly analyzed two of them and did not
fully analyze the `-> PromptSource` path.

## Decision

### D1 — `PromptSource.content` and `-> str` returns are literal passthrough

`PromptSource.content` is treated as a **literal string** — it is never
re-parsed as a template. `-> str` returns are similarly treated as literal
content. `_parse_docstring` is not called on any value that was not the
function's docstring (frozen at decoration time).

`PromptSource` remains the correct return type for prompts with provenance
metadata. Its `.content` field is rendered verbatim as the prompt message
content, with no placeholder substitution.

**Migration from `PromptSource(content="{placeholder}...")`:**

1. *Code-authored dynamic templates:* Replace with `return t"..."` (t-string).
   The `-> Template` path is the correct dynamic templating mechanism.

2. *Externally loaded template strings* (database, config system): parse the
   loaded string with `parse_trusted_template(source)` (see D5) to obtain a
   `Template`, then return the `Template` from the function body.

**Retired promise:** ADR 0001 P0-6 ("dynamic PromptSource can introduce
placeholders resolvable at render time") is retired by this ADR. P0-6 is
replaced by **P0-6ʹ**: "A returned `Template` that references an expression
whose expression text has no matching resolved parameter raises
`PromptRenderError` at render time."

### D2 — Compile-time and render-time guards against mixed source mode

**Compile-time** (`_compile_at_decoration`): if a function has a docstring
AND a non-None return annotation (`-> PromptSource`, `-> Template`, `-> str`,
etc.), raise `PromptCompileError` with `cause="mixed_source_mode"`. A function
cannot declare both a docstring template and a dynamic return annotation.

**Render-time** (`_resolve_source`): if `self._compiled` is not None (the
function has an eagerly compiled docstring template) and the function returns
a non-None value at runtime, raise `PromptRenderError` with a message
directing the developer to use `-> Template` or `-> PromptSource` instead.

Together these guards ensure that docstring-based functions always return
`None` (using the compiled docstring) and dynamic-source functions always
return a value (never `None`, which would silently produce an empty prompt).

### D3 — Structural strict-mode applies only to fully resolvable expression sets

In `_PromptStringGenerator._render_messages_impl`, the `all_structured`
condition for structural strict-mode is tightened to require that every
`Interpolation.expression` is a bare identifier present in `resolved`:

```python
all_structured = (
    bool(template_yields)
    and not str_yields
    and all(
        i.expression.isidentifier() and i.expression in resolved
        for tpl in template_yields
        for i in tpl.interpolations
    )
)
```

When `all_structured` is True, the structural check is exact and produces no
false positives. When False (any expression is non-identifier or maps to a
non-parameter local variable, as in `{name.upper()}` or `{display}`), the
check falls back to the substring heuristic (ADR 0004). This eliminates false
positives for realistic t-string authoring patterns while preserving the
exactness guarantee when it can be applied.

### D4 — `_render_static` wraps `KeyError` → `PromptRenderError`

`_render_static` is rewritten to catch `KeyError` from `resolved[item.expression]`
and re-raise as `PromptRenderError` with `missing_key=item.expression`. This
restores the error contract: all render failures are `PromptRenderError`
subclasses.

### D5 — Public `parse_trusted_template` utility

A public function `parse_trusted_template(source, *, prompt_name)` is added
to the library's public API. It delegates to `_parse_docstring` and applies the
same grammar guards (identifier-only placeholders, no format specs, no
conversions). This enables the externally-loaded-template use case (migration
path 2 from D1) without re-introducing an implicit injection surface.

The function's docstring carries an explicit security warning: callers are
responsible for ensuring the source string is trusted. User-controlled content
must not be passed to this function.

### Revised Injection Safety Claim

The framework guarantees injection safety on the following paths:

| Path | Injection safety |
|---|---|
| Docstring template (`"""..."""`) | **Guaranteed** — template frozen at decoration time; user values substituted as `str()`, never re-parsed |
| `-> Template` (t-string return) | **Guaranteed** — Python evaluates all expressions before the function returns; `_render_dynamic` uses `item.value`, no re-parsing |
| `-> PromptSource` (after D1) | **Guaranteed** — `.content` is a literal string passthrough; no placeholder substitution |
| `-> str` (after D1) | **Guaranteed** — treated as literal content; no placeholder substitution |
| `parse_trusted_template(source)` | **Developer's responsibility** — caller must ensure `source` is not user-controlled |

The framework does not and cannot prevent prompt injection of user-controlled
*values* into template *output* — that is a downstream concern outside the
framework's scope.

## Alternatives Considered

- **Document the risk without code change.** Rejected: documentation cannot
  prevent injection. The fix must be architectural. Developers who don't read
  the security ADR are still vulnerable.

- **Keep `PromptSource` re-parsing with an explicit opt-in flag
  (`parse_as_template: bool = False`).** Rejected: opt-in injection surfaces
  are still injection surfaces. The flag conflates provenance-carrying
  (`PromptSource`'s purpose) with template-parsing (`Template`'s purpose).
  `parse_trusted_template` provides the same capability with explicit
  developer intent and a visible security call-site.

- **Root-identifier extraction from `Interpolation.expression` for D3.**
  Rejected: string-split heuristics (`expression.split('.')[0]`) have edge
  cases (`{a + b}`, `{x if y else z}`) that produce unpredictable "used" sets.
  The "fall back to heuristic when not fully resolvable" approach is safer and
  consistent with ADR 0004's documented heuristic boundary.

## Consequences

**Positive:**
- Second-parse injection is architecturally eliminated on all paths except the
  explicitly documented `parse_trusted_template` utility.
- The injection safety model is complete and honest: four paths, each with a
  clear guarantee or explicit developer responsibility.
- Error contract is restored: all render failures are `PromptRenderError`.
- Structural strict-mode false positives eliminated for common t-string
  patterns (`{name.upper()}`, `{obj.field}`, etc.).
- Compile-time detection of mixed source mode prevents a class of silent
  misconfiguration bugs.

**Negative:**
- ADR 0001 P0-6 (dynamic PromptSource re-parse) is retired — a semver-relevant
  change. Code using `PromptSource(content="{placeholder}...")` must migrate.
- `PromptCompileError.cause` Literal gains a new member `"mixed_source_mode"`.
- `parse_trusted_template` adds a new public API surface that must be maintained
  with stable semver guarantees.

**Neutral:**
- `PromptSource` remains the correct return type for prompts with provenance
  metadata — its semantics narrow (provenance carrier only), not its usage.
- Generator substring heuristic (ADR 0004) is unchanged; structural strict-mode
  now falls back to it more often (for non-identifier expressions), which is
  the documented behavior.
- `_parse_docstring` remains internal; `parse_trusted_template` is the
  stable public name.

## Notes

- Red-team session: 2026-04-27, conducted in-session via `/swarm-red-team`.
- FINDING-3 interacts with ADR 0004's documented heuristic limitations; the D3
  fix does not change ADR 0004's contracts, it narrows when the structural path
  is taken.
- FINDING-4 (KeyError) also applies if `_parse_docstring` produces expressions
  that aren't in `resolved`; D4 covers this case uniformly.
