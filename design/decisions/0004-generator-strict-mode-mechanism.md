# 0004 — Generator strict-mode mechanism

- **Status:** Accepted
- **Date:** 2026-04-26
- **Deciders:** Daniyar Supiyev (author)
- **Supersedes:** —
- **Superseded by:** —

## Context

ADR 0001 Promise 11 commits that `@promptstring` strict-mode failures
fire before any caller-side LLM call via a structural check
(placeholder-set membership). For `@promptstring_generator`, the
same Promise 11 records that strict-mode is "best-effort with known
limitations" via a substring-occurrence check, and ADR 0001's C4
delta defers the choice between three concrete options to this ADR:

> **Evaluate generator strict-mode heuristic.** The
> substring-containment check is best-effort and has known gaps for
> values whose `str()` is a common substring (e.g. `""`, `"True"`,
> `"1"`). Either (a) document the best-effort limitation as part of
> the 1.0 contract (already done in Promise 11 above), or (b) replace
> with a structurally sound mechanism before tagging 1.0.

The current implementation (`core.py:274–286`):

```python
used = {
    name
    for name, value in resolved.items()
    if str(value) in "\n".join(m.content for m in messages)
}
extras = sorted(name for name in resolved if name not in used)
```

Known failure modes:

- **Empty-string false negatives.** `value=""` is a substring of any
  string, so an unused empty-string parameter passes strict-mode.
- **Common-substring false positives** for values whose `str()` is a
  short common token (`""`, `"True"`, `"False"`, `"1"`, `"0"`). A
  parameter whose value happens to be `"True"` may be flagged "used"
  when the rendered output mentions "True" for any other reason.
- **Numeric-substring false positives.** `value=42` rendered into
  `"4200 more results"` would pass strict because `"42"` occurs in
  `"4200"`.
- **Repr-shape mismatches.** `value=[1, 2, 3]` only matches if the
  user yielded the exact `str([1, 2, 3])` form (`"[1, 2, 3]"`,
  including spaces). Yielding `"[1,2,3]"` or `"1, 2, 3"` causes a
  false negative.

These gaps are inherent to substring-occurrence checking. Replacing
with a structurally sound mechanism requires changing the generator
protocol — either by introducing a sentinel that the user yields to
mark "this is a substituted parameter," or by tagging yielded
content with metadata.

This ADR records the choice between four options and documents the
1.x and 2.x evolution path.

## Decision

**Adopt option (a): keep the substring-occurrence heuristic; document
its limitations as part of the 1.0 contract.**

Strict-mode for `@promptstring_generator` remains opt-in
(`strict=False` default per ADR 0001 Promise 3). When the user
explicitly opts into `strict=True`:

- The library performs the substring-occurrence check on resolved
  parameter `str()` values against the joined rendered output.
- A resolved parameter not found is raised as
  `PromptUnreferencedParameterError`.
- The known limitations (empty-string false negatives, common-
  substring false positives, numeric-substring false positives,
  repr-shape mismatches) are documented as part of Promise 11.
- Users who require structurally sound strict-mode use
  `@promptstring`, where strict-mode is structural by construction
  (placeholder-set membership).

The existing language in ADR 0001 Promise 11 already encodes this:
"the substring-occurrence check is best-effort with known
limitations." This ADR ratifies that as the 1.0 mechanism rather
than introducing a new sentinel-based mechanism before tagging.

### Implementation note: warn on known-bad value patterns

To soften the worst false-negative cases without breaking the
contract, the implementation MAY (not MUST) emit a stdlib `logging`
warning at WARNING level when:

- a resolved parameter has `str(value) == ""` (empty-string false
  negative is structurally guaranteed); or
- a resolved parameter has `len(str(value)) <= 1` (single-character
  false-positive risk).

The warning is informative for the developer; it does not raise and
does not affect the strict-mode pass/fail outcome. The logger name
SHOULD be `promptstrings.strict_heuristic` (parallel to
`promptstrings.observer` from ADR 0002). This warning behavior is
**not part of the 1.0 contract** — it is an implementation
recommendation that may evolve in 1.x without SemVer impact.

## Alternatives considered

### Option (b) — `Param(name)` sentinel for opt-in structural strict

The decorated generator would `yield Param("user_name")` instead of
`yield str(user_name)`. The library would substitute `str(value)` at
render time and track which `Param` sentinels appeared in the yield
stream. Strict-mode becomes structural: every resolved parameter
must correspond to a `Param` sentinel that was yielded.

```python
# Hypothetical syntax under option (b)
@promptstring_generator(strict=True)
def conversation(topic: str, user: str):
    yield Role("system")
    yield "You are an expert on "
    yield Param("topic")              # structural mark
    yield "."
    yield Role("user")
    yield "Tell me about "
    yield Param("topic")
    yield " for "
    yield Param("user")
    yield "."
```

**Why rejected for 1.0:**

- Adds `Param` as a new public symbol to the surface, exceeding the
  surface budget that ADR 0002 deliberately capped.
- Forces users into a verbose yield idiom that breaks the natural
  Python-generator pattern (`yield f"..."` interpolation). The
  cleaner-than-f-string DX promised in VISION is harmed.
- Requires a migration path from current `yield f"text {var}"`
  patterns; users on 0.x would face a breaking syntax change.
- The opt-in nature means most users never enable structural strict
  anyway — they get the same outcome as option (a) with extra
  surface.

**Why this remains the strongest 1.x candidate.** If real users
report that the heuristic's false positives or false negatives are
causing material pain, option (b) is the natural evolution: it can
be added as **purely additive** in a 1.x minor release because:

- `Param` would be a new optional sentinel; yielding strings would
  continue to work unchanged.
- Strict-mode could probe the yield stream: if any `Param` sentinel
  is present, use structural check; otherwise fall back to
  substring (current behavior).
- Existing 1.0 callers see no breakage; new callers opt into the
  stricter mechanism by yielding `Param`.

This evolution path is documented here so that adopting (b) in 1.x
does not require superseding this ADR — only an additive minor-
release ADR that names the new sentinel.

### Option (c) — Tagged yield protocol

The generator would yield typed tuples (`("text", "...")`,
`("param", "user_name", value)`) instead of bare strings. The library
would track parameter usage from the tagged stream.

**Why rejected:**

- Changes the generator yield protocol — every existing
  `@promptstring_generator` body would need to be rewritten. This is
  a 0.x → 1.0 breaking change beyond what ADR 0001's migration notes
  cover.
- More invasive than (b): all yields become tagged, not just the
  parameter-substitution ones.
- Same surface-cost concern as (b) plus a worse migration story.

### Option (d) — Drop generator strict-mode entirely

`@promptstring_generator(strict=True)` would raise
`NotImplementedError` (or be silently ignored, with `strict` accepted
but treated as `False`). Users needing strict-mode would use
`@promptstring`.

**Why rejected:**

- Breaks ADR 0001 Promise 3, which commits `strict` as a public
  parameter on **both** decorators with documented semantics for
  each.
- Removes a feature that exists in current `core.py` and that users
  on 0.x may already depend on.
- The asymmetry between the two decorators is already documented
  honestly in Promise 11 ("structural" vs. "best-effort"); silently
  removing the generator side after committing it would be a worse
  contract violation than the heuristic's known gaps.

## Consequences

**Positive:**
- 1.0 ships with no new public symbols. The surface budget set by
  ADR 0002 (≤6 new symbols, final tally 5+1) holds.
- ADR 0001 Promise 11's existing "best-effort with known limitations"
  language is sufficient; no edits to 0001 required.
- Users who need structural guarantees have a clear directive: use
  `@promptstring`. The library's two decorators serve different
  guarantee strengths, and the strength asymmetry is documented.
- Implementation work for this ADR is zero — current `core.py`
  behavior already implements option (a).

**Negative:**
- Strict-mode for `@promptstring_generator` is genuinely weak in the
  documented failure modes. A user with a parameter whose `str()`
  happens to be `"True"` may ship a bug to production that strict-
  mode failed to catch. This is the cost of locking option (a) for
  1.0.
- VISION Problem 1's "the class of silently-dropped-variable bugs
  ceases to exist" overstates for the generator path. The asymmetry
  note in VISION Problem 1 mitigates this, but a reader who skims
  may form an over-strong expectation.

**Neutral / follow-on:**
- No implementation deltas for the strict-mode mechanism itself
  beyond ADR 0001's existing C2 delta (wire
  `PromptUnreferencedParameterError` to the generator strict-check
  path). This ADR does not change that wiring.
- The recommended (non-contract) `WARNING` log for empty-string and
  single-character values MAY be added during implementation. If
  added, the logger name `promptstrings.strict_heuristic` is the
  recommended choice (parallel to `promptstrings.observer`).
- This ADR closes the C4 delta in ADR 0001's implementation work
  order. Once accepted, the only remaining 1.0-blocker ADR work is
  implementation of ADRs 0001 + 0002 + 0003 + 0004 against `core.py`,
  followed by R1–R16 test landing.
- Option (b) (Param sentinel) is the canonical 1.x evolution path
  if field data shows the heuristic's gaps cause material user pain.
  This evolution can be additive — no need to supersede this ADR.

## Notes

This ADR closes the C4 delta deferred by ADR 0001
([§ Promotion to ADR](0001-api-and-dx-baseline-for-1.0.md#consequences)).
After acceptance, the minimum-viable ADR set for tagging 1.0 is
complete: 0001 (baseline contract), 0002 (integration seams), 0003
(error field schema), 0004 (this ADR).

The decision to keep the heuristic is conservative for 1.0: when in
doubt about a contract surface, keep the smaller surface and document
the limitation honestly. Option (b)'s `Param` sentinel is a real
improvement in agent-DX legibility (the structural check would let
agents reason about strict-mode soundness directly from the yield
stream), but adopting it in 1.0 would lock a sentinel design before
any user has confirmed which sentinel shape they actually want.

VISION context: [`../VISION.md`](../VISION.md), Problem 1
("prompt construction entangled with call-site scope"), specifically
the asymmetry note in the library's-answer subsection.

Companion ADRs:
- [`0001-api-and-dx-baseline-for-1.0.md`](0001-api-and-dx-baseline-for-1.0.md)
  — Promise 11 (the contract surface this ADR ratifies), C4 delta
  (the deferral this ADR closes).
- [`0003-error-class-field-schema.md`](0003-error-class-field-schema.md)
  — `PromptUnreferencedParameterError` schema (the leaf class raised
  by the strict-check path retained in this ADR).
