# Developer Experience (human users)

Design docs for how `promptstrings` should *feel* to a human user — the
person reading docstrings, writing the first integration, debugging a
failed render.

## Concerns owned by this track

- API ergonomics: decorator vs. class vs. functional surfaces, naming,
  argument shape, defaults.
- Error legibility: do error messages name the offending placeholder, the
  template line, the resolved values?
- Strictness vs. flexibility: when the library says "no," is it teaching
  or punishing?
- Documentation surface: what belongs in the README, in docstrings, in
  long-form guides, in examples.
- IDE / type-checker experience: does autocomplete reveal the right
  surface? Does mypy point at the right line?
- Discoverability: how does a new user find what they need without
  reading the source?

## Index

<!-- Add entries as docs land. -->

_No DX docs yet._

## Out of scope

Anything that primarily affects LLM agents as users belongs in
`../agent-dx/`. Anything that's a pure architectural decision belongs in
`../decisions/`. Use this folder for design *thinking* about
human-facing ergonomics.
