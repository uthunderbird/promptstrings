"""Reading a decorated function's signature, type hints, and Annotated markers."""

from __future__ import annotations

from collections.abc import Callable
from string.templatelib import Template
from typing import Annotated, Any, get_args, get_origin, get_type_hints

from .types import PromptSource


def _get_param_type_hints(fn: Callable[..., Any]) -> dict[str, Any]:
    """Return get_type_hints for fn, with best-effort return annotation resolution.

    Under PEP 563 (from __future__ import annotations), annotations are strings.
    get_type_hints resolves them against fn.__globals__. Local types (defined inside
    a function body) are absent from globals and cause NameError.

    Strategy:
    1. Try the full dict (fast path — works when all types are importable globals).
    2. On failure, resolve params-only (strip return). If that fails, NameError is
       from a param annotation — re-raise immediately (ADR 0007 D1 fail-fast).
    3. Attempt to resolve the return annotation separately using eval against
       fn.__globals__. On success, merge it back. On failure, use the raw annotation
       value (string or actual type) — _response_schema_from_hints handles both.
    """
    try:
        return get_type_hints(fn, include_extras=True)
    except (NameError, AttributeError):
        pass

    orig = fn.__annotations__
    fn.__annotations__ = {k: v for k, v in orig.items() if k != "return"}
    try:
        hints = get_type_hints(fn, include_extras=True)
    except (NameError, AttributeError):
        raise
    finally:
        fn.__annotations__ = orig

    # Attempt to resolve the return annotation separately.
    raw_return = orig.get("return")
    if raw_return is not None:
        if isinstance(raw_return, str):
            try:
                hints["return"] = eval(raw_return, fn.__globals__)  # noqa: S307
            except Exception:
                hints["return"] = raw_return
        else:
            hints["return"] = raw_return

    return hints

def _annotated_markers(hint: Any) -> list[Any]:
    """Return Annotated metadata items for a hint, or [] if not Annotated."""
    if get_origin(hint) is Annotated:
        return list(get_args(hint)[1:])
    return []

_INTERNAL_RETURN_TYPES: tuple[Any, ...] = (type(None), type(...))

def _response_schema_from_hints(hints: dict[str, Any]) -> Any:
    """Extract response_schema from resolved type hints (ADR 0009).

    Returns the raw return annotation for user-defined types (e.g. MyModel,
    list[MyModel]). Returns None for promptstrings-internal return types:
    NoneType, Ellipsis, str, Template, PromptSource.
    """
    ret = hints.get("return")
    if ret is None or ret is ...:
        return None
    if ret is type(None) or ret is type(...):
        return None
    if ret is str or ret is Template or ret is PromptSource:
        return None
    return ret

def _has_dynamic_return_annotation(fn: Callable[..., Any]) -> bool:
    """Return True if fn's return annotation proves it returns PromptSource or Template dynamically.

    Checks both the raw __annotations__ entry (for non-PEP-563 code) and a
    best-effort resolved form (for PEP-563 / from __future__ import annotations
    code where annotations are strings).
    """
    try:
        raw = fn.__annotations__
    except AttributeError:
        return False

    return_hint = raw.get("return")
    if return_hint is None or return_hint is ... or return_hint == "...":
        return False

    # Fast path: annotation is already the class (no PEP 563)
    if return_hint is PromptSource or return_hint is Template:
        return True

    # Slow path: annotation is a string (PEP 563) — resolve against fn globals
    if isinstance(return_hint, str):
        try:
            resolved = eval(return_hint, fn.__globals__)  # noqa: S307
            return resolved is PromptSource or resolved is Template
        except Exception:
            # Common string aliases used in docstrings / tests
            return return_hint in ("PromptSource", "Template")

    return False
