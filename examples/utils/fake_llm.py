"""Deterministic LLM client for running examples without a real API key.

To use a real LLM, replace FakeLLMClient with your actual client.
"""

from __future__ import annotations

from typing import Any


class FakeLLMClient:
    """OpenAI-compatible stub that returns a fixed response regardless of input.

    Synchronous: client.chat(messages)
    Asynchronous: await client.async_chat(messages)
    """

    def __init__(self, response: Any) -> None:
        self._response = response

    def chat(self, messages: list[dict[str, str]]) -> Any:
        return self._response

    async def async_chat(self, messages: list[dict[str, str]]) -> Any:
        return self._response
