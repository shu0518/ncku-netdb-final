#!/usr/bin/env python3
"""bug-hunter analyzer -- deterministic evidence module (crash detection + spec-oracle differential testing).

Used as a module by scripts/run.py (imported, then `_run(payload)` called); it returns an evidence
dict and does NOT write the result file (that is run.py's job).

payload:
  {
    "code": "<python source>",
    "entry_function": "<name>",
    "edge_inputs": [                       # spec-derived oracle (from the skill)
      {"input": [[]],    "expected": [],   "label": "empty"},   # with expected -> differential test
      {"input": [[5],5], "label": "crash probe only"}           # without expected -> crash check only
    ],
    "timeout_sec": 1.0
  }

Returns:
  {"entry_found", "arity", "ast_lines", "probes", "suspicious_lines", "mismatch_labels", "summary"}
"""
from __future__ import annotations

import ast
import signal
import traceback
from contextlib import contextmanager


def _ast_features(code: str, entry: str) -> tuple[dict, int]:
    """Return (ast_lines, arity). arity = number of positional params of entry, -1 if not found."""
    out = {"entry_def": -1, "return_lines": [], "loop_lines": []}
    arity = -1
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return out, arity
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == entry:
            out["entry_def"] = node.lineno
            a = node.args
            arity = len(a.posonlyargs) + len(a.args)  # excludes *args/**kwargs/keyword-only
        if isinstance(node, ast.Return) and node.lineno:
            out["return_lines"].append(node.lineno)
        if isinstance(node, (ast.For, ast.While)) and node.lineno:
            out["loop_lines"].append(node.lineno)
    out["return_lines"].sort()
    out["loop_lines"].sort()
    return out, arity


class _Timeout(Exception):
    pass


@contextmanager
def _time_limit(seconds: float):
    """SIGALRM-based timeout (POSIX). No limit on non-POSIX platforms."""
    if not hasattr(signal, "SIGALRM"):
        yield
        return

    def _handler(signum, frame):
        raise _Timeout("probe timed out")

    old = signal.signal(signal.SIGALRM, _handler)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, old)


def _call(fn, args):
    """list -> positional expansion; non-list -> single argument."""
    return fn(*args) if isinstance(args, list) else fn(args)


def _probe(code: str, entry: str, sample: dict, timeout_sec: float) -> dict:
    label = sample.get("label", "?")
    has_expected = "expected" in sample
    ns: dict = {}
    try:
        exec(compile(code, "<candidate>", "exec"), ns)
    except Exception as e:
        return {"label": label, "outcome": "crash",
                "error": f"compile/exec error: {e!r}"}
    fn = ns.get(entry)
    if not callable(fn):
        return {"label": label, "outcome": "crash",
                "error": f"entry function {entry!r} not defined"}
    args = sample.get("input", [])
    try:
        with _time_limit(timeout_sec):
            got = _call(fn, args)
    except _Timeout as e:
        return {"label": label, "outcome": "timeout", "error": str(e)}
    except Exception as e:
        tb = traceback.extract_tb(e.__traceback__)
        bad_line = -1
        for f in tb:
            if f.filename == "<candidate>" and f.lineno:
                bad_line = f.lineno  # take the deepest frame inside candidate
        out = {"label": label, "outcome": "crash", "error": f"{type(e).__name__}: {e}"}
        if bad_line > 0:
            out["bad_line"] = bad_line
        return out
    # no crash: if expected was given, compare
    if has_expected:
        expected = sample.get("expected")
        if got != expected:
            return {"label": label, "outcome": "mismatch",
                    "got": repr(got), "expected": repr(expected)}
    return {"label": label, "outcome": "ok"}


def _run(payload: dict) -> dict:
    code = str(payload.get("code", ""))
    entry = str(payload.get("entry_function", ""))
    timeout_sec = float(payload.get("timeout_sec", 1.0))

    ast_lines, arity = _ast_features(code, entry)
    entry_found = ast_lines.get("entry_def", -1) > 0

    # Only spec-derived oracle inputs are trusted: an empty oracle yields no probes, so clean code
    # is never hit with spec-out-of-range inputs that would manufacture false crashes.
    samples = payload.get("edge_inputs") or []

    probes = []
    suspicious: set[int] = set()
    mismatch_labels: list[str] = []
    for s in samples:
        r = _probe(code, entry, s, timeout_sec)
        probes.append(r)
        if r["outcome"] == "crash" and r.get("bad_line", -1) > 0:
            suspicious.add(r["bad_line"])
        if r["outcome"] == "mismatch":
            mismatch_labels.append(r["label"])

    crashes = sum(1 for r in probes if r["outcome"] == "crash")
    mismatches = sum(1 for r in probes if r["outcome"] == "mismatch")
    timeouts = sum(1 for r in probes if r["outcome"] == "timeout")
    oks = len(probes) - crashes - mismatches - timeouts
    summary = (
        f"arity={arity}; {len(probes)} probes; "
        f"{crashes} crash, {mismatches} mismatch, {timeouts} timeout, {oks} ok; "
        f"suspicious_lines={sorted(suspicious)}; mismatch={mismatch_labels}"
    )
    return {
        "entry_found": entry_found,
        "arity": arity,
        "ast_lines": ast_lines,
        "probes": probes,
        "suspicious_lines": sorted(suspicious),
        "mismatch_labels": mismatch_labels,
        "summary": summary,
    }