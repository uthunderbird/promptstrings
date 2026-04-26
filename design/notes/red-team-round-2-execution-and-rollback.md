---
title: Red-Team Round 2 — Execution, Failure Modes, and Rollback
target: design/proposals/api-1.0-baseline.md
round: 2 of 3
focus: Execution order, failure modes, rollback, and test coverage adequacy
created: 2026-04-24
---

# Red-Team Round 2 — Execution, Failure Modes, and Rollback

## Scope

Round 1 addressed contract gaps. Round 2 assumes the contract surface is roughly
right and asks: can it actually be executed? Companion code examined:
`src/promptstrings/core.py`.

Findings are classified as:
- **CRITICAL** — execution will fail, hard rollback constraint, or missing required test surface
- **LOWER-PRIORITY** — real gap, meaningful DX cost, but not an execution blocker
- **RECOMMENDATION** — improvement without a concrete failure path

---

## Critical Findings

### C-1: R1 test description is internally incoherent

**Location:** DX rubric, R1.

R1 says: "render with a missing placeholder; assert `exc.placeholder` is set and
`exc.resolved_keys` is a tuple."

"Missing placeholder" is the scenario where the template references `{name}` but
`name` was not resolved — this raises `PromptRenderError` (lines 188–189 in
`core.py`), not a strictness error. The named attributes `exc.placeholder` and
`exc.resolved_keys` are presumably intended for `PromptUnusedParameterError` (the
reverse case: resolved key not consumed by template). The rubric scenario and the
expected attributes belong to different error classes and different failure
directions.

This ambiguity makes R1 unpassable as written — any test author will have to guess
which scenario is intended. If R1 tests the wrong class, it will either never raise
or will test an exception that has no named attributes post-delta.

**Simultaneously**, the proposal defers "Exact field set on each error class's
named-attributes API" to a separate ADR (section "Out of scope of this proposal").
R1 demands `exc.placeholder` and `exc.resolved_keys` by name. These two
commitments are in direct conflict. One must yield; the document does not resolve
this.

**Fix required:** Correct R1 to test the right scenario (unused parameter in
`@promptstring`), name the exact attributes that will exist on
`PromptUnusedParameterError`, and remove the deferral of "exact field set" — or
scope the deferral to exclude the attributes tested in R1–R9.

---

### C-2: Decoration-time parsing creates an undocumented breaking import-semantic change

**Location:** Promise 7, Promise 8, Promotion step 4 ("Move template parsing to
decoration time"), no corresponding migration section.

In the current code, `_PromptString` does no template parsing at construction time
(`__init__`, lines 160–164). `_normalize_source` is called only from
`_resolve_source` at render time (line 169). Under current 0.x behavior, importing
a module that contains a docstring-missing `@promptstring` function does not raise
— the error is deferred until render.

The 1.0 delta moves this to decoration time (`__init__`). This is a significant
change in import semantics:

- Test suites that import modules containing promptstring-decorated functions to
  test other code paths will now fail at collection time with `PromptCompileError`
  if any decorated function is missing a valid docstring.
- Test fixtures that mock the render call to avoid template errors will not help,
  because the error fires at decoration time before any mock can be installed.
- Applications that lazily import modules will see import-time errors where they
  previously saw render-time errors; error handling at the call site will no longer
  catch these.

No migration note exists in the proposal. R8's test ("import a module containing
such a function; assert PromptCompileError") confirms this is intentional behavior,
but nothing in the proposal warns 0.x users.

**Fix required:** Add a migration note in the proposal (or the future ADR) calling
out this import-semantic change explicitly.

---

### C-3: `asyncio.gather` for async resolvers is a structural rewrite, not a patch — and is a one-way door

**Location:** Promise 9, Promotion step 4 (C1 delta).

The current `_resolve_dependencies` (lines 128–148) runs all resolvers in a single
sequential loop, interleaving sync and async resolvers in parameter declaration
order. The return value is `tuple[dict[str, Any], int]` — the count `int` is used
by four callers to check `> 1` before raising.

Converting this to concurrent `asyncio.gather` requires:
1. A two-pass loop: collect `PromptDepends` first (run sequentially), collect
   `AwaitPromptDepends` separately (dispatch as tasks).
2. Removing the `awaited_dependency_count` return value and all four `> 1` guard
   checks across `_PromptString.render`, `_PromptString.render_messages`,
   `_PromptStringGenerator.render_messages`, and `_resolve_dependencies` itself.
3. Merging gathered results back into the resolved dict.

This is not a small patch. The document says "Replace with `asyncio.gather`" as if
it is a one-line change; it is a structural rewrite of the resolution loop. If any
of the four guard sites is updated before the gather implementation is in place,
the library is in a broken intermediate state where multiple async resolvers run
sequentially without a guard and without the promised concurrency.

Once the gather semantics are published, rolling back to sequential is a breaking
change: callers that relied on concurrency (e.g., concurrent DB + cache fetches)
would suffer latency regressions, and callers that had non-cancellation-safe
resolvers that accidentally worked under sequential execution would start failing.
**The gather delta is a one-way door.**

The proposal does not acknowledge either the structural scope of the rewrite or the
irreversibility of this change.

**Fix required:** In Promotion step 4, expand the C1 delta description to
acknowledge (a) the need to restructure `_resolve_dependencies` as a two-pass
design, (b) the need to remove the four guard sites atomically, and (c) that this
is irreversible once shipped.

---

### C-4: Dynamic-source strict-mode fires after side-effecting async resolvers have run

**Location:** Promise 10/11, Lifecycle integration map (Render phase).

Promise 10 says: "strict-mode failures raise before any LLM call." This is
technically true — the caller's LLM call site is never reached if strict validation
fails.

However, the execution order within `render()` for the dynamic-source path (where
the wrapped function returns a `PromptSource` at render time) is:

1. Resolve dependencies — async resolvers run here, potentially making network
   calls, DB queries, or LLM calls within resolver bodies.
2. Call the wrapped function to get the `PromptSource`.
3. Compile the template from the dynamic source.
4. Validate strict-mode (check placeholder membership).
5. Raise `PromptUnusedParameterError` if strict fails.

Step 4 can raise after step 1 has already run side-effecting resolvers. The
promise "raise before any LLM call" applies to the *caller's downstream LLM call*,
not to LLM calls made inside resolver bodies or the wrapped function itself. A user
who reads Promise 10 as "if validation fails, nothing has happened yet" is wrong,
and the document does not correct this.

This is not a contract violation as written, but it is a meaningful gap between the
promise's spirit and its scope. In the docstring-source path, this problem also
exists but is less severe because template compilation happened at decoration time
and strict checking is purely structural.

**Fix required:** Add a scope qualifier to Promise 10 clarifying that "before any
LLM call" refers to the caller's downstream LLM call, not to calls made inside
resolver bodies, which have already run by the time strict validation fires.

---

### C-5: Promise 10 "raise before any LLM call" has a generator-body loophole

**Location:** Promise 10, Promise 11, `_PromptStringGenerator.render_messages`
lines 274–285.

For `@promptstring_generator` with `strict=True`, the strict check happens after
all generator items have been collected (line 274, after the flush at line 272).
This means:

- The generator body has fully executed.
- Any `await` points inside the generator body have completed.
- Any LLM calls made inside the generator body have already returned.

If a user's generator calls an LLM internally (a common usage pattern: "generate
prompt parts, call LLM for context enrichment, yield the enriched content"), and
the strict check then fires, an LLM call has already been made before the error
was raised.

Promise 11 acknowledges the heuristic nature of the generator strict check (false
negatives on common substrings) but does not acknowledge this ordering problem. The
guarantee of "raise before any LLM call" is silently violated for all generator
bodies that contain LLM calls.

This gap exists independently of the heuristic's false-negative problem. Even a
structurally sound generator strict mechanism (as suggested in the C4 delta) would
not fix this ordering issue — as long as strict validation happens after generator
execution, generator-internal LLM calls will have already fired.

**Fix required:** Acknowledge in Promise 11 that for `@promptstring_generator`, the
"raise before any LLM call" guarantee does not extend to LLM calls made inside the
generator body. Consider whether this should be a separate scope qualifier or
whether it changes the recommendation for the C4 delta (e.g., move strict checking
to a pre-execution annotation mechanism).

---

### C-6: Leaf exception delta (C2) and the test delta are not ordered — R4 will fail if tests land first

**Location:** Promotion step 4, bullets 5–6 (C2 delta) vs. last bullet ("Land
tests for R1–R9").

Both C2 delta and the test delta appear as peers in step 4 with no ordering
specified. R4 tests `isinstance(exc, PromptUnusedParameterError)` — which requires
C2 to have landed. If the test suite is written and run before C2 is implemented,
R4 fails and blocks the 1.0 gate. If tests are written but not run until after all
deltas, the development cycle loses the benefit of TDD.

More precisely: R4 as written only tests class existence and isinstance routing, not
that the *right* class is raised in the *right* scenario. A malicious-but-compliant
implementation could raise `PromptUnusedParameterError` from the generator path and
`PromptUnreferencedParameterError` from the template path and R4 would pass. R4
needs a second assertion: that each class is raised from its respective code path.

**Fix required:** In Promotion step 4, sequence the C2 delta before the test delta
explicitly, and expand R4 to include path-specificity assertions.

---

### C-7: R8 fails against current code; the decoration-time parsing delta is a prerequisite for it

**Location:** DX rubric R8, Promotion step 4.

R8 says: "import a module containing such a function; assert PromptCompileError."
The current `__init__` for `_PromptString` (lines 160–164) does not call
`_normalize_source` or `_compile_template`. The error is deferred to
`_resolve_source` at render time. R8 will fail against current code.

The Promotion plan lists the decoration-time parsing delta and the test delta as
peers. If R8 is run before the parsing delta lands, it fails — and since all
R1–R9 must pass before tagging, this creates an execution ordering constraint the
plan does not state.

**Fix required:** The parsing delta must precede the test run for R8. State this
ordering in Promotion step 4.

---

## Lower-Priority Findings

### L-1: R4 does not verify path-routing, only class existence

**Location:** DX rubric R4.

R4 checks `isinstance(exc, PromptUnusedParameterError)` — this passes as long as
the class exists and `isinstance` works. A compliant-but-wrong implementation could
route all strictness failures through `PromptUnusedParameterError` regardless of
which code path raised. R4 needs a complementary assertion: trigger a generator
strict failure explicitly and assert `PromptUnreferencedParameterError` (not
`PromptUnusedParameterError`) is raised.

---

### L-2: R7 is not automatable as stated

**Location:** DX rubric R7.

"Every public type... has a one-line class docstring readable in `help()` output."
`help()` is an interactive REPL tool. The wording "a test the library must pass
before 1.0" implies CI automation, but no test form is given. A straightforward
automated form would be: for each public class exported from `promptstrings`,
assert `cls.__doc__ is not None` and `"\n" not in cls.__doc__.strip()`. The rubric
should either state this form or clarify that R7 is a manual inspection gate, not
an automated test.

---

### L-3: `type(exc) == PromptStrictnessError` exact-match catches break silently after C2 delta

**Location:** Promise 5, C2 delta.

After the C2 delta, `PromptStrictnessError` is never raised directly — only its
leaves are. Code that uses `type(exc) == PromptStrictnessError` (exact type
equality, not `isinstance`) will silently stop catching these errors. This is not
caught by `isinstance`-based tests.

No migration note exists for this pattern. It is an uncommon but valid Python
pattern (used when callers specifically want to catch only the base class, not
subclasses). The risk is silent swallowing of strictness failures in 0.x→1.0
migrations.

---

### L-4: `asyncio.gather` is a one-way door; the document does not say so

**Location:** Promise 9.

See C-3 for the full argument. The irreversibility is mentioned under C-3 as a
critical execution concern, but even setting that aside, users benefit from knowing
that concurrent resolution semantics cannot be removed in a 1.x patch without a
2.0. The document should state this explicitly.

---

### L-5: `Promptstring` Protocol is append-only but this is not stated

**Location:** Promise 1, Promise 2.

The document says new decorators in 1.x must satisfy the `Promptstring` Protocol.
It does not say whether Protocol members can be removed or narrowed in 1.x. The
implication is that the Protocol is append-only (adding members would break
implementations that don't have them; removing members would break callers that
use them). This constraint is load-bearing — if the Protocol is silently treated as
append-only, any future "Protocol minimization" would be a breaking 2.0 change even
if the authors did not realize they were making a 2.0-scope commitment.

---

### L-6: "New contract version" for `inspect.Parameter` replacement is ambiguous

**Location:** Promise 2, "The `Parameter` type in `declared_parameters`..."

"a future ADR may wrap it in a custom dataclass, but any such change is a new
contract version." Does "new contract version" mean 2.0? Or can it be done in 1.x
with a new ADR? If it can be done in 1.x, it breaks callers who type-annotate
against `inspect.Parameter`. This should be stated as "requires a 2.0" or
explicitly excluded from the 1.x compatibility guarantee.

---

### L-7: Missing test for `context=None` equivalence (Promise 4)

**Location:** Promise 4 ("Passing `context=None`... is exactly equivalent to
passing an empty `PromptContext()`"), DX rubric.

No R-criterion tests this equivalence. There is no falsifiable test that
`render(None)` and `render(PromptContext())` produce identical results. This is a
small but load-bearing promise — it is part of the 1.0 contract and has no rubric
coverage.

---

### L-8: Promotion plan is unordered — no safe partial-land state described for the gather delta

**Location:** Promotion step 4.

The gather delta touches 4 locations in `core.py` (`_resolve_dependencies`,
`_PromptString.render`, `_PromptString.render_messages`,
`_PromptStringGenerator.render_messages`). Updating any subset leaves the library
in a broken state. The promotion plan lists all deltas as peers with no ordering.
For any delta that spans multiple files or multiple call sites, the plan should
state the atomic unit and whether partial application is safe.

---

## Recommendations

### REC-1: Add an explicit dependency order to Promotion step 4

The current plan is a flat list. A minimum safe order is:

```
1. Decoration-time parsing delta  (prerequisite for Protocol delta and R8)
2. Protocol delta + placeholders/declared_parameters  (depends on 1)
3. Named attributes + to_dict() on exception classes  (prerequisite for R1, R6)
4. C2 delta (leaf exceptions) — atomic: both leaves at once  (prerequisite for R4)
5. C1 delta (gather) — atomic: all 4 sites at once  (prerequisite for Promise 9)
6. C4 delta (generator strict evaluation)
7. R1–R9 test suite  (prerequisite: all above deltas landed)
8. Tag 1.0
```

Steps 4 and 5 are independent of each other but both depend on step 3. Steps 2 and
3 are independent but both depend on step 1.

---

### REC-2: Clarify what "raise before any LLM call" means for resolvers

Promise 10's guarantee is scoped to the caller's downstream LLM call. It says
nothing about LLM calls made inside resolver bodies or the wrapped function. A
single sentence in Promise 10 or in the lifecycle map would prevent user confusion:
"This guarantee applies to the caller's downstream LLM call. Async resolvers
execute during the Resolution phase; any side effects they produce occur before
strict validation runs."

---

### REC-3: Add a "0.x → 1.0 migration" section or note

At minimum, call out:
- Import-time raising change (previously render-time for missing docstrings).
- `type(exc) == PromptStrictnessError` exact-match catch blocks silently break.
- `AwaitPromptDepends` at-most-one guard is removed (previously a guard for a
  programming mistake; now silently proceeds and runs both concurrently).

---

### REC-4: Expand R4 to assert path-routing

Add a complementary test: "trigger a generator strict failure; assert
`PromptUnreferencedParameterError` (not `PromptUnusedParameterError`) is raised."
Without this, R4 only verifies class existence, not routing correctness.

---

### REC-5: Make R7 automatable

Specify R7 as: "for each class exported from `promptstrings.__all__` (or the
public surface), assert `cls.__doc__ is not None` and that it contains no embedded
newlines (one-liner check)." This can run in CI. The current "readable in help()
output" form cannot.

---

## Ledger

**Target document:** `design/proposals/api-1.0-baseline.md`

**Focus:** Execution order, failure modes, rollback, and test coverage adequacy
(Round 2 of 3)

**Main findings:**

| # | Severity | Finding |
|---|----------|---------|
| C-1 | CRITICAL | R1 test description tests the wrong error class; simultaneously conflicts with the "exact field set deferred" non-promise |
| C-2 | CRITICAL | Decoration-time parsing is an undocumented breaking import-semantic change; no migration note |
| C-3 | CRITICAL | Gather delta is a structural rewrite of `_resolve_dependencies` (not a small patch), irreversible, and has no safe partial-land state |
| C-4 | CRITICAL | Dynamic-source strict-mode fires after side-effecting async resolvers have already run; Promise 10 does not acknowledge this |
| C-5 | CRITICAL | Generator-body LLM calls violate the spirit of Promise 10's "raise before any LLM call" guarantee; not acknowledged in Promise 11 |
| C-6 | CRITICAL | C2 delta and test delta are unordered in Promotion step 4; R4 fails if tests land before C2; R4 also lacks path-routing assertion |
| C-7 | CRITICAL | R8 fails against current code; decoration-time parsing delta must precede the test run |
| L-1 | LOWER | R4 only checks class existence, not that the right class is raised from the right path |
| L-2 | LOWER | R7 is not automatable as stated |
| L-3 | LOWER | `type(exc) == PromptStrictnessError` exact-match catches break silently after C2 delta; no migration note |
| L-4 | LOWER | Gather semantics are irreversible (one-way door); document does not state this |
| L-5 | LOWER | `Promptstring` Protocol is effectively append-only but this is not stated |
| L-6 | LOWER | "New contract version" for `inspect.Parameter` replacement is ambiguous (1.x vs. 2.0?) |
| L-7 | LOWER | `context=None` equivalence (Promise 4) has no rubric coverage |
| L-8 | LOWER | Promotion plan has no ordering; no safe partial-land state described for multi-site deltas |

**Ordered fix list for Round 3 repair:**

1. **(C-1)** Correct R1: fix the scenario (unused parameter, not missing placeholder),
   commit to the specific attribute names (`exc.unused_parameters` or equivalent) on
   `PromptUnusedParameterError`, and reconcile with or narrow the "exact field set
   deferred" non-promise.
2. **(C-2)** Add a "0.x → 1.0 migration" note covering the import-semantic change
   (decoration-time raising), `type() ==` exact-match breakage, and the guard removal.
3. **(C-3 + L-8)** Add an explicit dependency order to Promotion step 4 (see
   REC-1). Flag the gather delta as requiring an atomic 4-site change and as
   irreversible once shipped.
4. **(C-4)** Add a scope qualifier to Promise 10: "before the caller's downstream
   LLM call" — distinguish from resolver-body side effects.
5. **(C-5)** Add an acknowledgement in Promise 11 that generator-body LLM calls
   are not covered by the "raise before any LLM call" guarantee.
6. **(C-6)** Sequence C2 delta before the test delta in Promotion step 4; expand
   R4 to assert path-routing (see REC-4).
7. **(C-7)** State in Promotion step 4 that the parsing delta must land before the
   test suite is run (R8 will fail otherwise).
8. **(L-2 + REC-5)** Make R7 automatable: specify an assertable form.
9. **(L-5)** State explicitly that the `Promptstring` Protocol is append-only in
   1.x; removing or narrowing members requires a 2.0.
10. **(L-6)** Clarify that replacing `inspect.Parameter` with a custom dataclass
    requires a 2.0 (not just a "new contract version").
11. **(L-7)** Add an R-criterion (or extend an existing one) to test `context=None`
    equivalence.
12. **(L-4)** Add a sentence to Promise 9 noting that concurrent gather semantics
    are irreversible; rolling back to sequential would be a 2.0 change.
