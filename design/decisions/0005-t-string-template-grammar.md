# 0005 — T-string template grammar

- **Status:** Accepted
- **Date:** 2026-04-26
- **Deciders:** Daniyar Supiyev
- **Supersedes:** ADR 0001 (partially — template grammar section only; all other promises and non-promises remain in force)
- **Superseded by:** —

## Context

`promptstrings` targets Python 3.14+. Python 3.14 ships PEP 750 t-strings
(`t"Hello, {name}"`), which produce a `string.templatelib.Template` object
instead of a `str`. T-strings carry structured interpolation data: each
`{expr}` becomes an `Interpolation` with the unevaluated expression, the
format spec, and the conversion. This is structurally superior to the
current `string.Formatter`-based parsing approach.

Forces at play:

- **Current grammar is a workaround.** `_compile_template` parses `str`
  templates via `string.Formatter.parse()` and then re-validates
  placeholders (identifier check, no format specs, no conversions). This
  is error-prone and has already produced one compile-error cause
  (`non_identifier_placeholder`) that exists purely because `str` format
  grammar is too permissive.
- **T-strings are structurally stricter.** The Python parser rejects
  invalid t-string interpolation syntax at parse time, before the library
  sees it. The library no longer needs to police format specs or
  conversions — those errors become `SyntaxError` at the call site.
- **Docstring-based templates cannot become t-strings.** A docstring is
  always a `str`. The decoration-time parsing path (ADR 0001 Promises 7
  and 8) works because docstrings are available at import time. With
  t-strings, the template must be supplied as a return value or an
  explicit argument — the docstring path becomes secondary (legacy) or is
  removed.
- **DX shift.** The primary usage pattern changes from:

  ```python
  @promptstring
  def greet(name: str) -> None:
      """Hello, {name}."""
  ```

  to:

  ```python
  @promptstring
  def greet(name: str) -> Template:
      return t"Hello, {name}."
  ```

  This is a breaking change for any caller relying on the docstring
  pattern. Since the library has not yet made a public 1.0 release, this
  break is acceptable before tagging.

- **Generator form is unaffected in shape.** `@promptstring_generator`
  already relies on `yield` expressions rather than a compiled template.
  The generator body can yield `Template` objects or plain strings;
  mixing is allowed.

- **`_CompiledTemplate` and `string.Formatter` become dead code.** The
  current compile pipeline (`_compile_template`, `_CompiledTemplate`,
  `_normalize_source`, `_get_compiled`, `_resolve_source`) is replaced by
  direct `Template` rendering.

- **ADR 0004 substring heuristic becomes more precise.** With t-strings,
  the generator strict-mode heuristic can compare against structured
  `Interpolation` objects rather than a full-text substring scan. The
  option (b) `Param` sentinel deferred in ADR 0004 may now be
  implementable cleanly as a first-class `Interpolation` check. This is
  tracked as a follow-on decision.

## Decision

**Python 3.14+ t-strings (`string.templatelib.Template`) replace
`str`-based docstring templates as the primary template grammar for
`@promptstring`.**

Specific commitments:

1. **Primary return type is `Template`.** A `@promptstring`-decorated
   function SHOULD return a `t"..."` t-string. The return annotation
   changes from `-> None` / `-> PromptSource` to `-> Template` /
   `-> PromptSource`.

2. **`PromptSource.content` accepts `Template | str`.** This allows
   external sources (Langfuse, etc.) to supply either a t-string or a
   plain-string template. When `content` is a `str`, it is rendered via
   `str.format_map` as before; when it is a `Template`, it is rendered
   via `string.templatelib` traversal.

3. **Docstring path is deprecated, not removed, in 1.0.** Functions with
   a `str` docstring template continue to work but emit a
   `DeprecationWarning` at decoration time. Removal is scheduled for 2.0.

4. **`_compile_template`, `_CompiledTemplate`, and `string.Formatter` are
   removed.** Template rendering goes through a new `_render_template(t:
   Template, values: dict[str, Any]) -> str` helper that traverses
   `t.args`.

5. **`PromptCompileError` cause `"format_spec"` and `"conversion"` are
   retired.** These errors are now `SyntaxError` at the call site (Python
   parser level). The cause `Literal` is narrowed to
   `"missing_template" | "non_identifier_placeholder"` for the docstring
   deprecation path; the two retired causes are removed from the public
   schema in 2.0. In 1.0 they remain in the `Literal` type for backwards
   compatibility but are never raised.

6. **`placeholders` on `_PromptString` is populated from the `Template`'s
   `Interpolation` keys, not from `Formatter.parse()`.** Decoration-time
   population is preserved: if the function body is a single `return
   t"..."` expression, the template is extracted at decoration time via
   `inspect.getsource` + `ast.parse`. If the body is non-trivial, 
   `placeholders` remains `frozenset()` until first render.

7. **`requires-python` bumps to `>=3.14`.** The `python_version` mypy
   setting bumps to `"3.14"`.

8. **`ADR 0001` template grammar promises are superseded here.** All
   other ADR 0001 promises (Protocol, exceptions, strict mode, DI,
   observer) remain in force unchanged.

## Alternatives considered

- **Keep `str` templates, add t-string as opt-in.** Would allow both
  grammars simultaneously. Rejected: two grammar paths double the
  compile and render surface, complicate `placeholders` semantics, and
  undercut the core DX promise of "no surprises." The library is pre-1.0
  — this is the right moment for the break.

- **Accept `Template` only, remove `str` path immediately.** Would be
  the cleanest design. Rejected: `PromptSource` is used with external
  content (Langfuse, etc.) that arrives as `str`; forcing those callers
  to wrap in `t""` adds friction with no benefit. `str` content in
  `PromptSource` stays.

- **Use t-strings only in the generator form, keep docstring for
  `@promptstring`.** Rejected: inconsistent grammar between the two
  decorator forms is harder to document and harder to type correctly. The
  migration cost is small given the library is pre-1.0.

- **Wait for Python 3.14 adoption to mature before migrating.** Rejected:
  the library explicitly targets 3.14+ (user decision). Delaying creates
  a migration cliff after 1.0 is tagged.

## Consequences

**Positive:**
- Template grammar errors are `SyntaxError` (Python parser) rather than
  `PromptCompileError` — fail-faster, better editor integration.
- `placeholders` is derived from structured `Interpolation` objects, not
  from fragile string parsing — more reliable.
- The generator strict-mode heuristic (ADR 0004) can be replaced with
  a structural check against `Interpolation` keys — eliminates the
  substring false-positive risk entirely (tracked as follow-on).
- `_compile_template`, `_CompiledTemplate`, and `string.Formatter` are
  deleted — net reduction in code.
- The `cause="format_spec"` and `cause="conversion"` error paths are
  dead — two test classes and one `Literal` branch retire with them.

**Negative:**
- Breaking change for any caller using the docstring pattern (mitigated
  by deprecation warning in 1.0, removal in 2.0).
- `DeprecationWarning` at decoration time adds noise for legacy callers
  who haven't migrated.
- `inspect.getsource` + `ast.parse` for decoration-time placeholder
  extraction is fragile in some environments (frozen modules, `exec`).
  The `frozenset()` fallback already exists and handles this.

**Neutral:**
- `pyproject.toml` `requires-python` and mypy `python_version` must be
  updated.
- All existing tests that use docstring templates must be migrated to
  `-> Template: return t"..."` pattern, or retained as legacy-path
  coverage with the deprecation warning suppressed.
- README quickstart must be rewritten.
- ADR 0001 `Superseded by` field must be updated to reference this ADR.

## Notes

- PEP 750: https://peps.python.org/pep-0750/
- `string.templatelib` module ships in Python 3.14 stdlib.
- ADR 0004 follow-on: if `Interpolation`-based strict-mode replaces the
  substring heuristic, a new ADR 0006 should record that decision and
  supersede ADR 0004.
