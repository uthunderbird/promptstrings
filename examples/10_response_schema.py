"""response_schema as single source of truth across multiple prompt functions.

Each @promptstring with a user-defined return type exposes response_schema.
A generic dispatch helper can route structured output without knowing the
concrete model — no repetition at the call site.

For production use, replace FakeLLMClient with instructor or litellm and pass
prompt.response_schema as response_model / response_format.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from pydantic import BaseModel
from utils.fake_llm import FakeLLMClient

from promptstrings import PromptContext, Promptstring, promptstring


class Invoice(BaseModel):
    vendor: str
    amount: float


class Sentiment(BaseModel):
    label: str
    score: float


@promptstring
def extract_invoice(text: str) -> Invoice:
    """Extract invoice data from: {text}"""


@promptstring
def analyse_sentiment(text: str) -> Sentiment:
    """Classify the sentiment of: {text}"""


async def call_llm(prompt: Promptstring, ctx: PromptContext, fake_response: object) -> object:
    """Generic helper — works for any prompt with a response_schema."""
    messages = await prompt.render_messages(ctx)
    # For production: replace FakeLLMClient with a real structured-output call, e.g.:
    #   return await real_client.chat(
    #       response_model=prompt.response_schema,
    #       messages=[{"role": m.role, "content": m.content} for m in messages],
    #   )
    client = FakeLLMClient(fake_response)
    return await client.async_chat([{"role": m.role, "content": m.content} for m in messages])


async def main() -> None:
    for prompt, ctx, fake in [
        (
            extract_invoice,
            PromptContext({"text": "Bill from Acme, $500 USD"}),
            Invoice(vendor="Acme", amount=500.0),
        ),
        (
            analyse_sentiment,
            PromptContext({"text": "I love this library!"}),
            Sentiment(label="positive", score=0.97),
        ),
    ]:
        print(f"{prompt._fn.__name__}: response_schema={prompt.response_schema}")
        result = await call_llm(prompt, ctx, fake)
        print(f"  result: {result}\n")


asyncio.run(main())
