"""The three prompt classes and the guarantees each one carries.

Which guarantees you get depends on what the decorated function returns:

    docstring        -> owned-static   the library renders; placeholders known
                                       at decoration; strict before render;
                                       response_schema available
    -> Template      -> owned-dynamic  the library renders; placeholders not
                                       known until render; strict still enforced
    -> PromptSource  -> delegated      you render; the library never parses the
                                       text; no strict mode; provenance carried

The trade this example is really about: **strictness and provenance are on
opposite sides**. Owned paths check placeholders and set no provenance; the
delegated path carries provenance and checks nothing.

The delegated section below builds its text with an f-string to keep this
example dependency-free. In a real deployment that line is where Jinja2,
Mustache, or a prompt-management SDK's `.compile()` would go — the library does
not care which, because it never looks at the result.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from string.templatelib import Template

from promptstrings import (
    PromptContext,
    PromptRenderError,
    PromptSource,
    PromptSourceProvenance,
    PromptStrictnessError,
    parse_trusted_template,
    promptstring,
)


@dataclass(frozen=True)
class Summary:
    """A user-defined return type, so response_schema has something to report."""

    headline: str
    bullets: list[str]


# --- 1. Owned-static: the docstring is the template --------------------------

@promptstring
def owned_static(topic: str) -> Summary:
    """Summarise {topic} for a technical reader."""


# --- 2. Owned-dynamic: the library still renders, at render time -------------

TEMPLATE_FROM_STORE = "You are an expert on {topic}."  # trusted, not user input


@promptstring
def owned_dynamic(topic: str) -> Template:
    return parse_trusted_template(TEMPLATE_FROM_STORE)


# --- 3. Delegated: you render, the library carries provenance ----------------

@promptstring(strict=False)
def delegated(topic: str) -> PromptSource:
    # A real deployment renders with Jinja2 or a vendor SDK here. The library
    # never re-parses whatever comes back.
    text = f"You are an expert on {topic}."
    return PromptSource(
        content=text,
        provenance=PromptSourceProvenance(
            source_id="prompts/expert.jinja2",
            version="2026-07-27",
            hash="sha256:2c1a…",
        ),
    )


# --- the same two shapes, with a declared-but-unreferenced parameter ---------
# Used below to show that strict mode survives into owned-dynamic and cannot
# exist in delegated. Both declare `spare`, which no template mentions.

@promptstring
def owned_dynamic_lax(topic: str, spare: int = 0) -> Template:
    return parse_trusted_template(TEMPLATE_FROM_STORE)


@promptstring(strict=False)
def delegated_with_spare(topic: str, spare: int = 0) -> PromptSource:
    return PromptSource(content=f"You are an expert on {topic}.")


async def main() -> None:
    ctx = PromptContext({"topic": "Python packaging"})

    print("=== placeholders, known at decoration time ===")
    print(f"  owned-static : {sorted(owned_static.placeholders)}")
    print(f"  owned-dynamic: {sorted(owned_dynamic.placeholders)}  <- not known yet")
    print(f"  delegated    : {sorted(delegated.placeholders)}  <- never parsed")

    print("\n=== response_schema ===")
    print(f"  owned-static : {owned_static.response_schema}")
    print(f"  owned-dynamic: {owned_dynamic.response_schema}")
    print(f"  delegated    : {delegated.response_schema}")
    print("  only owned-static can declare one: the annotations that select the")
    print("  other two shapes are exactly the ones response_schema ignores.")

    print("\n=== provenance, on rendered messages ===")
    for label, prompt in [
        ("owned-static ", owned_static),
        ("owned-dynamic", owned_dynamic),
        ("delegated    ", delegated),
    ]:
        messages = await prompt.render_messages(ctx)
        print(f"  {label}: {messages[0].source}")

    print("\n=== strict mode ===")
    # Strict mode checks *declared parameters*, not context values: a key in the
    # context that the function never declares is simply never resolved, so it
    # cannot be reported as unused. Both prompts below therefore declare one.

    # Owned-dynamic still catches it — at render time, not decoration time.
    try:
        await owned_dynamic_lax.render(ctx)
        print("  owned-dynamic: no error (unexpected)")
    except PromptStrictnessError as exc:
        print(f"  owned-dynamic: {type(exc).__name__} — strict mode still applies")

    # Delegated cannot: the text was never parsed, so there is nothing to check.
    result = await delegated_with_spare.render(ctx)
    print(f"  delegated    : rendered anyway, no check possible -> {result!r}")

    print("\n=== delegation is unavailable on the generator engine ===")
    from promptstrings import promptstring_generator

    @promptstring_generator
    def multi(topic: str):
        yield PromptSource(content=f"Expert on {topic}.")

    try:
        await multi.render(ctx)
    except PromptRenderError as exc:
        print(f"  {exc}")


asyncio.run(main())
