"""Dependency injection: PromptDepends resolves parameters from context or side-effects.

Default-value form is the original DI syntax (silently deprecated in favour of
Annotated form — see 04_annotated_di.py). Shown here for completeness.

For production use, replace the lambda resolvers with real service lookups.
"""

from __future__ import annotations

import asyncio

from promptstrings import AwaitPromptDepends, PromptContext, PromptDepends, promptstring


def get_username(ctx: PromptContext) -> str:
    # In production: look up the authenticated user from ctx.extras or a service.
    return ctx.require("username")


async def get_locale(ctx: PromptContext) -> str:
    # In production: await a real async service call.
    return ctx.get("locale", "en-US")


@promptstring
def personalised_prompt(
    topic: str,
    username=PromptDepends(get_username),
    locale=AwaitPromptDepends(get_locale),
) -> None:
    """Hello {username} ({locale}). Let's discuss: {topic}."""


async def main() -> None:
    ctx = PromptContext({"topic": "type safety", "username": "Ada"})
    result = await personalised_prompt.render(ctx)
    print(result)

    # PromptDepends parameters are exempt from strict unused-param checks —
    # they may be resolved purely for side-effects (logging, caching, etc.).
    print("dep params (exempt from strict):", personalised_prompt._dep_params)


asyncio.run(main())
