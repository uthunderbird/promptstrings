# Changelog

All notable changes to `promptstrings` will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.3.0] - 2026-07-13

### Added
- Template composition is a supported first-class pattern (ADR 0011). Passing the result of
  `await inner.render(ctx)` as a parameter value to an outer prompt is safe: substituted values
  are never re-parsed as templates, on every render path combination (docstring × t-string ×
  `parse_trusted_template`). A user-controlled value containing `{identifier}` syntax passes
  through literally.
- Examples infrastructure (ADR 0010): runnable, dependency-light examples under `examples/`,
  one file per concept, plus an `examples` extra (`pip install promptstrings[examples]`).
- `examples/11_fastapi_endpoint.py` — DI-backed prompt rendering inside a FastAPI endpoint.
- `examples/12_template_composition.py` — direct and DI composition patterns, with a note on
  key naming when inner and outer prompts share a `PromptContext`.

### Changed
- Passing an unrendered promptstring (a `@promptstring` / `@promptstring_generator` object — i.e.
  a forgotten `await prompt.render(ctx)`) as a parameter value now raises `PromptRenderError`
  with an actionable message instead of silently rendering
  `<promptstrings.core._PromptString object at 0x...>` into the prompt (ADR 0011, D3). Fires on
  both render paths — `{name}` substitution and t-string interpolation — and regardless of strict
  mode.
  - The check is nominal, not structural: it does **not** test the `Promptstring` Protocol.
    Third-party implementations of that Protocol (the documented extension surface, ADR 0001
    Promise 2) still substitute via their own `__str__`.
  - `str(prompt_object)` is unaffected; serialising a prompt object for debugging still works.
  - `missing_key` is `None` on both raise sites: the parameter *was* resolved, so this is not a
    missing-key path (ADR 0003 field schema).

## [1.2.0] - 2026-04-27

### Added
- `response_schema` property for structured output (ADR 0009).

### Changed
- PEP-563 string return annotations are now resolved for dynamic-source detection and for
  `response_schema`: `_has_dynamic_return_annotation` evaluates string annotations against the
  function's globals, so an aliased or `from __future__ import annotations` style
  `-> PromptSource` / `-> Template` is recognised where it previously was not. Unresolvable
  return annotations fall back to the raw string instead of being dropped.

## [1.1.0] - 2026-04-27

### Added
- `Annotated` DI syntax and the `integrations` package (ADR 0007): `PromptDepends` /
  `AwaitPromptDepends` can be declared as `Annotated[T, PromptDepends(...)]`, with
  first-class Dishka (`DishkaContext` + `From()`) and Pydantic v2 support.
- `-> ...` (Ellipsis) return annotation is treated as equivalent to `-> None`.
- Differentiated fail-fast for `get_type_hints` `NameError`.

### Changed
- Async resolver concurrency now uses `asyncio.wait` + explicit cancellation instead of
  `asyncio.gather` (ADR 0008), giving deterministic cancellation and error propagation when
  one resolver fails.
- CI: `actions/checkout@v5` and `setup-uv@v6` (Node.js 24).

## [1.0.0] - 2026-04-27

First stable release. The API contract — stability guarantees, the 13 promises, and the DX
rubric — is documented in
[`design/decisions/0001`](design/decisions/0001-api-and-dx-baseline-for-1.0.md). From 1.0 the
project follows SemVer: breaking changes require a major version bump.

### Added
- Trusted-publisher release workflow.
- t-string template grammar on Python 3.14 (ADR 0005): the internal `_CompiledTemplate` is
  replaced by `string.templatelib.Template`. A `@promptstring` function may return a t-string
  (`t"..."`) annotated `-> Template`; `@promptstring_generator` may yield one. Generator
  strict-mode checking is structural as a result.
- `parse_trusted_template` for externally loaded template strings (ADR 0006), renamed from its
  pre-1.0 name to make the security contract explicit: only pass strings whose content you
  control, since `{param_name}` syntax in user-supplied input would be substituted.
- Injection-safety guarantees (ADR 0006): substituted values are never re-parsed as templates on
  any render path. The t-string path evaluates all expressions before the function returns.
- `PromptDepends` parameters are exempt from the strict unused-parameter check; error messages
  reworked for actionability.
- Integration seams (ADR 0002): the `Promptstrings` configuration carrier and the `Observer`
  hook.
- Generator strict-mode WARNING log via `promptstrings.strict_heuristic` logger (ADR 0004,
  non-contract implementation recommendation): emits WARNING at `logging.WARNING` level when
  a resolved parameter has `str(value) == ""` (guaranteed false negative) or
  `len(str(value)) <= 1` (elevated false-positive risk). Does not affect strict-mode outcome.
- Concurrent `AwaitPromptDepends` resolution via `asyncio.gather` (ADR 0001 Promise 9).
  All `AwaitPromptDepends` in a single render now run concurrently; the first exception
  cancels the rest. The at-most-one guard is removed — this is a one-way door.
  Resolvers must be cancellation-safe and must not depend on sibling side effects.
- `PromptUnusedParameterError` and `PromptUnreferencedParameterError` leaf exception classes
  (ADR 0001 Promise 3, C2 delta / R1 / R4):
  - `PromptUnusedParameterError`: `unused_parameters: tuple[str, ...]`, `resolved_keys: tuple[str, ...]`
  - `PromptUnreferencedParameterError`: `unreferenced_parameters: tuple[str, ...]`, `resolved_keys: tuple[str, ...]`
  - Both exported from top-level package.
  - Strict-mode raise sites in `_PromptString` updated to use `PromptUnusedParameterError`.
  - Strict-mode raise site in `_PromptStringGenerator` updated to use `PromptUnreferencedParameterError`.
- Named attributes and `to_dict()` on all public exception classes per ADR 0003 (R6):
  - `PromptRenderError`: `missing_key: str | None`, `context_keys: tuple[str, ...] | None`
  - `PromptCompileError`: `prompt_name: str`, `cause: Literal[...]`, `placeholder: str | None`,
    `optimize_mode_active: bool`; `to_dict()` includes parent fields always as `None`
  - `PromptStrictnessError`: inherits parent fields; leaf classes override in Step 4
  - `__reduce__` / `__setstate__` on all exception classes for pickle round-trip (ADR Promise 5)
- All `PromptCompileError` raise sites wired with `prompt_name`, `cause`, `placeholder`,
  `optimize_mode_active` structured fields.
- All `PromptRenderError` missing-key raise sites wired with `missing_key` and `context_keys`.
- `Promptstring` runtime-checkable Protocol with `placeholders`, `declared_parameters`,
  `render`, and `render_messages` (ADR 0001 Promise 2 / R3 / R9). Both `_PromptString`
  and `_PromptStringGenerator` satisfy the Protocol. Exported from the top-level package.
- `declared_parameters: Mapping[str, inspect.Parameter]` attribute on both concrete classes,
  populated at decoration time from `inspect.signature`.
- Decoration-time template parsing for docstring-sourced `@promptstring` functions
  (ADR 0001 Promises 7 and 8). Templates are now compiled in `__init__`, making
  `placeholders` available immediately without rendering.
- `PromptCompileError` is now raised at decoration time (not render time) when a
  function has no docstring and its return annotation does not prove `PromptSource`.
- Error message includes a hint about `python -OO` when `sys.flags.optimize >= 2`.
- `placeholders` property on `_PromptString` returns the eagerly-compiled placeholder
  set; `frozenset()` for dynamic-source functions (ADR 0001 non-promise 10).
- Docstrings added to all public and internal classes, methods, and functions.

### Changed
- Internal: local variable `extras` in strict-mode check renamed to `unused_params`
  (preparatory for ADR 0002's `PromptContext.extras` field).

## [0.1.0] - 2026-04-25

### Added
- Initial extraction from the femtobot project as a standalone package.
- `@promptstring` decorator with strict rendering by default.
- `@promptstring_generator` decorator for multi-message prompts.
- `PromptDepends` / `AwaitPromptDepends` dependency-injection primitives.
- `PromptContext`, `PromptMessage`, `PromptSource`, `PromptSourceProvenance`,
  `Role`.
- `PromptRenderError`, `PromptCompileError`, `PromptStrictnessError`.
