# Agent Developer Experience (LLM-agent users)

Design docs for how `promptstrings` should *feel* to an LLM agent that is
reading, writing, or modifying code that uses the library.

Agents are a different audience than humans:
- They read by introspecting types, signatures, and error messages —
  often without seeing the README or long docstrings.
- They produce code via in-context examples; surfaces with high
  "guessability" beat surfaces that require careful reading.
- They struggle with implicit conventions and silent failures more than
  humans do.
- They benefit disproportionately from precise, structured error
  messages that name the offending field.

## Concerns owned by this track

- **Type clarity:** are public types narrow enough that a type-aware
  agent can infer correct usage?
- **Error structure:** do exceptions carry enough machine-readable
  context that an agent can self-correct without re-running with prints?
- **Schema introspection:** can an agent ask the library "what
  placeholders does this template require?" without rendering it?
- **Examples-as-API:** is the README's quickstart code the same shape an
  agent would generate by analogy?
- **Failure messages:** do error strings name the symbol, file, and
  resolved values, so an agent can grep its way back to the cause?
- **Guessability:** when an agent invents a method name (`render_one`,
  `as_messages`, `to_string`), does the actual API match the most
  obvious guess, or do we lead the agent astray?

## Index

<!-- Add entries as docs land. -->

_No agent-DX docs yet._

## Out of scope

Pure human-facing ergonomics belong in `../dx/`. Architectural
decisions belong in `../decisions/`. This folder is for design
*thinking* about agent-facing ergonomics — the choices that make the
library more or less legible to a model reading and writing code.
