# Changelog

All notable changes to `promptstrings` will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

> **Note on 1.0.0–1.2.0.** Those three releases shipped without changelog entries. Their sections
> below were reconstructed from git history in 1.3.0, using the commit ranges between the release
> tags, and their dates are the tag dates. The CHANGELOG bundled inside the 1.0.0/1.1.0/1.2.0
> artifacts on PyPI is the original, incomplete one — those artifacts are immutable and were not
> republished.

## [Unreleased]

### Changed
- `core.py` is split into nine modules (ADR 0012): `errors`, `types`, `observability`,
  `introspection`, `templates`, `resolution`, `prompts`, `generators`, `factory`. **No public
  API change** — every name still imports from `promptstrings`, the split removed nothing from
  `promptstrings.__all__`, and `promptstrings.core` remains as a shim re-exporting all 43
  pre-split names. (`provenance_from_file` below is an addition by a separate decision, not by
  the split.)
  - Two caveats that are real but narrow. Re-export does not preserve monkeypatch targets:
    `monkeypatch.setattr("promptstrings.core._render_static", ...)` no longer affects
    rendering, because the library resolves that name in `promptstrings.templates`. And
    pickles embed the defining module, so objects pickled after this change cannot be loaded
    by 1.0.0–1.2.0.
  - `promptstrings.core` no longer exposes the modules it happened to import
    (`promptstrings.core.asyncio` and similar). That was incidental attribute leakage rather
    than API.
- A `@promptstring_generator` that yields a `PromptSource` now raises an error saying delegated
  rendering is unsupported on that engine and what to do instead, rather than reporting an
  unsupported yield type. The capability was never available; only the message changes.

### Added
- `provenance_from_file(path, *, source_id=None, version=None, provider_name=None)` (ADR 0012
  D4) — derives a `PromptSourceProvenance` from a template file: the path as identity and a
  `sha256:`-prefixed hash of its raw bytes. Provenance is carried only by prompts returning a
  `PromptSource`, which is also where the template tends to live in a file, so this removes the
  hand-written boilerplate that was causing provenance to be dropped.
  - `source_id` defaults to the given path in POSIX form and is never resolved to an absolute
    path; pass it explicitly when locating templates from `__file__`, so the recorded identity
    stays repository-relative rather than machine-specific.
  - The hash is byte-exact with no newline normalisation, so a CRLF checkout hashes
    differently — normalising would hide a real difference in what was sent to the model.
  - `version` is never assigned by the library.
- README section "Three kinds of prompt, three sets of guarantees" and
  `examples/13_prompt_classes.py`, documenting that a docstring, a `-> Template` return, and a
  `-> PromptSource` return carry different guarantees (ADR 0012 D2). Two consequences are
  stated explicitly for the first time: strictness and provenance are mutually exclusive per
  prompt, and `response_schema` is available only on the docstring path.
- `tools/split_gate.py` and a captured pre-split baseline, so the split's acceptance gates are
  re-runnable rather than a one-off claim.

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
- CI: an `examples` job runs every `examples/[0-9]*.py`, so the examples cannot rot. `build` (and
  therefore `publish`) now depends on it, so a broken example blocks a release.
- CI: a top-level `permissions: contents: read`, so jobs no longer inherit the repository's
  default token scope.
- README: a "Structured output" section documenting `response_schema` (shipped in 1.2.0,
  previously undocumented).
- `@promptstring` / `@promptstring_generator` objects now have a self-describing `__repr__` —
  `<unrendered promptstring 'name'>` instead of `<promptstrings.core._PromptString object at
  0x...>` (ADR 0011, D5). This covers the nested case the D3 guard cannot reach: containers
  format their elements with `repr()`, so a prompt object inside a list, dict, tuple, dataclass,
  or any depth of nesting previously rendered an opaque address into the prompt.
  - **The composition guarantee is two-tier.** A prompt object passed *as* a parameter value
    raises `PromptRenderError` (D3). A prompt object *nested inside* a structure does **not**
    raise — it renders as `<unrendered promptstring 'name'>`. Nested cases are named, not
    rejected.
  - Coverage follows from the object describing itself, so it requires no list of container
    types and adds no cost to the render path.
  - `str(prompt_object)` still works (Python falls back to `__repr__`), preserving the D3
    debugging carve-out. Not a compatibility event: the previous repr embedded a memory
    address and so could never be asserted on stably.

### Fixed
- README: the dishka example did not compile. It used `{user.name}` as a placeholder, which the
  `{identifier}`-only grammar rejects with `PromptCompileError`. It now resolves the attribute in
  the resolver and interpolates a plain `{username}`.
- README: the observer example defined `on_event`, which is not part of the `Observer` protocol
  (`on_render_start` / `on_render_end` / `on_render_error`). An observer copied from the README
  silently never fired. Both examples had been wrong since 1.0.0.

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
