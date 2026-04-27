from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from dishka import AsyncContainer

from promptstrings import AwaitPromptDepends, PromptContext

_CONTAINER_KEY = "_promptstrings_dishka_container"


@dataclass(frozen=True)
class DishkaContext(PromptContext):
    """PromptContext carrying a dishka AsyncContainer.

    Use From(SomeType) in Annotated markers to resolve from the container.
    Requires dishka to be installed: pip install promptstrings[dishka]
    """

    container: AsyncContainer | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "extras", {**self.extras, _CONTAINER_KEY: self.container})


def From[T](type_: type[T]) -> AwaitPromptDepends:
    """Resolve a parameter from the active dishka AsyncContainer.

    Usage: user: Annotated[User, From(User)]
    Requires DishkaContext as the render context; raises KeyError otherwise.
    """

    async def resolver(ctx: PromptContext) -> Any:
        container: AsyncContainer = ctx.extras[_CONTAINER_KEY]
        return await container.get(type_)

    return AwaitPromptDepends(resolver)
