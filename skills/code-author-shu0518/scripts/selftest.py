#!/usr/bin/env python3
"""
code-author selftest harness — STATIC + LOAD checks only (no test-case execution).

Scope (by design): verify the code is *legal and loadable*, not whether its
logic is correct. Correctness is judged solely by the grading environment on
hidden tests — the grader does NOT supply sample tests, so this harness does
NOT execute any. It only reports hard, deterministic facts that would otherwise
score the scenario 0:

  - loadable        : compiles and import-time exec succeeds (no syntax/runtime error at module level)
  - entry_defined   : constraints.entry_function is defined and callable
  - import_ok       : no forbidden imports (constraints.imports_forbidden)
  - sandbox_ok      : no eval/exec/open/__import__/compile, no subprocess/socket/... imports
  - loc_ok          : S-LOC (radon, spec §2.3) within constraints.max_loc

Output (stdout AND --out file, identical), a single JSON object:
{
  "checks_passed": int, "checks_failed": int,     # for run.py --selftest-file
  "loadable": bool, "entry_defined": bool,
  "import_ok": bool, "sandbox_ok": bool, "loc_ok": bool,
  "sloc": int, "max_loc": int,
  "import_violations": [...], "sandbox_violations": [...],
  "load_error": "", "all_clean": bool
}

Always exits 0 — it is a *report*, never a gate. The caller (run.py) always runs
afterwards so a result file is produced no matter what this reports.

Auto-chain to run.py (path safety): if --task_id is given, after writing the report
this script invokes the sibling run.py (path computed from __file__, so it is ALWAYS
correct no matter what the caller typed) to write the result file. The caller then
types only ONE path — this script's — removing the "wrong run.py path -> no result
file" failure mode.

Usage (one path, auto-writes result file):
  python3 <DIR>/scripts/selftest.py --code-file /tmp/ca_code.py --entry merge_intervals \
      --max-loc 500 --imports-forbidden "os,sys" --out /tmp/ca_selftest.json \
      --task_id task_pair_001 --rationale "..." --confidence 0.9

Usage (report only, no result file):
  python3 <DIR>/scripts/selftest.py --code-file /tmp/ca_code.py --entry merge_intervals
"""

from __future__ import annotations

import os
import ast
import json
import signal
import subprocess
import sys
import tempfile
import argparse
from contextlib import contextmanager
from pathlib import Path

LOAD_TIMEOUT_SEC = 5.0  # guards a module-level infinite loop at import time

_FORBIDDEN_CALLS = {"eval", "exec", "__import__", "open", "compile"}
_FORBIDDEN_IMPORT_ROOTS = {
    "subprocess", "multiprocessing", "threading",
    "importlib", "socket", "ctypes",
}


# --------------------------------------------------------------------------- #
# Timeout guard (covers module load)
# --------------------------------------------------------------------------- #
class _Timeout(Exception):
    pass


def _alarm(signum, frame):  # noqa: ANN001
    raise _Timeout()


_HAS_ALARM = hasattr(signal, "SIGALRM")


@contextmanager
def _time_limit(seconds: float):
    if not _HAS_ALARM or seconds <= 0:
        yield
        return
    old = signal.signal(signal.SIGALRM, _alarm)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, old)


# --------------------------------------------------------------------------- #
# Static checks
# --------------------------------------------------------------------------- #
def compute_sloc(code: str) -> int:
    """SLOC via `radon raw <file> --json` (spec §2.3). Fallback: non-blank, non-comment lines."""
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, encoding="utf-8") as f:
        f.write(code)
        path = Path(f.name)
    try:
        try:
            proc = subprocess.run(
                ["radon", "raw", str(path), "--json"],
                capture_output=True, text=True, timeout=10, check=False,
            )
            if proc.returncode == 0 and proc.stdout.strip():
                data = json.loads(proc.stdout)
                if isinstance(data, dict):
                    for v in data.values():
                        if isinstance(v, dict) and "sloc" in v:
                            return int(v["sloc"])
        except (FileNotFoundError, subprocess.TimeoutExpired, json.JSONDecodeError):
            pass
        return sum(1 for ln in code.splitlines()
                   if ln.strip() and not ln.strip().startswith("#"))
    finally:
        try:
            path.unlink()
        except OSError:
            pass


def _find_import_violations_with_parse_status(code: str, forbidden: list[str]) -> tuple[list[str], bool]:
    """Returns (violations, parse_ok). parse_ok=False means syntax error (cannot static-check)."""
    forbidden_set = {f.strip() for f in (forbidden or []) if f.strip()}
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return [], False
    if not forbidden_set:
        return [], True
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] in forbidden_set:
                    found.append(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            if node.module.split(".")[0] in forbidden_set:
                found.append(node.module)
    return sorted(set(found)), True


def find_import_violations(code: str, forbidden: list[str]) -> list[str]:
    """Return forbidden imports found in code. Kept list-shaped for local tests."""
    violations, _parse_ok = _find_import_violations_with_parse_status(code, forbidden)
    return violations


def find_sandbox_violations(code: str) -> list[str]:
    """Flag constructs the grading sandbox forbids (would score the scenario 0)."""
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return []
    out: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id in _FORBIDDEN_CALLS:
                out.append(f"call:{node.func.id}")
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] in _FORBIDDEN_IMPORT_ROOTS:
                    out.append(f"import:{alias.name}")
        elif isinstance(node, ast.ImportFrom) and node.module:
            if node.module.split(".")[0] in _FORBIDDEN_IMPORT_ROOTS:
                out.append(f"import:{node.module}")
    return sorted(set(out))


def try_load(code: str, entry: str, timeout: float) -> tuple[bool, bool, str]:
    """Compile + exec ONCE under a time limit. Returns (loadable, entry_defined, load_error)."""
    ns: dict = {}
    try:
        with _time_limit(timeout):
            exec(compile(code, "<candidate>", "exec"), ns)  # local static check only
    except _Timeout:
        return False, False, f"module-level execution exceeded {timeout}s (possible infinite loop at import time)"
    except SyntaxError as e:
        return False, False, f"syntax error: {e}"
    except Exception as e:  # noqa: BLE001
        return False, False, f"compile/exec error: {e!r}"
    entry_defined = bool(entry) and callable(ns.get(entry))
    return True, entry_defined, ""


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def _emit(obj: dict, out_path: str | None) -> int:
    text = json.dumps(obj, ensure_ascii=False, indent=2)
    sys.stdout.write("```json\n" + text + "\n```\n")
    if out_path:
        try:
            tmp = out_path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                f.write(text)
            os.replace(tmp, out_path)
        except OSError as e:
            sys.stderr.write(f"warning: could not write --out {out_path!r}: {e}\n")
    return 0  # ALWAYS 0 — report, not gate


def _chain_run_py(code_file: str, selftest_out: str, task_id: str, rationale: str, confidence: str) -> None:
    """Invoke the sibling run.py to write the result file. Path from __file__ = always correct."""
    run_py = os.path.join(os.path.dirname(os.path.abspath(__file__)), "run.py")
    if not os.path.exists(run_py):
        sys.stderr.write(f"warning: run.py not found next to selftest.py at {run_py!r}; result file NOT written\n")
        return
    cmd = [sys.executable, run_py,
           "--task_id", task_id,
           "--code-file", code_file,
           "--selftest-file", selftest_out,
           "--rationale", rationale,
           "--confidence", str(confidence)]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    sys.stdout.write(proc.stdout)
    if proc.returncode != 0:
        sys.stderr.write(proc.stderr)


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--code-file", "--code_file", dest="code_file", required=True)
    ap.add_argument("--entry", default="")
    ap.add_argument("--max-loc", "--max_loc", dest="max_loc", type=int, default=500)
    ap.add_argument("--imports-forbidden", "--imports_forbidden", dest="imports_forbidden", default="")
    ap.add_argument("--out", default="/tmp/ca_selftest.json")
    # Pass-through to run.py (if --task_id given, auto-chain to write the result file).
    ap.add_argument("--task_id", "--task-id", dest="task_id", default="")
    ap.add_argument("--rationale", default="")
    ap.add_argument("--confidence", default="0.5")
    a, _unknown = ap.parse_known_args(argv[1:])

    try:
        code = Path(a.code_file).read_text(encoding="utf-8")
    except OSError as e:
        _emit({
            "checks_passed": 0, "checks_failed": 5,
            "loadable": False, "entry_defined": False,
            "import_ok": False, "sandbox_ok": False, "loc_ok": False,
            "sloc": 0, "max_loc": a.max_loc,
            "import_violations": [], "sandbox_violations": [],
            "load_error": f"cannot read code file {a.code_file!r}: {e}",
            "all_clean": False,
        }, a.out)
        # Even on read failure, still try to write a result file if we have a task_id.
        if a.task_id:
            _chain_run_py(a.code_file, a.out, a.task_id, a.rationale, a.confidence)
        return 0

    forbidden = [s for s in a.imports_forbidden.split(",") if s.strip()]

    sloc = compute_sloc(code)
    loc_ok = sloc <= a.max_loc
    import_violations, parse_ok = _find_import_violations_with_parse_status(code, forbidden)
    sandbox_violations = find_sandbox_violations(code)
    loadable, entry_defined, load_error = try_load(code, a.entry, LOAD_TIMEOUT_SEC)

    # When syntax is broken we cannot trust the static import/sandbox scan -> mark not-ok.
    import_ok = parse_ok and not import_violations
    sandbox_ok = parse_ok and not sandbox_violations

    checks = {
        "loadable": loadable,
        "entry_defined": entry_defined,
        "import_ok": import_ok,
        "sandbox_ok": sandbox_ok,
        "loc_ok": loc_ok,
    }
    passed = sum(1 for v in checks.values() if v)
    failed = sum(1 for v in checks.values() if not v)

    _emit({
        "checks_passed": passed,
        "checks_failed": failed,
        **checks,
        "sloc": sloc,
        "max_loc": a.max_loc,
        "import_violations": import_violations,
        "sandbox_violations": sandbox_violations,
        "load_error": load_error,
        "all_clean": failed == 0,
    }, a.out)

    # Path-safe auto-chain: write the result file via the sibling run.py.
    if a.task_id:
        _chain_run_py(a.code_file, a.out, a.task_id, a.rationale, a.confidence)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
