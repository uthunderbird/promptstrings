"""Observer: render-event tracing via Promptstrings config + Observer protocol.

Observer.on_render_start / on_render_end / on_render_error fire on every render call.
Use this for logging, metrics, or prompt-management system integration.

For production use, replace PrintObserver with a real OTel span or structured logger.
"""

from __future__ import annotations

import asyncio

from promptstrings import (
    PromptContext,
    PromptRenderError,
    Promptstrings,
    RenderEndEvent,
    RenderErrorEvent,
    RenderStartEvent,
)


class PrintObserver:
    """Logs all render events to stdout."""

    def on_render_start(self, event: RenderStartEvent) -> None:
        print(f"[start] prompt={event.prompt_name!r} placeholders={event.placeholders}")

    def on_render_end(self, event: RenderEndEvent) -> None:
        elapsed_ms = event.elapsed_ns / 1_000_000
        print(f"[end]   prompt={event.prompt_name!r} messages={event.message_count} elapsed={elapsed_ms:.1f}ms")

    def on_render_error(self, event: RenderErrorEvent) -> None:
        print(f"[error] prompt={event.prompt_name!r} error={event.error!r}")


# Wire the observer into a Promptstrings instance.
ps = Promptstrings(observer=PrintObserver())


@ps.promptstring
def summarise(text: str) -> None:
    """Summarise the following: {text}"""


async def main() -> None:
    ctx = PromptContext({"text": "Python is a high-level programming language."})
    result = await summarise.render(ctx)
    print("result:", result)

    # Observer also fires on errors — try rendering with a missing key.
    try:
        await summarise.render(PromptContext())
    except PromptRenderError as exc:
        print("caught expected error:", exc)


asyncio.run(main())
