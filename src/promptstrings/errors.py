"""The exception hierarchy and its field schema (ADR 0003)."""

from __future__ import annotations

from typing import Any, Literal


class PromptRenderError(RuntimeError):
    """Base class for all prompt render-time failures (ADR 0003).

    Named attributes are JSON-safe and picklable. Use to_dict() for structured
    access from agents and tooling.
    """

    missing_key: str | None
    """Parameter name that could not be resolved; None for non-missing-key failures."""

    context_keys: tuple[str, ...] | None
    """Keys present in PromptContext.values at error time; None when context unavailable."""

    def __init__(
        self,
        message: str,
        *,
        missing_key: str | None = None,
        context_keys: tuple[str, ...] | None = None,
    ) -> None:
        """Initialise with optional structured fields."""
        super().__init__(message)
        self.missing_key = missing_key
        self.context_keys = context_keys

    def __reduce__(self) -> tuple[Any, ...]:
        """Support pickle round-trip for all named attributes."""
        return (
            self.__class__,
            (str(self),),
            {"missing_key": self.missing_key, "context_keys": self.context_keys},
        )

    def __setstate__(self, state: dict[str, Any] | None) -> None:
        """Restore named attributes after unpickling."""
        if state:
            for k, v in state.items():
                setattr(self, k, v)

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-safe dict representation (ADR 0003 rules R-A through R-E)."""
        return {
            "type": type(self).__name__,
            "message": str(self),
            "missing_key": self.missing_key,
            "context_keys": list(self.context_keys) if self.context_keys is not None else None,
        }

class PromptCompileError(PromptRenderError):
    """Raised at decoration time when a template cannot be compiled (ADR 0003).

    prompt_name, cause, placeholder, and optimize_mode_active identify the
    specific compile-time failure. missing_key and context_keys are always None.
    """

    prompt_name: str
    """__name__ of the decorated function; always set."""

    cause: Literal["missing_template", "format_spec", "conversion", "non_identifier_placeholder", "mixed_source_mode"]
    """Discriminator for which compile-time check failed."""

    placeholder: str | None
    """Offending placeholder text; None for cause='missing_template'."""

    optimize_mode_active: bool
    """True iff sys.flags.optimize >= 2 at decoration time."""

    def __init__(
        self,
        message: str,
        *,
        prompt_name: str = "<unknown>",
        cause: Literal[
            "missing_template", "format_spec", "conversion", "non_identifier_placeholder", "mixed_source_mode"
        ] = "missing_template",
        placeholder: str | None = None,
        optimize_mode_active: bool = False,
    ) -> None:
        """Initialise with compile-time error fields; missing_key/context_keys are always None."""
        super().__init__(message, missing_key=None, context_keys=None)
        self.prompt_name = prompt_name
        self.cause = cause
        self.placeholder = placeholder
        self.optimize_mode_active = optimize_mode_active

    def __reduce__(self) -> tuple[Any, ...]:
        """Support pickle round-trip for all named attributes."""
        return (
            self.__class__,
            (str(self),),
            {
                "prompt_name": self.prompt_name,
                "cause": self.cause,
                "placeholder": self.placeholder,
                "optimize_mode_active": self.optimize_mode_active,
            },
        )

    def __setstate__(self, state: dict[str, Any] | None) -> None:
        """Restore named attributes after unpickling."""
        # Parent fields default to None for compile errors.
        self.missing_key = None
        self.context_keys = None
        if state:
            for k, v in state.items():
                setattr(self, k, v)

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-safe dict representation (ADR 0003 rules R-A through R-E)."""
        return {
            "type": type(self).__name__,
            "message": str(self),
            "prompt_name": self.prompt_name,
            "cause": self.cause,
            "placeholder": self.placeholder,
            "optimize_mode_active": self.optimize_mode_active,
            "missing_key": None,
            "context_keys": None,
        }

class PromptStrictnessError(PromptRenderError):
    """Parent class for strict-mode failures; never raised directly by library code.

    Catch this class to handle both PromptUnusedParameterError (template path)
    and PromptUnreferencedParameterError (generator path) uniformly.
    to_dict() is inherited from PromptRenderError; leaf classes override it.
    """

    pass

class PromptUnusedParameterError(PromptStrictnessError):
    """Raised by @promptstring when a resolved parameter is not in the template (ADR 0001 P3).

    Fix: remove the parameter from the function signature, or add a {name} placeholder.
    """

    unused_parameters: tuple[str, ...]
    """Names of parameters that were resolved but not consumed by the template."""

    resolved_keys: tuple[str, ...]
    """All parameter names that were resolved at render time."""

    def __init__(
        self,
        message: str,
        *,
        unused_parameters: tuple[str, ...] = (),
        resolved_keys: tuple[str, ...] = (),
    ) -> None:
        """Initialise with the set of unused and all resolved parameter names."""
        super().__init__(message)
        self.unused_parameters = unused_parameters
        self.resolved_keys = resolved_keys

    def __reduce__(self) -> tuple[Any, ...]:
        """Support pickle round-trip."""
        return (
            self.__class__,
            (str(self),),
            {
                "unused_parameters": self.unused_parameters,
                "resolved_keys": self.resolved_keys,
            },
        )

    def __setstate__(self, state: dict[str, Any] | None) -> None:
        """Restore named attributes after unpickling."""
        self.missing_key = None
        self.context_keys = None
        if state:
            for k, v in state.items():
                setattr(self, k, v)

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-safe dict representation (ADR 0003 rules R-A through R-E)."""
        return {
            "type": type(self).__name__,
            "message": str(self),
            "unused_parameters": list(self.unused_parameters),
            "resolved_keys": list(self.resolved_keys),
            "missing_key": None,
            "context_keys": None,
        }

class PromptUnreferencedParameterError(PromptStrictnessError):
    """Raised by @promptstring_generator (strict=True) when a parameter value is not in output.

    Fix: yield a string containing the parameter's str() value, or remove the parameter.
    Note: the detection is best-effort (substring heuristic); see ADR 0004.
    """

    unreferenced_parameters: tuple[str, ...]
    """Names of parameters whose str() value was not found in the rendered output."""

    resolved_keys: tuple[str, ...]
    """All parameter names that were resolved at render time."""

    def __init__(
        self,
        message: str,
        *,
        unreferenced_parameters: tuple[str, ...] = (),
        resolved_keys: tuple[str, ...] = (),
    ) -> None:
        """Initialise with the set of unreferenced and all resolved parameter names."""
        super().__init__(message)
        self.unreferenced_parameters = unreferenced_parameters
        self.resolved_keys = resolved_keys

    def __reduce__(self) -> tuple[Any, ...]:
        """Support pickle round-trip."""
        return (
            self.__class__,
            (str(self),),
            {
                "unreferenced_parameters": self.unreferenced_parameters,
                "resolved_keys": self.resolved_keys,
            },
        )

    def __setstate__(self, state: dict[str, Any] | None) -> None:
        """Restore named attributes after unpickling."""
        self.missing_key = None
        self.context_keys = None
        if state:
            for k, v in state.items():
                setattr(self, k, v)

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-safe dict representation (ADR 0003 rules R-A through R-E)."""
        return {
            "type": type(self).__name__,
            "message": str(self),
            "unreferenced_parameters": list(self.unreferenced_parameters),
            "resolved_keys": list(self.resolved_keys),
            "missing_key": None,
            "context_keys": None,
        }
