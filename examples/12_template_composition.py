"""Template composition: using one promptstring's output as input to another.

Two patterns are shown:
1. Direct — await inner.render(ctx) and pass the string as a parameter.
2. DI — AwaitPromptDepends resolver renders inner automatically.

The second-parse injection guarantee: a rendered string containing {braces}
is never re-parsed as a template. Values are substituted once and frozen.

For production use, both patterns are safe. Prefer the DI pattern when the
inner prompt's parameters are available in the shared PromptContext.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Annotated

sys.path.insert(0, str(Path(__file__).parent))

from promptstrings import (
    AwaitPromptDepends,
    PromptContext,
    PromptRenderError,
    promptstring,
)

# --- Inner prompts -----------------------------------------------------------

@promptstring
def system_prompt(role: str, domain: str) -> None:
    """You are a {role} specialising in {domain}."""


@promptstring
def few_shot_examples(domain: str) -> None:
    """Here are two examples of {domain} questions and answers."""


# --- Pattern 1: direct composition -------------------------------------------

@promptstring(strict=False)
def full_prompt_direct(system: str, examples: str, question: str) -> None:
    """System: {system}

Examples: {examples}

Question: {question}"""


async def pattern_direct() -> None:
    ctx = PromptContext({"role": "tutor", "domain": "Python", "question": "What is a generator?"})

    system_text = await system_prompt.render(ctx)
    examples_text = await few_shot_examples.render(ctx)

    result = await full_prompt_direct.render(
        PromptContext({"system": system_text, "examples": examples_text, "question": ctx.require("question")})
    )
    print("=== Pattern 1: direct ===")
    print(result)
    print()


# --- Pattern 2: DI composition -----------------------------------------------

def make_system_resolver(role: str, domain: str) -> AwaitPromptDepends:
    async def resolver(ctx: PromptContext) -> str:
        return await system_prompt.render(PromptContext({"role": role, "domain": domain}))
    return AwaitPromptDepends(resolver)


def make_examples_resolver(domain: str) -> AwaitPromptDepends:
    async def resolver(ctx: PromptContext) -> str:
        return await few_shot_examples.render(PromptContext({"domain": domain}))
    return AwaitPromptDepends(resolver)


@promptstring(strict=False)
def full_prompt_di(
    system: Annotated[str, make_system_resolver("tutor", "Python")],
    examples: Annotated[str, make_examples_resolver("Python")],
    question: str,
) -> None:
    """System: {system}

Examples: {examples}

Question: {question}"""


async def pattern_di() -> None:
    ctx = PromptContext({"question": "What is a generator?"})
    result = await full_prompt_di.render(ctx)
    print("=== Pattern 2: DI ===")
    print(result)
    print()


# --- Injection safety demonstration ------------------------------------------

@promptstring(strict=False)
def outer(content: str) -> None:
    """Answer: {content}"""


async def injection_demo() -> None:
    # A value containing {braces} is never re-parsed — it passes through literally.
    ctx = PromptContext({"content": "Use {variables} like this"})
    result = await outer.render(ctx)
    print("=== Injection safety ===")
    print(result)
    assert "{variables}" in result  # braces are literal, not substituted


# --- Forgetting to render: the two tiers -------------------------------------

async def forgot_to_render_demo() -> None:
    """A prompt object left where a rendered string belongs, at both tiers.

    Tier 1 — passed as the parameter value: PromptRenderError (ADR 0011 D3).
    Tier 2 — nested inside a structure: no error, but the object names itself
    instead of printing an address (ADR 0011 D5). Containers format their
    elements with repr(), which the guard cannot intercept, so nested cases are
    named rather than rejected.
    """
    print("=== Forgetting to render ===")

    # Tier 1: raises.
    try:
        await outer.render(PromptContext({"content": system_prompt}))
    except PromptRenderError as exc:
        print("top level  ->", exc)

    # Tier 2: renders, but is diagnosable rather than opaque.
    result = await outer.render(PromptContext({"content": [system_prompt]}))
    print("nested     ->", result)
    assert "object at 0x" not in result


asyncio.run(pattern_direct())
asyncio.run(pattern_di())
asyncio.run(injection_demo())
asyncio.run(forgot_to_render_demo())
