"""Resolving declared parameters from a PromptContext, including concurrent async resolvers."""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import Callable
from typing import Any

from .errors import PromptRenderError
from .introspection import _annotated_markers
from .types import AwaitPromptDepends, PromptContext, PromptDepends


async def _maybe_await(value: Any) -> Any:
    """Await value if it is awaitable; otherwise return it directly."""
    if inspect.isawaitable(value):
        return await value
    return value

async def _resolve_dependencies(
    fn: Callable[..., Any],
    context: PromptContext,
    *,
    hints: dict[str, Any],
) -> dict[str, Any]:
    """Resolve all declared parameters for fn using the given context.

    Resolution priority per parameter:
    1. Annotated[T, AwaitPromptDepends(resolver)] — async, collected for gather
    2. Annotated[T, PromptDepends(resolver)] — sync resolver
    3. parameter.default is AwaitPromptDepends / PromptDepends (silent deprecated)
    4. name in context.values — direct value lookup
    5. parameter.default (Python default) or raise PromptRenderError

    AwaitPromptDepends resolvers (steps 1 and 3) run concurrently via
    asyncio.wait; the first exception cancels all siblings (ADR 0001 P9, ADR 0008).
    """
    signature = inspect.signature(fn)
    resolved: dict[str, Any] = {}
    async_names: list[str] = []
    async_coros: list[Any] = []

    for name, parameter in signature.parameters.items():
        markers = _annotated_markers(hints.get(name))

        # Step 1: Annotated[T, AwaitPromptDepends(resolver)]
        await_dep = next((m for m in markers if isinstance(m, AwaitPromptDepends)), None)
        if await_dep is not None:
            async_names.append(name)
            async_coros.append(await_dep.resolver(context))
            continue

        # Step 2: Annotated[T, PromptDepends(resolver)]
        sync_dep = next((m for m in markers if isinstance(m, PromptDepends)), None)
        if sync_dep is not None:
            resolved[name] = await _maybe_await(sync_dep.resolver(context))
            continue

        # Step 3: default-value PromptDepends / AwaitPromptDepends (silent deprecated)
        default = parameter.default
        if isinstance(default, AwaitPromptDepends):
            async_names.append(name)
            async_coros.append(default.resolver(context))
            continue
        if isinstance(default, PromptDepends):
            resolved[name] = await _maybe_await(default.resolver(context))
            continue

        # Step 4: context.values
        if name in context.values:
            resolved[name] = context.values[name]
            continue

        # Step 5: Python default or raise
        if default is inspect.Parameter.empty:
            raise PromptRenderError(
                f"Unable to resolve prompt parameter: {name}",
                missing_key=name,
                context_keys=tuple(context.values.keys()),
            )
        resolved[name] = default

    if async_coros:
        # Run all AwaitPromptDepends concurrently (ADR 0001 P9, ADR 0008).
        # asyncio.wait with FIRST_EXCEPTION is used instead of asyncio.gather so
        # that sibling tasks are explicitly cancelled when one raises — fulfilling
        # the "first exception cancels the rest" contract. asyncio.gather leaves
        # siblings running as orphaned tasks on the event loop.
        tasks = [asyncio.ensure_future(c) for c in async_coros]
        _, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_EXCEPTION)
        for t in pending:
            t.cancel()
            try:
                await t
            except asyncio.CancelledError:
                pass
        # Propagate via .result() which re-raises with original __traceback__ intact.
        for name, task in zip(async_names, tasks):
            resolved[name] = task.result()

    return resolved
