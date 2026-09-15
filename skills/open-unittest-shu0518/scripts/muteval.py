"""muteval.py — deterministic, stdlib-only verifier for generated unit tests.

Core of the Open Track metric (open-unittest-shu0518). No third-party deps so
it runs identically in the held-out grading environment.

Pipeline (all in-process):
  1. build a module = reference source + generated test source, exec it.
  2. baseline: run every `test_*()` function on the *unmodified* reference;
     record which pass. The metric only trusts tests that pass on the reference.
  3. coverage: re-run baseline-passing tests under sys.settrace, measure which
     executable lines of the reference were hit.
  4. mutation: deterministically generate single-point AST mutants of the
     reference (arithmetic / comparison / boolean / constant operators). For
     each mutant, re-run the baseline-passing tests; a mutant is *killed* if any
     of those tests now fails or errors. mutation_score = killed / total.

A test that does not exercise the code's behaviour cannot kill mutants, so the
score cannot be gamed by coverage padding or hardcoded constants — this is the
anti-gameable property required by the spec.
"""
from __future__ import annotations

import ast
import sys
import copy
import types
import builtins

# Cap mutants so a pathological input cannot blow the wall-clock budget.
MAX_MUTANTS = 60
COMBINED_FILENAME = "<aiase_combined>"


# --------------------------------------------------------------------------- #
# Test collection + execution
# --------------------------------------------------------------------------- #
def _build_module(ref_src: str, test_src: str):
    """Compile reference + tests into one namespace. Reference keeps lines 1..R
    so coverage line numbers map directly. Returns (namespace, ref_line_count)."""
    ref_lines = ref_src.count("\n") + 1
    combined = ref_src.rstrip("\n") + "\n\n" + test_src
    code = compile(combined, COMBINED_FILENAME, "exec")
    ns: dict = {"__name__": "aiase_combined", "__builtins__": builtins}
    exec(code, ns)
    return ns, ref_lines


def _test_names(ns: dict) -> list[str]:
    out = []
    for name, obj in ns.items():
        if name.startswith("test_") and isinstance(obj, types.FunctionType):
            if obj.__code__.co_argcount == 0:
                out.append(name)
    return sorted(out)


def _run_one(ns: dict, name: str) -> tuple[bool, str]:
    """Run a single test function. Returns (passed, error_repr)."""
    try:
        ns[name]()
        return True, ""
    except Exception as e:  # AssertionError or any runtime error => not passing
        return False, f"{type(e).__name__}: {e}"


def run_tests(ref_src: str, test_src: str, only: list[str] | None = None):
    """Exec ref+tests, run the named tests (or all). Returns dict:
       {ok_build, build_error, results: {name: (passed, err)}}."""
    try:
        ns, _ = _build_module(ref_src, test_src)
    except Exception as e:
        return {"ok_build": False, "build_error": f"{type(e).__name__}: {e}",
                "results": {}}
    names = only if only is not None else _test_names(ns)
    results = {n: _run_one(ns, n) for n in names}
    return {"ok_build": True, "build_error": "", "results": results}


# --------------------------------------------------------------------------- #
# Coverage (stdlib settrace)
# --------------------------------------------------------------------------- #
def _executable_lines(ref_src: str) -> set[int]:
    """Executable statement lines of the reference (exclude def/class headers
    and bare docstrings)."""
    tree = ast.parse(ref_src)
    lines: set[int] = set()
    headers = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            headers.add(node.lineno)
        if isinstance(node, ast.stmt) and hasattr(node, "lineno"):
            lines.add(node.lineno)
    docstrings = set()
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if body and isinstance(body[0], ast.Expr) and \
                isinstance(getattr(body[0], "value", None), ast.Constant) and \
                isinstance(body[0].value.value, str):
            docstrings.add(body[0].lineno)
    return (lines - headers - docstrings)


def coverage(ref_src: str, test_src: str, passing: list[str]) -> float:
    """Fraction of reference executable lines hit while running passing tests."""
    exec_lines = _executable_lines(ref_src)
    if not exec_lines:
        return 0.0
    try:
        ns, ref_lines = _build_module(ref_src, test_src)
    except Exception:
        return 0.0
    hit: set[int] = set()

    def tracer(frame, event, arg):
        if event == "line" and frame.f_code.co_filename == COMBINED_FILENAME:
            ln = frame.f_lineno
            if ln <= ref_lines:
                hit.add(ln)
        return tracer

    sys.settrace(tracer)
    try:
        for n in passing:
            try:
                ns[n]()
            except Exception:
                pass
    finally:
        sys.settrace(None)
    covered = exec_lines & hit
    return round(len(covered) / len(exec_lines), 4)


# --------------------------------------------------------------------------- #
# Mutation (single-point AST mutations, deterministic order)
# --------------------------------------------------------------------------- #
_BINOP = {ast.Add: ast.Sub, ast.Sub: ast.Add, ast.Mult: ast.FloorDiv,
          ast.Div: ast.Mult, ast.FloorDiv: ast.Mult, ast.Mod: ast.Mult,
          ast.Pow: ast.Mult}
_CMP = {ast.Lt: ast.GtE, ast.LtE: ast.Gt, ast.Gt: ast.LtE, ast.GtE: ast.Lt,
        ast.Eq: ast.NotEq, ast.NotEq: ast.Eq, ast.Is: ast.IsNot,
        ast.IsNot: ast.Is}
_BOOL = {ast.And: ast.Or, ast.Or: ast.And}


def _mutables(tree: ast.AST) -> list[ast.AST]:
    """Mutable nodes in a fixed (ast.walk) order so the k-th node is stable
    across reparses of identical source."""
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.BinOp) and type(node.op) in _BINOP:
            out.append(node)
        elif isinstance(node, ast.Compare) and node.ops and type(node.ops[0]) in _CMP:
            out.append(node)
        elif isinstance(node, ast.BoolOp) and type(node.op) in _BOOL:
            out.append(node)
        elif isinstance(node, ast.Constant) and isinstance(node.value, bool):
            out.append(node)
        elif isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            out.append(node)
    return out


def _describe(node: ast.AST) -> str:
    if isinstance(node, ast.BinOp):
        return f"binop {type(node.op).__name__}->{_BINOP[type(node.op)].__name__}"
    if isinstance(node, ast.Compare):
        return f"cmp {type(node.ops[0]).__name__}->{_CMP[type(node.ops[0])].__name__}"
    if isinstance(node, ast.BoolOp):
        return f"bool {type(node.op).__name__}->{_BOOL[type(node.op)].__name__}"
    if isinstance(node, ast.Constant) and isinstance(node.value, bool):
        return f"const {node.value}->{not node.value}"
    return f"const {node.value!r}->{node.value}+1"


def _apply(node: ast.AST) -> None:
    if isinstance(node, ast.BinOp):
        node.op = _BINOP[type(node.op)]()
    elif isinstance(node, ast.Compare):
        node.ops[0] = _CMP[type(node.ops[0])]()
    elif isinstance(node, ast.BoolOp):
        node.op = _BOOL[type(node.op)]()
    elif isinstance(node, ast.Constant) and isinstance(node.value, bool):
        node.value = not node.value
    elif isinstance(node, ast.Constant):
        node.value = node.value + 1


def make_mutants(ref_src: str) -> list[tuple[str, str]]:
    """Return [(description, mutated_source)] — one single-point mutation each."""
    try:
        base = ast.parse(ref_src)
    except SyntaxError:
        return []
    n = len(_mutables(base))
    mutants: list[tuple[str, str]] = []
    for k in range(n):
        tree = ast.parse(ref_src)
        target = _mutables(tree)[k]
        desc = _describe(target)
        _apply(target)
        try:
            src = ast.unparse(ast.fix_missing_locations(tree))
        except Exception:
            continue
        mutants.append((desc, src))
        if len(mutants) >= MAX_MUTANTS:
            break
    return mutants


# --------------------------------------------------------------------------- #
# Top-level metric
# --------------------------------------------------------------------------- #
def evaluate(ref_src: str, test_src: str) -> dict:
    """Compute the full Open Track self-report for one (reference, tests) pair."""
    report = {
        "ok_build": False, "build_error": "",
        "n_tests": 0, "tests_pass_on_reference": False,
        "passing_tests": [], "failing_tests": [],
        "coverage_pct": 0.0,
        "mutants_total": 0, "mutants_killed": 0, "mutation_score": 0.0,
        "surviving_mutants": [],
    }

    base = run_tests(ref_src, test_src)
    report["ok_build"] = base["ok_build"]
    report["build_error"] = base["build_error"]
    if not base["ok_build"]:
        return report

    results = base["results"]
    report["n_tests"] = len(results)
    passing = [n for n, (ok, _) in results.items() if ok]
    failing = [n for n, (ok, _) in results.items() if not ok]
    report["passing_tests"] = passing
    report["failing_tests"] = failing
    report["tests_pass_on_reference"] = (len(results) > 0 and not failing)

    if not passing:
        return report

    report["coverage_pct"] = round(coverage(ref_src, test_src, passing) * 100, 2)

    mutants = make_mutants(ref_src)
    report["mutants_total"] = len(mutants)
    killed = 0
    survivors = []
    for desc, msrc in mutants:
        run = run_tests(msrc, test_src, only=passing)
        if not run["ok_build"]:
            killed += 1  # mutant that won't even build is detected => killed
            continue
        if any(not ok for ok, _ in run["results"].values()):
            killed += 1
        else:
            survivors.append(desc)
    report["mutants_killed"] = killed
    report["surviving_mutants"] = survivors[:20]
    report["mutation_score"] = round(killed / len(mutants), 4) if mutants else 0.0
    return report