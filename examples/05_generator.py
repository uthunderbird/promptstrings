"""Multi-turn prompts: @promptstring_generator yields one message per turn.

For production use, feed render_messages() into a multi-turn LLM conversation loop.
"""

from __future__ import annotations

import asyncio

from promptstrings import PromptContext, promptstring_generator


@promptstring_generator
def chat_thread(topic: str, user_question: str) -> None:
    yield f"You are an expert on {topic}. Answer concisely."
    yield f"user: {user_question}"


async def main() -> None:
    ctx = PromptContext({"topic": "Python packaging", "user_question": "What is a wheel?"})

    messages = await chat_thread.render_messages(ctx)
    for msg in messages:
        print(f"[{msg.role}] {msg.content}")

    # render() concatenates all turns with newlines
    full_text = await chat_thread.render(ctx)
    print("\nrender():\n", full_text)


asyncio.run(main())
