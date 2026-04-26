# Changelog

All notable changes to `promptstrings` will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
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
