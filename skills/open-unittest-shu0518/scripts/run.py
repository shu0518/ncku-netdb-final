#!/usr/bin/env python3
"""run.py — open-unittest-shu0518 grading-time harness (file-based output).

Called by the skill (via the terminal toolset) as:
    python3 <SKILL_DIR>/scripts/run.py --task-file T.json --tests-file TESTS.py

- T.json     : the task input the skill received (task_id, entry_function, code).
- TESTS.py   : the unit tests the LLM generated (raw Python, `test_*()` funcs).

It runs the deterministic verifier (muteval) and ATOMICALLY writes the result
JSON to $AIASE_RESULT_PATH (fallback ./aiase_result.json). The grader reads that
file; nothing needs to be printed to the chat.

Robustness: it ALWAYS writes a schema-valid result file (even when the build or
tests fail) and ALWAYS exits 0, so the agent never loops retrying — it just
finishes the turn. Missing result file = 0, so writing something is mandatory.

Does NOT depend on the repo-root contract module (not importable once installed under
~/.hermes/skills/). The tiny write-file helper is inlined per the file-based spec.
"""
from __future__ import annotations

import os
import sys
import json
import argparse
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # sibling import
import muteval  # noqa: E402


def resolve_result_path(default_name: str = "aiase_result.json") -> str:
    """Result path: prefer env AIASE_RESULT_PATH, else cwd/default_name."""
    return os.environ.get("AIASE_RESULT_PATH") or os.path.join(os.getcwd(), default_name)


def atomic_write_json(path: str, obj: dict) -> None:
    """Write JSON atomically (temp file + os.replace) so the grader never reads
    a half-written file."""
    d = os.path.dirname(os.path.abspath(path)) or "."
    os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=d, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def load_task(path: str) -> dict:
    """Parse the task JSON, tolerating the common ways a weak model corrupts a
    re-typed JSON string when writing it into a heredoc:
      (a) a `\\n` escape rewritten as a literal backslash + real newline
          (json raises 'Invalid \\escape'); and
      (b) bare unescaped control chars (newline/tab) left inside a string value
          (json raises 'Invalid control character').
    Strict parse is tried first; repairs are applied only if it fails."""
    with open(path, encoding="utf-8") as f:
        raw = f.read().lstrip("\ufeff")
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    # (a) backslash directly followed by a line break -> proper \n escape
    fixed = (raw.replace("\\\r\n", "\\n").replace("\\\n", "\\n").replace("\\\r", "\\n"))
    try:
        return json.loads(fixed)
    except json.JSONDecodeError:
        pass
    # (b) escape any remaining raw control chars inside the (single-line) JSON
    repaired = (fixed.strip().replace("\r\n", "\\n").replace("\n", "\\n")
                .replace("\r", "\\n").replace("\t", "\\t"))
    return json.loads(repaired)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--task-file", required=True, help="task input JSON")
    ap.add_argument("--tests-file", required=True, help="generated tests (.py)")
    a = ap.parse_args()

    result_path = resolve_result_path()

    # Resolve task_id even if everything else fails, so the result file is valid.
    task_id, entry, ref_src = "", "", ""
    err = ""
    try:
        task = load_task(a.task_file)
        task_id = str(task.get("task_id", ""))
        entry = str(task.get("entry_function") or task.get("entry") or "")
        ref_src = task.get("code") or task.get("source") or ""
    except Exception as e:
        err = f"task parse failed: {type(e).__name__}: {e}"

    test_src = ""
    if not err:
        try:
            with open(a.tests_file, encoding="utf-8") as f:
                test_src = f.read()
        except Exception as e:
            err = f"tests read failed: {type(e).__name__}: {e}"

    result = {
        "task_id": task_id,
        "entry_function": entry,
        "tests": test_src,
        "self_report": {},
        "error": err,
    }

    if not err and ref_src.strip():
        try:
            result["self_report"] = muteval.evaluate(ref_src, test_src)
        except Exception as e:
            result["error"] = f"evaluate failed: {type(e).__name__}: {e}"
    elif not err:
        result["error"] = "missing reference code in task"

    atomic_write_json(result_path, result)

    sr = result.get("self_report", {})
    print(f"[open-unittest] task={task_id} wrote {result_path} "
          f"mutation_score={sr.get('mutation_score')} "
          f"pass_on_ref={sr.get('tests_pass_on_reference')} "
          f"coverage={sr.get('coverage_pct')}")
    return 0  # always succeed so the agent does not retry-loop


if __name__ == "__main__":
    sys.exit(main())
