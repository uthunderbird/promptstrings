"""Structured output: -> MyModel + response_schema + instructor-style call.

response_schema exposes the return annotation so it can be passed directly to
instructor, litellm, or any other structured-output framework without repetition.

For production use, replace FakeLLMClient with your real LLM client.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from pydantic import BaseModel
from utils.fake_llm import FakeLLMClient

from promptstrings import PromptContext, promptstring


class Invoice(BaseModel):
    vendor: str
    amount: float
    currency: str


@promptstring
def extract_invoice(text: str) -> Invoice:
    """Extract invoice data from the following text: {text}"""


async def main() -> None:
    ctx = PromptContext({"text": "Invoice from Acme Corp, $1,250.00 USD"})
    messages = await extract_invoice.render_messages(ctx)

    # response_schema is the single source of truth — no need to repeat Invoice here.
    # For production: replace FakeLLMClient with instructor or litellm, e.g.:
    #   result = client.chat.completions.create(
    #       response_model=extract_invoice.response_schema,
    #       messages=[m.__dict__ for m in messages],
    #   )
    fake_response = Invoice(vendor="Acme Corp", amount=1250.0, currency="USD")
    client = FakeLLMClient(fake_response)
    result = await client.async_chat([{"role": m.role, "content": m.content} for m in messages])

    print("response_schema:", extract_invoice.response_schema)
    print("result:", result)
    assert result.vendor == "Acme Corp"


asyncio.run(main())
