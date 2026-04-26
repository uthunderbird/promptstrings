# Changelog

All notable changes to `promptstrings` will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-04-25

### Added
- Initial extraction from the femtobot project as a standalone package.
- `@promptstring` decorator with strict rendering by default.
- `@promptstring_generator` decorator for multi-message prompts.
- `PromptDepends` / `AwaitPromptDepends` dependency-injection primitives.
- `PromptContext`, `PromptMessage`, `PromptSource`, `PromptSourceProvenance`,
  `Role`.
- `PromptRenderError`, `PromptCompileError`, `PromptStrictnessError`.
