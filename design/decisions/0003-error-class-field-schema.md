# 0003 — Error class field schema and `to_dict()` contract

- **Status:** Accepted
- **Date:** 2026-04-26
- **Deciders:** Daniyar Supiyev (author); recommendations D1–D5 ratified
- **Supersedes:** —
- **Superseded by:** —

## Context

ADR 0001 commits in Promise 5 that "public exception classes carry
named, picklable attributes plus a `to_dict()` returning a JSON-safe
payload" and locks the field set on `PromptUnusedParameterError`
(per rubric R1: `exc.unused_parameters`, `exc.resolved_keys`). The
field set on every other public exception is explicitly deferred to
this ADR (baseline § *Out of scope of this proposal*).

The four exception classes whose schemas are not locked by ADR 0001:

1. **`PromptRenderError`** — root of the hierarchy; raised by
   `PromptContext.require()` on absent keys, by `_resolve_dependencies`
   when a required parameter has no resolver and no default, and
   propagates user resolver bodies that raise it.
2. **`PromptCompileError`** — fires at decoration time on missing
   docstring, format-spec or conversion in a placeholder, or
   non-identifier placeholder syntax.
3. **`PromptStrictnessError`** — abstract parent of the two leaf
   classes; users catch it directly via `except PromptStrictnessError`
   to handle either path uniformly. Never raised directly by library
   code (per ADR 0001).
4. **`PromptUnreferencedParameterError`** — generator strict-mode
   leaf; field-name parallel to `PromptUnusedParameterError` already
   committed by ADR 0001.

VISION Problem 3 ("errors are illegible to agents") makes this ADR
load-bearing: an LLM agent debugging a prompt failure must read the
exception's structured fields rather than parse the message string.
The R1-tested fields on `PromptUnusedParameterError` are not enough;
every public exception needs the same agent-legible shape.

This ADR records the schemas decided for each class plus five
convention rules (R-A through R-E) that govern `to_dict()`
serialization across the entire error hierarchy.

## Decision

### `PromptRenderError`

The root class for render-time failures. Caught for "something went
wrong during rendering" handling.

**Named attributes (1.0 contract):**

```python
class PromptRenderError(Exception):
    """Base class for render-time prompt failures."""

    missing_key: str | None
    """The parameter name that could not be resolved. None when the
    error did not originate from a missing-key path (e.g., user
    resolver raised it directly)."""

    context_keys: tuple[str, ...] | None
    """Keys present in PromptContext.values at the time of the error.
    None when the context was unavailable (e.g., user-raised before
    library entered resolution). extras keys are NOT included
    (extras is framework-private)."""
```

**`to_dict()` shape:**

```python
def to_dict(self) -> dict[str, Any]:
    return {
        "type": "PromptRenderError",
        "message": str(self),
        "missing_key": self.missing_key,
        "context_keys": list(self.context_keys) if self.context_keys is not None else None,
    }
```

**Resolver call chain.** Not exposed. Python's standard traceback
already shows where a user resolver raised; library-side
reconstruction would duplicate that information without adding
discriminating value for agents.

### `PromptCompileError`

Fires at decoration time. Three sub-causes from ADR 0001 Promise 8;
this ADR adds a fourth (`format_spec` and `conversion` collapsed
into one is the simplest split — they're really the same sub-cause
distinguished by the `Formatter.parse` field).

**Named attributes (1.0 contract):**

```python
class PromptCompileError(PromptRenderError):
    """Raised at decoration time when a template cannot be compiled."""

    prompt_name: str
    """The __name__ of the decorated function. Always set."""

    cause: Literal[
        "missing_template",
        "format_spec",
        "conversion",
        "non_identifier_placeholder",
    ]
    """Discriminator for which compile-time check failed."""

    placeholder: str | None
    """The offending placeholder text, when applicable. None for
    cause='missing_template' (no placeholder is at fault — the
    template itself is absent)."""

    optimize_mode_active: bool
    """True iff sys.flags.optimize >= 2 at the time of the error.
    Set on every PromptCompileError. Particularly meaningful when
    cause='missing_template': True suggests python -OO stripped
    the docstring."""
```

**`to_dict()` shape:**

```python
def to_dict(self) -> dict[str, Any]:
    return {
        "type": "PromptCompileError",
        "message": str(self),
        "prompt_name": self.prompt_name,
        "cause": self.cause,
        "placeholder": self.placeholder,
        "optimize_mode_active": self.optimize_mode_active,
        # PromptCompileError inherits from PromptRenderError, so
        # missing_key and context_keys are present from the parent;
        # both are always None for compile-time errors.
        "missing_key": None,
        "context_keys": None,
    }
```

**`cause` is a `Literal[str]`, not a `StrEnum`.** This is stdlib-
trivial: agents reading `exc.cause == "missing_template"` is more
legible than `exc.cause is PromptCompileCause.MISSING_TEMPLATE`. It
also avoids exporting an enum class as a public symbol — keeping the
surface budget tight.

### `PromptStrictnessError`

Abstract parent of the two leaves. Never raised directly by library
code. Users catch it via `except PromptStrictnessError` to handle
both paths uniformly.

**Named attributes:** none on the parent. The two leaves carry their
own field sets; the parent exists only as a catch-target.

**No constructor guard.** ADR 0001 commits the parent is never raised
by library code; that contract is enough. Defensive runtime
enforcement (`__init__` raising on direct instantiation) adds friction
without value — users who instantiate it directly are outside the
contract and on their own.

**`to_dict()`:** inherited from `PromptRenderError`. The parent class
exists only as a catch-target; concrete leaves override `to_dict()`
with their own field sets. A parent-typed instance never exists at
runtime under normal use.

### `PromptUnusedParameterError` and `PromptUnreferencedParameterError`

ADR 0001 R1 commits `exc.unused_parameters` and `exc.resolved_keys` on
`PromptUnusedParameterError`. By symmetry,
`PromptUnreferencedParameterError` exposes
`exc.unreferenced_parameters` and `exc.resolved_keys`. This ADR adds
the `to_dict()` shape per R6.

**`PromptUnusedParameterError.to_dict()`:**

```python
{
    "type": "PromptUnusedParameterError",
    "message": str(self),
    "unused_parameters": list(self.unused_parameters),
    "resolved_keys": list(self.resolved_keys),
    "missing_key": None,         # from parent; never set on this leaf
    "context_keys": None,        # from parent; never set on this leaf
}
```

**`PromptUnreferencedParameterError.to_dict()`:**

```python
{
    "type": "PromptUnreferencedParameterError",
    "message": str(self),
    "unreferenced_parameters": list(self.unreferenced_parameters),
    "resolved_keys": list(self.resolved_keys),
    "missing_key": None,         # from parent; never set on this leaf
    "context_keys": None,        # from parent; never set on this leaf
}
```

### Convention rules (apply to the entire error hierarchy)

- **R-A.** `to_dict()` always returns a `dict[str, Any]` with at
  least `"type"` and `"message"` keys. `"type"` is `cls.__name__`;
  `"message"` is `str(self)`.

- **R-B.** Tuples in attributes serialize to JSON arrays (via
  `list(...)`) in `to_dict()` output. The attribute itself stays a
  tuple at the Python level (immutable, hashable, picklable).

- **R-C.** `None`-valued attributes serialize as JSON `null`, NOT
  omitted from the dict. Stable shape across instances of the same
  class is part of the contract: a consumer iterating `to_dict()`
  keys may rely on the key set being constant for a given exception
  type.

- **R-D.** `to_dict()` MUST be JSON-safe per R6: every value is
  `None`, `bool`, `int`, `float`, `str`, `list[<JSON-safe>]`, or
  `dict[str, <JSON-safe>]`. No `datetime`, no `Path`, no custom
  classes, no objects requiring custom JSON encoders. User code
  wanting richer payloads MAY subclass and override `to_dict()`.

- **R-E.** Field names in `to_dict()` output are stable across the
  1.x line. New fields MAY be added (additive); existing fields MUST
  NOT be renamed or removed within a major version. Removing or
  renaming a field is a 2.0-scope breaking change.

### What 1.0's R6 test covers

R6 (from ADR 0001) says: "Every public exception has a `to_dict()`
returning a JSON-safe payload. *Test:* `json.dumps(exc.to_dict())`
round-trips."

Per this ADR, R6's coverage extends to:
- `PromptRenderError` instances raised from a missing-key path
  (`missing_key` set).
- `PromptCompileError` instances for each of the four `cause` values.
- `PromptUnusedParameterError` and `PromptUnreferencedParameterError`
  instances. (Already covered by R1.)
- `PromptStrictnessError` parent: not directly tested (never raised
  by library code per ADR 0001).

The test must verify that every key in the documented `to_dict()`
shape is present (R-C) and that the resulting dict survives
`json.dumps` round-trip (R-D).

## Alternatives considered

- **`cause` as `enum.StrEnum`** — rejected. Adds a new public symbol
  to the surface (the enum class), and an agent reading
  `exc.cause is MyEnum.MISSING_TEMPLATE` must first import the enum
  before doing the comparison. `Literal[str]` is type-safe at the
  static-checker level and stringly-comparable at runtime, with no
  import overhead.

- **Expose resolver call chain on resolver-raised `PromptRenderError`**
  — rejected. The standard Python traceback already shows where a
  user resolver raised. Library-side reconstruction (e.g., a
  `resolver_chain: tuple[str, ...]` attribute naming each
  `PromptDepends` traversed) would duplicate traceback information,
  bloat the exception surface, and create a new contract surface
  (the format and ordering of the chain) that the library would
  need to defend across versions. Rejected as over-engineering for
  1.0; revisit if real users report the traceback alone is
  insufficient.

- **`PromptRenderError.context_keys` includes `extras` keys** —
  rejected. `extras` is documented as framework-private (ADR 0002
  Promise I-3); leaking framework-state keys into agent-readable
  error payloads exposes implementation details users wouldn't
  expect to see. `context_keys` covers `values` only.

- **`PromptStrictnessError.__init__` raises on direct instantiation**
  — rejected. ADR 0001 already commits the class is never raised by
  library code; that contract is sufficient. A defensive runtime
  guard would penalize users who legitimately subclass for testing
  purposes, with no benefit to anyone else.

- **Omit `None`-valued keys from `to_dict()` output** — rejected.
  Stable shape across instances of the same class is more useful for
  agents (they can rely on key presence without conditional checks)
  than smaller payloads. The cost is a few null fields in the JSON;
  the benefit is predictable structure.

- **Return a `dataclass` from `to_dict()` instead of a `dict`** —
  rejected. A `dict[str, Any]` is the common JSON-shaped surface
  that all serialization libraries (Pydantic, `json`, `orjson`,
  `msgspec`) accept directly. Returning a dataclass forces consumers
  to call `dataclasses.asdict()` themselves.

## Consequences

**Positive:**
- VISION Problem 3 (errors illegible to agents) is fully addressed.
  Every public exception class exposes a stable, JSON-safe,
  named-attribute schema. An agent catching any `PromptRenderError`
  subclass can branch on `exc.type` (from `to_dict()`) or `type(exc)`
  and act on the named fields without parsing the message string.
- The hierarchy gains predictable shape: any `to_dict()` result
  always has `"type"` and `"message"`; subclass-specific fields
  follow. Agents and tooling can iterate `to_dict()` results
  uniformly.
- `PromptCompileError.optimize_mode_active` makes the
  `python -OO` debugging case mechanically detectable: an agent
  encountering `cause="missing_template"` and
  `optimize_mode_active=True` knows the cause is the optimize flag,
  not a missing docstring.

**Negative:**
- Five named attributes added to the public surface (across four
  classes). They lock for the entire 1.x line per R-E.
- `to_dict()` field names are now SemVer-contract-grade. A future
  revision wanting to rename a field (e.g., `missing_key` →
  `missing_parameter` for parallelism with leaves) is a 2.0 breaking
  change.
- `PromptCompileError.cause` is a `Literal` type with four values;
  adding a fifth in 1.x is *additive* (callers using
  `match`/`if-elif` chains won't break, but those using exhaustive
  static checking via `assert_never` will get a type error). This is
  acceptable but worth noting.

**Neutral / follow-on:**
- Implementation deltas (additions to ADR 0001's work order):
  1. Add `missing_key` and `context_keys` attributes to
     `PromptRenderError`. Wire population at:
     - `PromptContext.require()` raise site (set `missing_key` and
       `context_keys`)
     - `_resolve_dependencies` line 146 (set `missing_key`,
       `context_keys`).
     - User-raised paths leave both as `None`.
  2. Add `prompt_name`, `cause`, `placeholder`,
     `optimize_mode_active` attributes to `PromptCompileError`. Wire
     population at the four `PromptCompileError(...)` raise sites in
     `_compile_template` and at the new decoration-time check
     introduced by ADR 0001 Promise 8.
  3. Implement `to_dict()` on each class per the schemas above. Each
     leaf overrides; the parent provides a default that subclasses
     extend.
  4. Add tests for R6 covering each documented `to_dict()` field set
     (one test per class × per cause where applicable).
  5. Wire all of the above into the decoration-time and render-time
     code paths from ADR 0001's implementation deltas. This work
     depends on ADR 0001 deltas 1, 3, and 4 (decoration-time
     parsing, named-attributes infrastructure, leaf classes) being
     landed first.

- This ADR closes the deferred item recorded in baseline §
  *Out of scope of this proposal*: "Exact field set on each error
  class's named-attributes API, except for the attributes explicitly
  committed in the DX rubric."

- The remaining 1.0-blocker ADR is 0004 (generator strict-mode
  mechanism). After 0004 is accepted, the minimum-viable ADR set
  for tagging 1.0 is complete.

## Notes

The five decision points (D1–D5) raised during ADR drafting were all
ratified as proposed:

| ID | Question | Resolution |
|---|---|---|
| D1 | `PromptRenderError.context_keys` includes `extras`? | No — `values` only |
| D2 | Expose resolver call chain on resolver-raised errors? | No — traceback covers it |
| D3 | `PromptCompileError.cause` as `Literal` or `enum.StrEnum`? | Literal |
| D4 | Expose `optimize_mode_active: bool` on `PromptCompileError`? | Yes |
| D5 | `PromptStrictnessError.__init__` raises if instantiated directly? | No — contract is enough |

Companion ADRs:
- [`0001-api-and-dx-baseline-for-1.0.md`](0001-api-and-dx-baseline-for-1.0.md)
  — Promise 5 (error hierarchy), R1 (already-locked
  `PromptUnusedParameterError` schema), R6 (`to_dict()` rubric).
- [`0002-integration-seams-for-1.0.md`](0002-integration-seams-for-1.0.md)
  — `extras` privacy rationale (Promise I-3) anchors D1's exclusion.

VISION context: [`../VISION.md`](../VISION.md), Problem 3 ("Errors are
illegible to agents").
