# 0008 — Async resolver cancellation and error propagation

- **Status:** Proposed
- **Date:** 2026-04-27
- **Deciders:** Daniyar Supiyev
- **Supersedes:** —
- **Superseded by:** —

## Context

`_resolve_dependencies` runs all `AwaitPromptDepends` resolvers concurrently.
ADR 0001 Promise 9 commits to the following contract:

> "The first exception cancels the rest. Resolvers MUST be cancellation-safe
> and MUST NOT depend on side effects of other resolvers in the same render."

The original implementation used `asyncio.gather(*coros)` (default
`return_exceptions=False`). A code audit revealed that `asyncio.gather` does
**not** cancel sibling coroutines when one raises — it returns the first
exception to the caller but leaves the remaining coroutines running as
unattended tasks in the event loop. This directly contradicts the ADR 0001 P9
contract and makes the "resolvers MUST be cancellation-safe" requirement
meaningless (cancel never fires).

A secondary finding: stacktrace and re-raise behaviour across the entire
dependency resolution path was audited and found correct:

- `asyncio.gather`, `_maybe_await`, and the Observer `try/except … raise`
  blocks all propagate exceptions raw with no wrapping and no traceback
  truncation.
- Sync resolver exceptions propagate through `_maybe_await` without any
  intermediate frame pollution.
- The `except BaseException as exc: … raise` pattern in `render()` and
  `render_messages()` preserves the original traceback while still firing
  the Observer `RenderErrorEvent`.

No cleanup is needed for sync resolvers — they run sequentially and hold no
resources across calls. The only cleanup gap is the orphaned async tasks.

## Decision

Replace `asyncio.gather` in `_resolve_dependencies` with `asyncio.wait`
(`return_when=FIRST_EXCEPTION`) followed by explicit cancellation of all
pending tasks. Concretely:

1. Wrap each coroutine in `asyncio.ensure_future` to produce `Task` objects.
2. Await `asyncio.wait(tasks, return_when=asyncio.FIRST_EXCEPTION)`.
3. For each task in `pending`: call `task.cancel()` and `await` it, swallowing
   the resulting `CancelledError`. This delivers `CancelledError` to the
   resolver so it can run cleanup code in `try/finally` blocks.
4. Propagate the result by calling `task.result()` on each task in insertion
   order — `.result()` re-raises the stored exception with its original
   `__traceback__` intact, adding only a single `raise` frame at the call
   site.

This fulfils ADR 0001 P9 exactly: the first exception triggers cancellation of
all siblings, the original exception type and traceback are preserved, and the
public error API (ADR 0001 P5 hierarchy) is unchanged.

Error propagation invariants that are confirmed correct and require no change:

- Exceptions from sync resolvers (`PromptDepends`) propagate raw through
  `_maybe_await` with full traceback.
- The Observer `try/except BaseException … raise` pattern does not wrap or
  truncate exceptions.
- `PromptRenderError` is raised only for library-controlled failure cases
  (missing parameter, missing placeholder); user resolver exceptions are never
  wrapped.

## Alternatives considered

- **Keep `asyncio.gather`, fix only the docstring** — rejected. ADR 0001 P9
  is a public contract ("resolvers MUST be cancellation-safe"), not an
  implementation comment. The requirement is meaningless if cancel never fires.
  Fixing the documentation without fixing the behaviour would downgrade a
  promise retroactively.

- **Switch to `asyncio.TaskGroup` (Python 3.11+)** — rejected. `TaskGroup`
  raises `ExceptionGroup` when any child task fails. Catching
  `ExceptionGroup` requires `except*` syntax (Python 3.11+) and breaks the
  existing error hierarchy promised by ADR 0001 P5. Users currently catch
  `PromptRenderError`, `ValueError`, or resolver-specific exceptions directly;
  `ExceptionGroup` would make all of those catch-blocks fail silently.

- **`asyncio.wait` with `FIRST_COMPLETED` + polling** — rejected. Unnecessary
  complexity; `FIRST_EXCEPTION` is the right return_when value for this
  use case.

## Consequences

- **Positive:** ADR 0001 P9 contract is fulfilled. Async resolvers that
  perform I/O and hold resources (connections, locks) can clean up correctly
  via `try/finally` when cancelled. The "cancellation-safe" requirement is now
  load-bearing rather than decorative.

- **Positive:** Error propagation is clean: original exception type, original
  `__traceback__`, no wrapping. One additional frame (`raise` inside
  `_resolve_dependencies`) appears in the traceback — this is the same
  overhead as `asyncio.gather` and is acceptable.

- **Negative:** Each async resolver call requires an `asyncio.Task` object
  instead of a raw coroutine. For the typical case (a handful of resolvers per
  render) this overhead is negligible.

- **Neutral:** Resolvers were already required to be cancellation-safe by ADR
  0001 P9. No new requirement is introduced; the existing requirement now
  actually fires.

- **Neutral:** The docstring of `_resolve_dependencies` must be updated to
  accurately describe the `asyncio.wait` implementation rather than
  `asyncio.gather`.

## Notes

Audit findings (2026-04-27):

| Path | Stacktrace preserved | Re-raises | Cleanup needed |
|------|---------------------|-----------|----------------|
| Sync resolver via `_maybe_await` | ✅ | ✅ raw | — (sequential) |
| Async resolver via `asyncio.gather` | ✅ | ✅ raw | ⚠️ orphaned tasks |
| Observer `try/except … raise` | ✅ (bare `raise`) | ✅ | — |
| `_get_param_type_hints` retry path | ✅ (bare `raise`) | ✅ | — |

The only defect found was the orphaned task leak in the async resolver path.
All other error-handling paths are correct.
