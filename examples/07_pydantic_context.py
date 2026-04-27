"""PydanticPromptContext: populate context from a Pydantic model (ADR 0007).

Eliminates the manual dict construction when your application data is already
in a Pydantic model. dump_mode='python' keeps Python objects; 'json' serialises
them (datetime → ISO string, etc.).

For production use, pass your real request/session model to from_model().
"""

from __future__ import annotations

import asyncio
from datetime import datetime

from pydantic import BaseModel

from promptstrings import PromptContext, promptstring
from promptstrings.integrations.pydantic import PydanticPromptContext


class ReportRequest(BaseModel):
    author: str
    topic: str
    deadline: datetime


@promptstring
def report_prompt(author: str, topic: str, deadline: str) -> None:
    """Write a report on {topic} for {author}. Deadline: {deadline}."""


async def main() -> None:
    request = ReportRequest(
        author="Ada",
        topic="async Python patterns",
        deadline=datetime(2026, 5, 1),
    )

    # dump_mode='json' serialises datetime → ISO string so it fits the {deadline} placeholder.
    ctx = PydanticPromptContext.from_model(request, dump_mode="json")
    print("context values:", ctx.values)

    result = await report_prompt.render(ctx)
    print(result)

    # PydanticPromptContext is a PromptContext — works everywhere a PromptContext does.
    assert isinstance(ctx, PromptContext)


asyncio.run(main())
