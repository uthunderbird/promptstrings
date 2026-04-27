"""FastAPI integration: promptstring inside a request handler.

Shows the idiomatic pattern: FastAPI Depends() provides request-scoped values,
PromptContext is built from them, render_messages() produces the LLM payload.
response_schema is passed directly to the (fake) LLM client — no repetition.

For production use, replace FakeLLMClient with your real LLM client and
run with: uvicorn 11_fastapi_endpoint:app
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel
from utils.fake_llm import FakeLLMClient

from promptstrings import PromptContext, promptstring

app = FastAPI()


# --- Domain models -----------------------------------------------------------

class SentimentRequest(BaseModel):
    text: str


class SentimentResult(BaseModel):
    label: str
    score: float


# --- Prompt ------------------------------------------------------------------

@promptstring
def sentiment_prompt(text: str) -> SentimentResult:
    """Classify the sentiment of the following text: {text}"""


# --- FastAPI dependencies ----------------------------------------------------

def get_llm_client() -> FakeLLMClient:
    # For production: return your real LLM client here (e.g. instructor-wrapped openai).
    return FakeLLMClient(SentimentResult(label="positive", score=0.95))


# --- Endpoint ----------------------------------------------------------------

@app.post("/sentiment", response_model=SentimentResult)
async def analyse_sentiment(
    request: SentimentRequest,
    client: FakeLLMClient = Depends(get_llm_client),
) -> SentimentResult:
    ctx = PromptContext({"text": request.text})
    messages = await sentiment_prompt.render_messages(ctx)

    # response_schema carries SentimentResult — no need to repeat it here.
    # For production: result = await real_client.chat(
    #     response_model=sentiment_prompt.response_schema,
    #     messages=[{"role": m.role, "content": m.content} for m in messages],
    # )
    result = await client.async_chat(
        [{"role": m.role, "content": m.content} for m in messages]
    )
    return result


# --- Demo (run without uvicorn) ----------------------------------------------

def main() -> None:
    with TestClient(app) as client:
        response = client.post("/sentiment", json={"text": "I love this library!"})
        print("status:", response.status_code)
        print("response:", response.json())
        assert response.status_code == 200
        assert response.json()["label"] == "positive"

    print("prompt name:", sentiment_prompt._fn.__name__)
    print("response_schema:", sentiment_prompt.response_schema)
    print("placeholders:", sentiment_prompt.placeholders)


if __name__ == "__main__":
    main()
