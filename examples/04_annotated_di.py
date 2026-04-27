"""Annotated DI syntax: Annotated[T, PromptDepends(...)] — primary form (ADR 0007).

Preferred over default-value form because it keeps the type annotation explicit
and works correctly with static analysis tools.

For production use, replace the lambda resolvers with real service lookups.
"""

from __future__ import annotations

import asyncio
from typing import Annotated

from promptstrings import AwaitPromptDepends, PromptContext, PromptDepends, promptstring


def get_username(ctx: PromptContext) -> str:
    return ctx.require("username")


async def get_locale(ctx: PromptContext) -> str:
    return ctx.get("locale", "en-US")


@promptstring
def personalised_prompt(
    topic: str,
    username: Annotated[str, PromptDepends(get_username)],
    locale: Annotated[str, AwaitPromptDepends(get_locale)],
) -> None:
    """Hello {username} ({locale}). Let's discuss: {topic}."""


async def main() -> None:
    ctx = PromptContext({"topic": "type safety", "username": "Ada"})
    result = await personalised_prompt.render(ctx)
    print(result)

    # Annotated dep params are equally exempt from strict unused-param checks.
    print("dep params:", personalised_prompt._dep_params)


asyncio.run(main())
