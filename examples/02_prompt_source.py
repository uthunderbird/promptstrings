"""Dynamic source: -> PromptSource, PromptSourceProvenance.

PromptSource is used when the prompt content comes from an external system
(e.g. a prompt management platform). The content is a literal passthrough —
promptstrings does not substitute placeholders inside it.

For production use, load content from Langfuse, LangSmith, or your own store
and populate PromptSourceProvenance with real version metadata.
"""

from __future__ import annotations

import asyncio

from promptstrings import (
    PromptContext,
    PromptSource,
    PromptSourceProvenance,
    promptstring,
)

provenance = PromptSourceProvenance(
    source_id="prompts.system.v2",
    version="2026-04-27",
    hash="sha256:abc123",
    provider_name="local",
)


@promptstring(strict=False)
def system_prompt(topic: str) -> PromptSource:
    # Content is assembled here, then wrapped in PromptSource.
    # promptstrings does not re-parse or substitute inside PromptSource.content.
    return PromptSource(
        content=f"You are a helpful assistant. Today's topic is {topic}.",
        provenance=provenance,
    )


async def main() -> None:
    ctx = PromptContext({"topic": "Python packaging"})

    messages = await system_prompt.render_messages(ctx)
    print("content:", messages[0].content)
    print("provenance:", messages[0].source.as_metadata() if messages[0].source else None)

    # response_schema is None for -> PromptSource (internal type)
    print("response_schema:", system_prompt.response_schema)


asyncio.run(main())
