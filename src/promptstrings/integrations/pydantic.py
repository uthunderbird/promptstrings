from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel

from promptstrings import PromptContext


@dataclass(frozen=True)
class PydanticPromptContext(PromptContext):
    """PromptContext backed by a Pydantic v2 BaseModel.

    Requires pydantic>=2.0: pip install promptstrings[pydantic]
    Pydantic v1 is not supported.
    """

    @classmethod
    def from_model(
        cls,
        model: BaseModel,
        *,
        dump_mode: str = "python",
        extras: dict[str, Any] | None = None,
    ) -> PydanticPromptContext:
        """Populate values from model.model_dump(mode=dump_mode).

        dump_mode='python' (default): Python objects (datetime stays datetime).
        dump_mode='json': JSON-serializable types (datetime -> ISO string, etc.).
        """
        if not isinstance(model, BaseModel):
            raise TypeError(
                f"Expected a pydantic.BaseModel instance, got {type(model).__name__}"
            )
        return cls(values=model.model_dump(mode=dump_mode), extras=extras or {})
