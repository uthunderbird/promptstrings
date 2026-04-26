# 0005 — T-string template grammar

- **Status:** Accepted
- **Date:** 2026-04-26
- **Deciders:** Daniyar Supiyev
- **Supersedes:** ADR 0001 (partially — internal compile representation and render path only; docstring authoring pattern and all other promises remain in force)
- **Superseded by:** —

## Context

`promptstrings` targets Python 3.14+. Python 3.14 ships PEP 750 t-strings
(`string.templatelib`), which produce a `Template` object carrying structured
`Interpolation` data instead of a plain `str`.

Investigation established the following facts before this ADR was written:

**What `Template(str)` does NOT do.** `Template('Hello, {name}.')` treats the
entire string as a single literal — `strings=('Hello, {name}.',)`,
`interpolations=()`. It does not parse `{name}` as a placeholder. T-strings
therefore cannot replace docstring parsing — `string.Formatter` is still
needed to parse the docstring into parts before constructing a `Template`.

**What programmatic `Template` construction gives us.** The constructor
`Template(*args: str | Interpolation)` accepts interleaved strings and
`Interpolation` objects. `Interpolation(value, expression, conversion=None,
format_spec='')` requires a `value` — but a module-level `_MISSING` sentinel
can be used at decoration time (no real value yet). The `expression` field is
an arbitrary string ("the arbitrary string provided when constructing the
interpolation instance," per docs) — not enforced to be an identifier.

**Injection surface.** The current `_CompiledTemplate.render()` is safe: it
does `str(values[field_name])` and appends — never calls `str.format_map`.
Attribute traversal (`{topic.__class__}`) is blocked by the `isidentifier()`
guard at compile time. Second-parse injection (`str.format` re-parsing a value
containing `{secret}`) does not occur — `str.format` is one-shot. The safety
is **implicit**: a future refactor to `str.format_map` would silently reopen
the attribute-leakage door. `Template` makes the safety **explicit by type** —
`str.format_map(Template)` is a `TypeError`.

**Render path.** A programmatically constructed `Template` (docstring-derived)
can be rendered via `expression`-lookup in `resolved`:

```python
''.join(
    item if isinstance(item, str) else str(resolved[item.expression])
    for item in tpl
)
```

A t-string-derived `Template` (returned from function body) must be rendered
via `item.value` directly — values are already resolved and the `expression`
may not match parameter names (`display = name.title(); return t"Hi, {display}."`).

**Performance.** Template iteration is ~35% slower than the current
`_CompiledTemplate.render()` list-walk (25.6ms vs 19.0ms per 100k renders).
Absolute difference: ~0.06 µs per render. LLM call latency dominates by
orders of magnitude — this is not a constraint.

Forces at play:

- **`_CompiledTemplate` is a reinvention of `Template`.** Both store
  `(strings, placeholder_names)` — `_CompiledTemplate` as a custom frozen
  dataclass, `Template` as a stdlib type. Replacing the former with the latter
  removes custom code and aligns the library's internal representation with the
  stdlib.
- **Type safety.** `Template` is not a `str`. Code that accidentally uses
  `str.format_map` on a template object gets a `TypeError` immediately rather
  than silently leaking object attributes. This prevents a class of future
  regression.
- **One internal type for all compiled templates.** Docstring-derived templates
  and t-string-derived templates currently have different internal types
  (`_CompiledTemplate` vs. the raw string in `PromptSource`). After this ADR,
  both are `Template`. Processing code (the render loop, `PromptMessage`
  construction, future audit fields) handles one type.
- **Docstring authoring pattern is unchanged.** `"""Hello, {name}."""` stays.
  T-strings cannot be docstrings: `t"..."` is `Expr(TemplateStr(...))` in the
  AST, not `Expr(Constant(...))`, so Python never assigns it to `__doc__`.
- **`isidentifier()` guard is retained.** `Template`/`Interpolation` do not
  enforce identifier-only expressions. The guard stays in the docstring parse
  path to produce a clear `PromptCompileError` at decoration time.

## Decision

**Replace `_CompiledTemplate` with `string.templatelib.Template` as the
library's internal compiled representation. Retain the docstring authoring
pattern unchanged. Add `Template` as an accepted return type from
`@promptstring`-decorated functions.**

Specific commitments:

1. **`_CompiledTemplate` is deleted.** Its role — storing parsed strings and
   placeholder names — is taken over by `string.templatelib.Template`.

2. **Docstring parse path produces a `Template`.** `_compile_template` (or its
   successor) parses the docstring via `string.Formatter.parse()`, applies all
   existing guards (`isidentifier()`, no format specs, no conversions), then
   constructs and returns a `Template` using a module-level `_MISSING`
   sentinel as the `value` for each `Interpolation`. `string.Formatter` is
   still imported and used at decoration time for parsing; it is not removed.

   ```python
   _MISSING = object()  # module-level singleton

   def _parse_docstring(source: str, *, prompt_name: str) -> Template:
       args: list[str | Interpolation] = []
       for literal, field_name, fmt_spec, conversion in Formatter().parse(source):
           if literal:
               args.append(literal)
           if field_name is None:
               continue
           # existing guards: fmt_spec, conversion, isidentifier()
           args.append(Interpolation(_MISSING, field_name))
       return Template(*args)
   ```

3. **Docstring-derived `Template` is rendered via `expression`-lookup.**

   ```python
   def _render_static(tpl: Template, resolved: dict[str, Any]) -> str:
       return ''.join(
           item if isinstance(item, str) else str(resolved[item.expression])
           for item in tpl
       )
   ```

4. **`Template` is accepted as a return type from `@promptstring` functions.**
   A function annotated `-> Template` (or returning a `Template` at runtime)
   is treated as a dynamic template. It is rendered via `item.value` — values
   are already resolved by the time the function is called with its parameters.

   ```python
   def _render_dynamic(tpl: Template) -> str:
       return ''.join(
           item if isinstance(item, str) else str(item.value)
           for item in tpl
       )
   ```

5. **Two render strategies, one type.** The library knows which strategy to
   use by the source of the `Template`:
   - Docstring-derived (value is `_MISSING`): `_render_static` with `resolved`
   - T-string-derived (value is real): `_render_dynamic`

   Code that processes templates — `placeholders` property, strict-mode check,
   future `PromptMessage.interpolations` — handles one type regardless of
   source.

6. **`placeholders` is populated from `Template.interpolations`.** For
   docstring-derived templates (compiled at decoration time), `placeholders`
   returns `frozenset(i.expression for i in tpl.interpolations)` — no change
   in behavior, but the source changes from `_CompiledTemplate.placeholders`
   to `Template.interpolations`. For dynamic-source functions (`-> PromptSource`
   or `-> Template` with non-trivial body), `placeholders` remains
   `frozenset()` until render time.

7. **`PromptCompileError` causes `"format_spec"` and `"conversion"` are
   retained.** These are still raised for docstring templates containing
   `{name:>10}` or `{name!r}`. The t-string path never raises them (Python
   parser handles format specs and conversions natively for t-strings, which
   carry them in `Interpolation.format_spec` and `Interpolation.conversion`).
   The `Literal` type is unchanged.

8. **`requires-python` bumps to `>=3.14`.** The `python_version` mypy setting
   bumps to `"3.14"`. `string.templatelib` is stdlib in 3.14.

## Alternatives considered

- **Keep `_CompiledTemplate`, use `Template` only for t-string returns.**
  Would still require two internal types — `_CompiledTemplate` for docstrings,
  `Template` for returns. Rejected: no type-safety benefit for the docstring
  path; future processing code must handle both types. The unification benefit
  is lost.

- **Parse docstrings directly into `Template` via `Template(str)`.** Does not
  work — `Template('Hello, {name}.')` treats the entire string as a literal.
  `string.Formatter` parsing is still required.

- **Replace docstring authoring with `return t"..."` pattern.** Would make
  t-strings the primary DX. Rejected: t-strings cannot be docstrings (AST
  constraint), and the docstring pattern is well-established and unchanged.
  The t-string return path is an addition, not a replacement.

- **Use `None` instead of `_MISSING` sentinel as Interpolation value.**
  `None` is a valid user value. `_MISSING = object()` is an unforgeable
  identity-checkable sentinel — preferred for correctness.

## Consequences

**Positive:**
- `_CompiledTemplate` custom dataclass deleted — stdlib `Template` takes its
  place. Net code reduction.
- Type safety: `Template` cannot be passed to `str.format_map`. Future
  refactors that accidentally use `str.format_map` get a `TypeError`
  immediately.
- One internal type for all compiled templates — processing code is simpler.
- `placeholders` populated from `Template.interpolations` — same behavior,
  no custom parsing needed after decoration.
- `return t"Hello, {name}."` is now a first-class, supported authoring
  pattern with full type-checker support.

**Negative:**
- `string.Formatter` is NOT removed — still used for docstring parsing.
- `_render_static` / `_render_dynamic` strategy split must be maintained —
  two render loops for one type.
- 35% render overhead vs. current `_CompiledTemplate.render()` list-walk.
  Absolute: ~0.06 µs per render. Irrelevant for LLM workloads.
- `_MISSING` sentinel must be a module-level singleton (not per-call
  `object()`); callers must not inspect `Interpolation.value` on
  docstring-derived templates.

**Neutral:**
- `requires-python` bumps to `>=3.14`. `pyproject.toml` and mypy config
  updated.
- Existing tests using docstring authoring are unaffected — DX unchanged.
- `_normalize_source` helper may be removed (its role is absorbed by
  `_parse_docstring`).
- ADR 0004 follow-on: generator `yield t"..."` path enables structural
  strict-mode check via `Interpolation.expression` — tracked as ADR 0006.

## Notes

- PEP 750: https://peps.python.org/pep-0750/
- `string.templatelib` docs: https://docs.python.org/3/library/string.templatelib.html
- `Interpolation.__new__` signature: `(value, expression, conversion=None, format_spec='')`
- `Template.__new__` signature: `(*args: str | Interpolation)` — consecutive
  strings concatenated; consecutive interpolations get empty-string separators.
- Injection analysis: `str.format` does NOT second-parse values (one-shot
  substitution only). Attribute leakage (`{topic.__class__}`) is blocked by
  `isidentifier()` guard retained from current implementation.
