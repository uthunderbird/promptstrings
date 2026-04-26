---
title: Red-team round 1 — contract completeness and correctness
round: 1 of 3
focus: Completeness and correctness of the 1.0 contract surface
target: design/proposals/api-1.0-baseline.md
date: 2026-04-24
---

# Red-team round 1: contract completeness and correctness

Treat the document as a SemVer commitment for an external library.
Every finding below is grounded in the document text, the companion
implementation (`src/promptstrings/core.py`), or the logical
relationship between them.

---

## Critical findings (contract is wrong or breakable)

### C1. Promise 8 contradicts the implementation — the "concurrent gather" contract does not exist yet

Promise 8 states: "`AwaitPromptDepends` resolvers run concurrently via
`asyncio.gather`." The document explicitly says this "replaces the
current 'at most one' runtime restriction."

The companion `core.py` still enforces the at-most-one restriction at
lines 183–185 and 204–206:

```python
if awaited_dependency_count > 1:
    raise PromptRenderError(
        "Promptstring render currently allows at most one AwaitPromptDepends dependency"
    )
```

The 1.0 document is making a contract promise about behavior that the
implementation actively prohibits. If this document were tagged 1.0
today, every user with two or more `AwaitPromptDepends` decorators
would receive a `PromptRenderError` at runtime despite the promise.
This is not a documentation lag — it is a live contradiction between
stated contract and code gate. The document must either retract the
promise or block the tag until the guard is removed and `asyncio.gather`
is in place.

Severity: **critical** — the promise is currently false.

---

### C2. `PromptUnusedParameterError` and `PromptUnreferencedParameterError` are promised but not defined anywhere in the contract

Promise 4 introduces two leaf exception classes:
`PromptUnusedParameterError` and `PromptUnreferencedParameterError`.
The document treats them as part of the public SemVer contract.

`core.py` has no such classes. The current code raises a single
`PromptStrictnessError` at line 192 and 213 (for `_PromptString`)
and at line 282 (for `_PromptStringGenerator`) — all with no subclass
distinction, and with different heuristics:

- `_PromptString`: "extra resolved keys not in template placeholders"
- `_PromptStringGenerator`: "str(value) not found in joined message content"

These two paths detect genuinely different failure modes (template
non-reference vs. generator non-consumption). But:

1. Neither class exists in the implementation.
2. The document does not specify *which* of the two leaf classes
   corresponds to which of the two code paths. The naming suggests
   `PromptUnusedParameterError` → `_PromptString` path (template
   didn't consume the parameter) and `PromptUnreferencedParameterError`
   → `_PromptStringGenerator` path (generator body didn't reference the
   value), but this is inference. The contract must state it explicitly.
3. DX test R4 references `isinstance` checks against these classes, so
   R4 cannot pass until they exist and are mapped.

Severity: **critical** — promised public classes are absent; R4 is
unpassable in the current codebase.

---

### C3. The `strict` parameter is not mentioned anywhere in the contract

Both `@promptstring` and `@promptstring_generator` accept a `strict`
keyword argument in the implementation. The document never mentions it.

This creates an immediate breakage risk:

- The document promises "Two decorators only" (Promise 1) and describes
  their behavior (Promises 5–11), but says nothing about whether
  `strict` is part of the public API.
- `_PromptString` defaults `strict=True`; `_PromptStringGenerator`
  defaults `strict=False` (lines 160 and 227). This asymmetry has
  observable consequences: passing `@promptstring` will raise on
  unreferenced parameters by default, while `@promptstring_generator`
  will not.
- If `strict` is a public parameter, Promise 10 ("strict-mode failures
  raise before any LLM call") implies a caller must know they can pass
  `strict=False` to disable this. The document is silent.
- If `strict` is *not* public, the different defaults are hidden state
  that users can stumble into via `inspect.signature`.
- The asymmetric defaults are themselves undocumented — a user who
  switches from `@promptstring` to `@promptstring_generator` for
  multi-role output will silently lose strict validation.

Severity: **critical** — the `strict` parameter is a load-bearing API
surface that the 1.0 contract entirely omits.

---

### C4. The generator strict-mode heuristic is unreliable and makes Promise 10 partially false

Promise 10 states: "If strict-mode validation fails, the caller's
downstream LLM call site is never reached." This is a strong guarantee.

The `_PromptStringGenerator` strict check (lines 274–285) validates by
looking for `str(value)` as a substring of the joined message content.
This heuristic has several failure modes:

1. **False negative — no raise when it should:** If `str(value)` is a
   common substring (e.g., `"True"`, `"1"`, `""`), the check passes
   even though the parameter was not intentionally referenced. The LLM
   call proceeds with a silently wrong prompt.
2. **False positive — raise when it should not:** If a value's string
   representation coincidentally appears in another part of the prompt,
   the check incorrectly passes.
3. **Empty-string value:** `str(value)` is `""`, which is a substring
   of any string, so the parameter is always "found." The check never
   fires for empty-string-valued parameters.

For `_PromptString`, the check is structurally sound (template
placeholder membership). For `_PromptStringGenerator`, it is not.
Promise 10 reads as applying uniformly across both types, but the
generator implementation cannot keep the promise with the current
heuristic.

The document should either (a) restrict Promise 10 to `_PromptString`
and document that generator strict-mode is best-effort, or (b) require
a structurally sound generator strict check.

Severity: **critical** — Promise 10 is false for generator strict-mode
in a class of realistic inputs.

---

## Lower-priority findings (contract is incomplete in a recoverable way)

### L1. `PromptCompileError` hierarchy position is semantically odd

`core.py` line 15: `class PromptCompileError(PromptRenderError)`.
The document says "Error hierarchy is rooted in `PromptRenderError`"
(Promise 4) and does not challenge this. But callers who catch
`PromptRenderError` to handle render-time failures will also catch
`PromptCompileError`, which fires at decoration time (import time), not
render time. A blanket `except PromptRenderError` in a request handler
will silently swallow import errors that should crash the process.

The contract should either acknowledge this inheritance explicitly and
recommend that `PromptCompileError` be caught separately (at decoration
time), or restructure the hierarchy so compile errors are not a subtype
of render errors.

Severity: **lower priority** — callers can work around it, but the
hierarchy misleads.

---

### L2. `PromptContext` mutability is unspecified and silently mutable

`PromptContext` is documented as "the only value-injection mechanism"
(Promise 3) with no mention of whether it is immutable. The
implementation uses `@dataclass(frozen=True)` with a `dict` field
(line 63). `frozen=True` prevents reassignment of the `values`
attribute, but the dict itself is mutable — a caller can mutate
`context.values` between two concurrent `render` calls on the same
instance, violating Promise 9 (re-entrancy) in practice without any
library error.

The contract should state whether `PromptContext` values are expected
to be immutable after construction, and whether the library defends
against in-place mutation.

Severity: **lower priority** — needs documentation; defensible by
copying the dict at resolution entry.

---

### L3. `declared_parameters` type is deferred but is still a Protocol member

Promise 2 lists `declared_parameters: Mapping[str, Parameter]` as a
Protocol member. The "Out of scope of this proposal" section defers the
"Exact type of `Parameter`" to a follow-up ADR.

But `declared_parameters` is already part of the promised Protocol. If
`Parameter` is not defined before 1.0, the Protocol member cannot be
fully typed, which means the runtime-checkable Protocol check
(`isinstance(x, Promptstring)`) may pass while the attribute's value
type is still in flux. Any code that iterates `declared_parameters` in
1.x will be depending on an unspecified `Parameter` type.

Either `Parameter` must be locked before 1.0, or `declared_parameters`
should be deferred from the Protocol until its value type is settled.

Severity: **lower priority** — the Protocol is half-specified.

---

### L4. Non-promise 4 makes a structural claim the Protocol contradicts

Non-promise 4 states: "A consumer typed against `Promptstring` must
rely only on '≥1 message of type `PromptMessage`.'"

But the `Promptstring` Protocol also promises `render() -> str`.
A caller invoking `.render()` on a `_PromptStringGenerator` gets a
string produced by joining all messages with `"\n\n"` — the join
separator is not promised. If the separator is not part of the contract,
callers who use `.render()` on a generator-backed promptstring cannot
predict the output format, yet they are using a promised API method.

The join separator (`"\n\n"`) is currently implementation detail
(non-promise), but callers who rely on `.render()` have a reasonable
expectation about what the string looks like. The contract should
either promise the separator or explicitly note that `.render()` on a
generator-backed instance has unspecified formatting.

Severity: **lower priority** — gap between a promise and reasonable
caller expectation.

---

### L5. The error lifecycle for `PromptRenderError` on missing context values is not in the lifecycle map

`PromptContext.require()` raises `PromptRenderError` directly (line
71). The lifecycle map names `PromptRenderError` nowhere in the
Resolution or Render phase rows, and does not note that the error
hierarchy can fire from within user-supplied resolver code (i.e., the
library provides `require()` as a helper that throws library errors
into user resolver code). A caller catching `PromptRenderError` after a
`render()` call will catch errors from their own resolvers without being
able to distinguish them from library errors.

The contract should mention that resolver bodies can raise
`PromptRenderError` (or its subclasses) and that these propagate
unchanged, or provide a distinct `PromptContextError` to allow
disambiguation.

Severity: **lower priority** — operational confusion for callers who
need to distinguish library failures from resolver failures.

---

## Recommendations (contract could be tightened)

### R-A. Cancellation safety is required but not testable as stated

Non-promise 2 states "Resolvers MUST be cancellation-safe." This is
correct, but the word "MUST" in a non-promise section creates an odd
asymmetry: the library cannot enforce this, yet the document presents
it as a hard user obligation. No DX test covers it. Consider adding at
minimum a prose note explaining what "cancellation-safe" means for
resolvers in asyncio (i.e., no finally-block side-effects that corrupt
shared state), and whether the library performs any best-effort cleanup
on cancellation.

### R-B. `render_messages` minimum guarantee is under-specified

Non-promise 4 says ≥1 `PromptMessage`. The Protocol does not specify
`PromptMessage`'s required fields (beyond `role` and `content` from
the dataclass). A consumer who receives a `PromptMessage` with
`source=None` but expected provenance has no contract to cite. The
minimum `PromptMessage` schema should be documented in the Protocol
section.

### R-C. The `python -OO` detection heuristic is documented but its error path is not

Promise 7 says the decorator raises `PromptCompileError` when `__doc__
is None` and names `-OO` as a likely cause. The document does not
specify what `PromptCompileError` carries (named attributes, message
text) for this case. Since error message text is explicitly non-promised
(Non-promise 3), a caller catching `PromptCompileError` cannot know
whether it fired for `-OO`, for a genuinely missing docstring, or for
a bad template. The error subtype hierarchy does not distinguish these.
A `PromptMissingSourceError` subtype would allow callers to handle the
`-OO` case differently from a template syntax error.

### R-D. No guidance on `context=None` vs. `context=PromptContext()` equivalence

Both `render` and `render_messages` accept `context: PromptContext |
None`. The implementation treats `None` as equivalent to
`PromptContext()` (empty context). The document never states this
equivalence as a promise, so a caller cannot rely on it across 1.x
versions. This should be a one-line promise.

---

## Ledger

**Target document:** `design/proposals/api-1.0-baseline.md`

**Focus used:** Completeness and correctness of the 1.0 contract surface
— hidden assumptions, contradictory promises, undefined-behavior gaps,
missing lifecycle phases, load-bearing non-promises.

**Main findings:**

| # | Severity | Summary |
|---|---|---|
| C1 | CRITICAL | Promise 8 (concurrent `asyncio.gather`) contradicts the live `at-most-one` guard in `core.py`; the promise is currently false. |
| C2 | CRITICAL | `PromptUnusedParameterError` and `PromptUnreferencedParameterError` are promised public classes that do not exist; R4 is unpassable. |
| C3 | CRITICAL | The `strict` parameter is a public, behavior-controlling API surface (with asymmetric defaults) that the contract entirely omits. |
| C4 | CRITICAL | Promise 10 (strict failures raise before LLM call) is false for `_PromptStringGenerator` under the substring-containment heuristic. |
| L1 | LOWER | `PromptCompileError` inherits from `PromptRenderError`; blanket render-error handlers silently swallow import-time errors. |
| L2 | LOWER | `PromptContext.values` dict is mutable despite `frozen=True`; re-entrancy promise (Promise 9) is violable by callers. |
| L3 | LOWER | `declared_parameters: Mapping[str, Parameter]` is a Protocol promise with a deferred `Parameter` type — half-specified for 1.0. |
| L4 | LOWER | `.render()` on a generator-backed instance uses an unspecified join separator; gap between a promised method and its output contract. |
| L5 | LOWER | `PromptContext.require()` raises library errors from inside user resolver code; no contract guidance on distinguishing library vs. resolver failures. |
| R-A | REC | "MUST be cancellation-safe" is unenforceable and untestable; needs elaboration or a best-effort library note. |
| R-B | REC | `PromptMessage` minimum schema is unspecified in the Protocol section. |
| R-C | REC | `PromptCompileError` subtypes do not distinguish `-OO` from bad template from missing docstring. |
| R-D | REC | `context=None` equivalence to `PromptContext()` is an implementation assumption, not a stated promise. |

**Ordered fix list for the repair round (priority order):**

1. **(C1)** Remove the `at-most-one` guard from `core.py` and replace
   with `asyncio.gather`; or retract Promise 8 until implementation
   is ready. Either way, document and code must agree before 1.0 tag.

2. **(C3)** Decide whether `strict` is public API. If yes, add it to
   the Promises section with both decorator signatures, document the
   default asymmetry (`True` for `@promptstring`, `False` for
   `@promptstring_generator`), and explain why. If no, mark it private
   and seal it.

3. **(C4)** Replace the generator strict-mode substring heuristic with
   a structurally sound check, or qualify Promise 10 to exclude
   generators and document what "best-effort" generator strict-mode
   means.

4. **(C2)** Define `PromptUnusedParameterError` and
   `PromptUnreferencedParameterError` in the contract (map each to its
   code path) and implement both classes in `core.py`.

5. **(L3)** Lock the `Parameter` type before the 1.0 tag, or move
   `declared_parameters` out of the Protocol and into the "deferred"
   list.

6. **(L1)** Restructure the error hierarchy so `PromptCompileError`
   is not a subtype of `PromptRenderError`, or add an explicit warning
   in the contract that compilation errors propagate through the render
   error class and must be caught separately at module import time.

7. **(R-D)** Promote `context=None` equivalence to `PromptContext()`
   to a one-line promise.

8. **(L4)** Promise the `"\n\n"` join separator for `.render()` on
   generator-backed instances, or qualify that `.render()` output
   format is unspecified for generators.

9. **(L2)** State whether `PromptContext.values` is expected to be
   immutable after construction; defend at resolution entry if needed.

10. **(L5)** Note in the contract that `PromptContext.require()` (and
    any resolver that raises) can produce `PromptRenderError` from
    within user code, and provide guidance for distinguishing library
    vs. resolver failures.

11. **(R-C)** Add a `PromptMissingSourceError` (or similar) subtype
    to distinguish the `-OO` / missing-docstring case from template
    syntax errors.

12. **(R-A)** Expand the "cancellation-safe" MUST with a concrete
    definition or a brief example of what violates it.

13. **(R-B)** Document the minimum `PromptMessage` field set in the
    Protocol section.
