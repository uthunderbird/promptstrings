"""Dishka integration: DishkaContext + From() for container-resolved dependencies.

From(SomeType) creates an AwaitPromptDepends resolver that reads the type
from a dishka AsyncContainer stored in the context. No manual wiring needed.

For production use, replace MockContainer with a real dishka AsyncContainer.
"""

from __future__ import annotations

import asyncio
from typing import Annotated

from promptstrings import PromptContext, promptstring
from promptstrings.integrations.dishka import DishkaContext, From


class UserService:
    def __init__(self, username: str) -> None:
        self.username = username

    def __str__(self) -> str:
        return self.username


class MockContainer:
    """Stand-in for a real dishka AsyncContainer."""

    def __init__(self) -> None:
        self._services: dict[type, object] = {
            UserService: UserService("Ada"),
        }

    async def get(self, type_: type) -> object:
        return self._services[type_]


@promptstring
def personalised_greeting(
    topic: str,
    user_service: Annotated[UserService, From(UserService)],
) -> None:
    """Hello {user_service}! Today's topic: {topic}."""


async def main() -> None:
    container = MockContainer()
    ctx = DishkaContext(values={"topic": "dependency injection"}, container=container)

    # user_service is resolved from the container; its __str__ is used in the template.
    result = await personalised_greeting.render(ctx)
    print(result)

    # DishkaContext is a PromptContext — fully compatible.
    assert isinstance(ctx, PromptContext)


asyncio.run(main())
