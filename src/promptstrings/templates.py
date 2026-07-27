"""The owned-prompt grammar: parsing, placeholder extraction, compilation, and the two render functions."""

from __future__ import annotations

import sys
import textwrap
from collections.abc import Callable
from string import Formatter
from string.templatelib import Interpolation, Template
from typing import Any

from .errors import PromptCompileError, PromptRenderError
from .introspection import _has_dynamic_return_annotation
from .types import _PromptObject

_MISSING: object = object()

def _parse_docstring(source: str, *, prompt_name: str = "<unknown>") -> Template:
    """Parse a docstring template string into a stdlib Template (ADR 0005).

    Uses string.Formatter to parse the docstring, applies all grammar guards
    (no format specs, no conversions, identifier-only placeholders), then
    constructs a Template with _MISSING sentinels as Interpolation values.

    Raises PromptCompileError for unsupported grammar.
    """
    formatter = Formatter()
    args: list[str | Interpolation] = []
    for literal, field_name, format_spec, conversion in formatter.parse(source):
        if literal:
            args.append(literal)
        if field_name is None:
            continue
        if format_spec:
            raise PromptCompileError(
                f"Format specs are not supported in promptstrings (prompt: {prompt_name!r})",
                prompt_name=prompt_name,
                cause="format_spec",
                placeholder=field_name,
                optimize_mode_active=sys.flags.optimize >= 2,
            )
        if conversion:
            raise PromptCompileError(
                f"Conversions are not supported in promptstrings (prompt: {prompt_name!r})",
                prompt_name=prompt_name,
                cause="conversion",
                placeholder=field_name,
                optimize_mode_active=sys.flags.optimize >= 2,
            )
        if not field_name.isidentifier():
            raise PromptCompileError(
                f"Promptstring placeholders must use the minimal {{identifier}} grammar "
                f"(got {field_name!r}, prompt: {prompt_name!r})",
                prompt_name=prompt_name,
                cause="non_identifier_placeholder",
                placeholder=field_name,
                optimize_mode_active=sys.flags.optimize >= 2,
            )
        args.append(Interpolation(_MISSING, field_name))
    return Template(*args) if args else Template("")

def _placeholders_from_template(tpl: Template) -> frozenset[str]:
    """Extract placeholder names from a docstring-derived Template."""
    return frozenset(i.expression for i in tpl.interpolations)

def _is_unrendered_prompt(value: Any) -> bool:
    """Return True if value is one of this library's own prompt objects (ADR 0011 D3).

    Deliberately narrowed to the concrete internal classes rather than the
    ``Promptstring`` Protocol: the Protocol is the documented extension surface
    (ADR 0001 Promise 2), so a third-party implementation may define a
    meaningful ``__str__`` and legitimately substitute as a string. Only our own
    objects are known to have no valid rendered form.
    """
    return isinstance(value, _PromptObject)

def _render_static(tpl: Template, resolved: dict[str, Any]) -> str:
    """Render a docstring-derived Template using expression→resolved lookup."""
    parts: list[str] = []
    for item in tpl:
        if isinstance(item, str):
            parts.append(item)
        else:
            try:
                value = resolved[item.expression]
            except KeyError:
                raise PromptRenderError(
                    f"Template expression {item.expression!r} has no matching resolved parameter",
                    missing_key=item.expression,
                )
            if _is_unrendered_prompt(value):
                raise PromptRenderError(
                    f"Parameter {item.expression!r} is an unrendered promptstring — "
                    f"did you forget `await {item.expression}.render(ctx)`?",
                    missing_key=None,
                )
            parts.append(str(value))
    return "".join(parts)

def parse_trusted_template(source: str, *, prompt_name: str = "<unknown>") -> Template:
    """Parse a **trusted** template string into a stdlib Template.

    The name signals the security contract: only pass strings whose content
    you control. Do not pass user-supplied input — placeholder expressions
    in the returned Template are substituted from resolved parameters at render
    time, so a user-controlled ``{param_name}`` would be silently replaced with
    the parameter's value.

    Applies the same grammar guards as docstring templates: identifier-only
    placeholders, no format specs, no conversions. Raises ``PromptCompileError``
    for invalid grammar.

    Typical use: loading prompt templates from a version-controlled database or
    config system. Return the result from a function annotated ``-> Template``::

        @promptstring
        def system(topic: str) -> Template:
            template_str = db.get("system_prompt")  # trusted source
            return parse_trusted_template(template_str)
    """
    return _parse_docstring(source, prompt_name=prompt_name)

def _render_dynamic(tpl: Template) -> str:
    """Render a t-string-derived Template using already-resolved Interpolation values."""
    parts: list[str] = []
    for item in tpl:
        if isinstance(item, str):
            parts.append(item)
        else:
            if _is_unrendered_prompt(item.value):
                raise PromptRenderError(
                    "A t-string interpolation evaluated to an unrendered promptstring — "
                    "did you forget `await prompt.render(ctx)`?",
                    missing_key=None,
                )
            parts.append(str(item.value))
    return "".join(parts)

def _compile_at_decoration(
    fn: Callable[..., Any],
    prompt_name: str,
) -> Template | None:
    """Attempt to compile a template at decoration time (ADR 0005).

    Returns a Template when the function has a docstring-based template.
    Returns None when the function is dynamic-source (PromptSource or Template annotation).
    Raises PromptCompileError immediately when neither condition holds.
    """
    docstring = getattr(fn, "__doc__", None)
    if docstring:
        # Guard: docstring + dynamic return annotation = mixed source mode (ADR 0006 D2).
        if _has_dynamic_return_annotation(fn):
            raise PromptCompileError(
                f"Promptstring {prompt_name!r} has both a docstring template and a dynamic "
                f"return annotation; use one or the other.",
                prompt_name=prompt_name,
                cause="mixed_source_mode",
                placeholder=None,
                optimize_mode_active=sys.flags.optimize >= 2,
            )
        normalized = textwrap.dedent(docstring).strip()
        return _parse_docstring(normalized, prompt_name=prompt_name)

    # No docstring — check if the function proves it returns a dynamic source.
    if _has_dynamic_return_annotation(fn):
        # Dynamic source: placeholders cannot be known until render time.
        return None

    # Neither docstring nor dynamic annotation: fail immediately.
    optimize_active = sys.flags.optimize >= 2
    optimize_note = " (docstrings are stripped by python -OO; run without -OO)" if optimize_active else ""
    raise PromptCompileError(
        f"Promptstring {prompt_name!r} has no docstring and its return annotation does not "
        f"prove a PromptSource or Template is returned.{optimize_note}",
        prompt_name=prompt_name,
        cause="missing_template",
        placeholder=None,
        optimize_mode_active=optimize_active,
    )
