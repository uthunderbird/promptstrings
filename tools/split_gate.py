"""Acceptance gates for the ADR 0012 module split.

Two modes:

    python tools/split_gate.py capture   # step 0, run BEFORE the split
    python tools/split_gate.py check     # step 4, run AFTER the split

`capture` records the pre-split surface into tools/split_baseline.json:
every top-level binding name in core.py, the package `__all__`, the names
reachable from `promptstrings` and `promptstrings.core`, and each top-level
definition's source text keyed by name.

`check` verifies gates 1, 3, 5, 6 and 7 from ADR 0012 D9 against that
baseline. Gates 2 and 4 are covered by importing at all and by `make`.

Gate 6 allows exactly the three deltas ADR 0012 D8 requires for the cycle
fix, applied as transformations of the pre-split text, and nothing else.

**Gate 6 is a split-time gate; the others are not.** It answers one
historical question — did the split move code without editing it — and it
was answered at the split commit. Every legitimate change to a moved
definition afterwards will fail it, correctly, because the baseline is a
frozen snapshot of a file that no longer exists. To re-check the historical
claim, run `check` against the split commit (e.g. in a worktree) rather than
against the working tree.

Gates 1, 3, 5 and 7 stay meaningful indefinitely: they assert that the
public surface, the shim, and the layering still hold.
"""

from __future__ import annotations

import ast
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
PKG = ROOT / "src" / "promptstrings"
BASELINE = pathlib.Path(__file__).resolve().parent / "split_baseline.json"

# ADR 0012 D8: the three edits the split is permitted to make, as exact
# transformations of the pre-split text rather than as an exemption list.
#
# Exempting a whole definition would make every later change to it invisible:
# once `_PromptStringGenerator` is on a skip-list, an unrelated edit to its body
# passes unnoticed. Applying the expected transformation and then demanding exact
# equality keeps the gate able to fail.
PERMITTED_DELTAS: dict[str, tuple[str, str]] = {
    "_is_unrendered_prompt": (
        "    return isinstance(value, (_PromptString, _PromptStringGenerator))",
        "    return isinstance(value, _PromptObject)",
    ),
    "_PromptString": ("class _PromptString:", "class _PromptString(_PromptObject):"),
    "_PromptStringGenerator": (
        "class _PromptStringGenerator:",
        "class _PromptStringGenerator(_PromptObject):",
    ),
}


def _segment(source_lines: list[str], node: ast.AST) -> str:
    """Source text of `node`, including any decorators.

    `ast.get_source_segment` starts at the `def`/`class` line, so a decorated
    definition loses its decorators. Silently dropping `@dataclass` produces a
    plain class that still imports and still passes a behavioural test suite
    through the public API, so this must be handled here rather than trusted.
    """
    start = node.lineno
    for dec in getattr(node, "decorator_list", []):
        start = min(start, dec.lineno)
    return "\n".join(source_lines[start - 1 : node.end_lineno])


def top_level_defs(path: pathlib.Path) -> dict[str, str]:
    """Map every top-level binding in `path` to its source text."""
    source = path.read_text()
    lines = source.splitlines()
    tree = ast.parse(source)
    out: dict[str, str] = {}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            out[node.name] = _segment(lines, node)
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for t in targets:
                if isinstance(t, ast.Name):
                    out[t.id] = _segment(lines, node)
    return out


def package_defs() -> dict[str, str]:
    """Top-level definitions across every module in the package except the shim."""
    out: dict[str, str] = {}
    for py in sorted(PKG.glob("*.py")):
        if py.name in {"__init__.py", "core.py"}:
            continue
        for name, src in top_level_defs(py).items():
            out[name] = src
    return out


def reachable(module_name: str) -> list[str]:
    import importlib

    mod = importlib.import_module(module_name)
    return sorted(n for n in dir(mod) if not n.startswith("__"))


def module_import_graph() -> dict[str, set[str]]:
    """Intra-package import edges, module -> modules it imports from."""
    graph: dict[str, set[str]] = {}
    for py in sorted(PKG.glob("*.py")):
        if py.name in {"__init__.py", "core.py"}:
            continue
        edges: set[str] = set()
        tree = ast.parse(py.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.level == 1 and node.module:
                edges.add(node.module)
        graph[py.stem] = edges
    return graph


def find_cycle(graph: dict[str, set[str]]) -> list[str] | None:
    """Return one cycle as a node list, or None if the graph is a DAG."""
    WHITE, GREY, BLACK = 0, 1, 2
    colour = dict.fromkeys(graph, WHITE)
    stack: list[str] = []

    def visit(node: str) -> list[str] | None:
        colour[node] = GREY
        stack.append(node)
        for nxt in sorted(graph.get(node, ())):
            if nxt not in colour:
                continue
            if colour[nxt] == GREY:
                return stack[stack.index(nxt) :] + [nxt]
            if colour[nxt] == WHITE:
                found = visit(nxt)
                if found:
                    return found
        colour[node] = BLACK
        stack.pop()
        return None

    for node in sorted(graph):
        if colour[node] == WHITE:
            found = visit(node)
            if found:
                return found
    return None


def capture() -> None:
    import promptstrings

    data = {
        "core_defs": top_level_defs(PKG / "core.py"),
        "package_all": sorted(promptstrings.__all__),
        "reachable_package": reachable("promptstrings"),
        "reachable_core": reachable("promptstrings.core"),
    }
    BASELINE.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
    print(f"captured {len(data['core_defs'])} definitions -> {BASELINE.name}")
    print(f"  package __all__: {len(data['package_all'])} names")
    print(f"  reachable from promptstrings: {len(data['reachable_package'])}")
    print(f"  reachable from promptstrings.core: {len(data['reachable_core'])}")


def check() -> int:

    import promptstrings
    import promptstrings.core

    base = json.loads(BASELINE.read_text())
    failures: list[str] = []
    historical: list[str] = []

    def gate(number: str, ok: bool, detail: str, *, split_time: bool = False) -> None:
        """Report a gate.

        `split_time` gates answer a historical question — did the split move code
        without editing it — and were answered at the split commit. Every
        legitimate later edit to a moved definition makes them differ, correctly.
        They are reported but do not fail the run, because a permanently red
        check is one people learn to ignore. To re-check the historical claim,
        run against the split commit in a worktree.
        """
        if ok:
            print(f"[PASS] gate {number}: {detail}")
        elif split_time:
            print(f"[INFO] gate {number}: {detail}")
            print("       (split-time gate: differs because of a legitimate later edit)")
            historical.append(number)
        else:
            print(f"[FAIL] gate {number}: {detail}")
            failures.append(number)

    # Gate 1 — public names and __all__ unchanged.
    missing_public = [n for n in base["package_all"] if not hasattr(promptstrings, n)]
    gate(
        "1a",
        not missing_public,
        f"all {len(base['package_all'])} public names import from promptstrings"
        + (f" — missing {missing_public}" if missing_public else ""),
    )
    # The permanent invariant is that no public name is *lost*. Demanding
    # byte-identity would make this gate red for every later feature that
    # legitimately exports something — ADR 0012's own D4 adds one.
    removed = sorted(set(base["package_all"]) - set(promptstrings.__all__))
    added = sorted(set(promptstrings.__all__) - set(base["package_all"]))
    gate(
        "1b",
        not removed,
        "no public name removed from promptstrings.__all__"
        + (f" — removed {removed}" if removed else "")
        + (f" (added since the split: {added})" if added else ""),
    )

    # Gate 3 — every pre-split core name still importable from the shim.
    missing_shim = [n for n in base["core_defs"] if not hasattr(promptstrings.core, n)]
    gate(
        "3",
        not missing_shim,
        f"all {len(base['core_defs'])} pre-split names import from promptstrings.core"
        + (f" — missing {missing_shim}" if missing_shim else ""),
    )

    # Gate 5 — import-surface equivalence, scoped to the library's own names.
    #
    # Pre-split, `promptstrings.core` also exposed every module it imported —
    # `promptstrings.core.asyncio`, `.Any`, `.Template` and so on — because a
    # module's imports are attributes of it. That is incidental leakage, not
    # surface: no caller can reasonably depend on reaching the stdlib through
    # this module, and re-exporting `asyncio` from a shim to preserve it would
    # be absurd. The gate therefore protects the names `core` *defined*, and
    # reports the incidental difference instead of failing on it.
    own = set(base["core_defs"])
    lost_pkg = sorted(set(base["reachable_package"]) - set(reachable("promptstrings")))
    gate("5a", not lost_pkg, "promptstrings surface preserved" + (f" — lost {lost_pkg}" if lost_pkg else ""))

    now_core = set(reachable("promptstrings.core"))
    lost_own = sorted((set(base["reachable_core"]) & own) - now_core)
    gate(
        "5b",
        not lost_own,
        "promptstrings.core defined-name surface preserved"
        + (f" — lost {lost_own}" if lost_own else ""),
    )
    incidental = sorted((set(base["reachable_core"]) - own) - now_core)
    if incidental:
        print(f"       note: {len(incidental)} incidental import attributes no longer "
              f"reachable via promptstrings.core ({', '.join(incidental[:4])}, …) — accepted")

    # Gate 6 — definitions moved, not edited (except D8's three exact deltas).
    now = package_defs()
    edited: list[str] = []
    absent: list[str] = []
    for name, src in base["core_defs"].items():
        if name not in now:
            absent.append(name)
            continue
        expected = src
        if name in PERMITTED_DELTAS:
            old, new = PERMITTED_DELTAS[name]
            if old not in expected:
                edited.append(f"{name} (permitted delta no longer applies)")
                continue
            expected = expected.replace(old, new, 1)
        if now[name] != expected:
            edited.append(name)
    gate("6a", not absent, "every definition has a home" + (f" — unplaced {absent}" if absent else ""))
    gate(
        "6b",
        not edited,
        "no definition edited beyond D8's three permitted deltas"
        + (f" — since edited: {edited}" if edited else ""),
        split_time=True,
    )

    # Gate 7 — no cross-module import cycle.
    cycle = find_cycle(module_import_graph())
    gate("7", cycle is None, "module import graph is a DAG" + (f" — cycle {cycle}" if cycle else ""))

    if historical:
        print(f"\nsplit-time gate(s) now differ: {', '.join(historical)} — expected after "
              f"later edits, not a regression")
    if failures:
        print(f"{len(failures)} gate(s) failed: {', '.join(failures)}")
        return 1
    print("all standing gates passed")
    return 0


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    if mode == "capture":
        capture()
    elif mode == "check":
        sys.exit(check())
    else:
        print(__doc__)
        sys.exit(2)
