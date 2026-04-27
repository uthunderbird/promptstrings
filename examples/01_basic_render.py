"""Basic rendering: @promptstring, PromptContext, render() and render_messages().

For production use, pass a real PromptContext populated from your application state.
"""

from __future__ import annotations

import asyncio

from promptstrings import PromptContext, PromptMessage, promptstring


@promptstring
def greet(name: str, language: str) -> None:
    """You are a helpful assistant. Greet the user named {name} in {language}."""


async def main() -> None:
    ctx = PromptContext({"name": "Ada", "language": "English"})

    # render() returns the rendered string directly
    text = await greet.render(ctx)
    print("render():", text)

    # render_messages() returns a list of PromptMessage for passing to an LLM
    messages = await greet.render_messages(ctx)
    print("render_messages():", messages)
    assert messages == [PromptMessage(role="system", content=text)]

    # placeholders are known at decoration time
    print("placeholders:", greet.placeholders)


asyncio.run(main())
