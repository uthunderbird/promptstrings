"""Backwards-compatible re-export of the pre-split `core` surface.

Every top-level name that lived in this module before the ADR 0012 split is
re-exported here. `__all__` is explicit because `mypy strict` implies
`no_implicit_reexport` and `ruff` would otherwise flag the imports as unused.

Re-export does not preserve monkeypatch targets: patching
`promptstrings.core._render_static` no longer affects rendering, because the
library resolves that name in `templates`. Patch the defining module instead.
"""

from __future__ import annotations

from .errors import (
    PromptCompileError,
    PromptRenderError,
    PromptStrictnessError,
    PromptUnreferencedParameterError,
    PromptUnusedParameterError,
)
from .factory import Promptstrings, _default, promptstring, promptstring_generator
from .generators import _PromptStringGenerator, _strict_heuristic_logger
from .introspection import (
    _INTERNAL_RETURN_TYPES,
    _annotated_markers,
    _get_param_type_hints,
    _has_dynamic_return_annotation,
    _response_schema_from_hints,
)
from .observability import (
    Observer,
    RenderEndEvent,
    RenderErrorEvent,
    RenderStartEvent,
    _fire_observer,
    _NoOpObserver,
    _observer_logger,
)
from .prompts import _PromptString
from .resolution import _maybe_await, _resolve_dependencies
from .templates import (
    _MISSING,
    _compile_at_decoration,
    _is_unrendered_prompt,
    _parse_docstring,
    _placeholders_from_template,
    _render_dynamic,
    _render_static,
    parse_trusted_template,
)
from .types import (
    AwaitPromptDepends,
    PromptContext,
    PromptDepends,
    PromptMessage,
    PromptSource,
    PromptSourceProvenance,
    Promptstring,
    Resolver,
    Role,
)

__all__ = [
    "AwaitPromptDepends",
    "Observer",
    "PromptCompileError",
    "PromptContext",
    "PromptDepends",
    "PromptMessage",
    "PromptRenderError",
    "PromptSource",
    "PromptSourceProvenance",
    "PromptStrictnessError",
    "PromptUnreferencedParameterError",
    "PromptUnusedParameterError",
    "Promptstring",
    "Promptstrings",
    "RenderEndEvent",
    "RenderErrorEvent",
    "RenderStartEvent",
    "Resolver",
    "Role",
    "_INTERNAL_RETURN_TYPES",
    "_MISSING",
    "_NoOpObserver",
    "_PromptString",
    "_PromptStringGenerator",
    "_annotated_markers",
    "_compile_at_decoration",
    "_default",
    "_fire_observer",
    "_get_param_type_hints",
    "_has_dynamic_return_annotation",
    "_is_unrendered_prompt",
    "_maybe_await",
    "_observer_logger",
    "_parse_docstring",
    "_placeholders_from_template",
    "_render_dynamic",
    "_render_static",
    "_resolve_dependencies",
    "_response_schema_from_hints",
    "_strict_heuristic_logger",
    "parse_trusted_template",
    "promptstring",
    "promptstring_generator",
]
