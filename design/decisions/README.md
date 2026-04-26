# Architecture Decision Records (ADRs)

Numbered, append-only records of accepted decisions. Once an ADR is
`Accepted`, it is immutable — to change a decision, write a new ADR that
supersedes the old one and update the old one's `Superseded by` field.

## Index

<!-- Add entries as ADRs are accepted. Keep newest at the top. -->

_No ADRs yet._

## Adding an ADR

1. Copy `0000-template.md` to `NNNN-kebab-case-title.md` using the next
   monotonic number.
2. Fill in Context, Decision, Alternatives, Consequences. Alternatives are
   mandatory.
3. Open as `Status: Proposed`. Flip to `Accepted` when the call is made.
4. Add an entry to the Index above.

## Why ADRs

Decisions decay without context. Six months from now, "why did we choose
the decorator API over a class API?" should have a one-link answer, not a
git-archaeology session.
