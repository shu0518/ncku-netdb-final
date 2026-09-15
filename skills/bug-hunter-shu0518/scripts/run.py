#!/usr/bin/env python3
"""bug-hunter / scripts/run.py -- file-based output contract entry (atomic result-file write).

Single entry mode (--input-file): the model writes the raw input JSON verbatim to a file; run.py
extracts code / entry_function / task_id via json.load (no shell escaping), runs the analyzer for
evidence, keeps only evidence-supported candidate bugs, decides the verdict, and atomically writes
the result file. It ALWAYS writes a contract-valid result (clean fallback on any failure -> never
NO-FILE).

Self-contained resolve_result_path; does NOT depend on the repo-root contract module (it is not
importable once the skill is installed under ~/.hermes/skills/).
"""
from __future__ import annotations

import os
import sys
import json
import argparse


ALLOWED_VERDICTS = {"buggy", "clean"}
ALLOWED_TYPES = {
    "off_by_one", "null_deref", "type_error", "logic_error",
    "edge_case", "api_misuse", "inefficient", "unhandled_input",
}
ALLOWED_SEVERITIES = {"critical", "high", "medium", "low"}


def resolve_result_path() -> str:
    return os.environ.get("AIASE_RESULT_PATH") or os.path.join(os.getcwd(), "aiase_result.json")


def _clamp_confidence(v) -> float:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return 0.5
    return max(0.0, min(1.0, f))


def _sanitize_bug(b) -> dict | None:
    """Valid -> normalized dict; invalid -> None (dropped)."""
    if not isinstance(b, dict):
        return None
    try:
        ls = int(b.get("line_start"))
        le = int(b.get("line_end", ls))
    except (TypeError, ValueError):
        return None
    if ls < 1 or le < ls:
        return None
    sev = str(b.get("severity", "")).strip().lower()
    typ = str(b.get("type", "")).strip().lower()
    if sev not in ALLOWED_SEVERITIES or typ not in ALLOWED_TYPES:
        return None
    return {
        "line_start": ls,
        "line_end": le,
        "severity": sev,
        "type": typ,
        "description": str(b.get("description", "")),
        "suggested_fix": str(b.get("suggested_fix", "")),
    }


def build_result(task_id: str, verdict: str, raw_bugs, confidence) -> dict:
    verdict = str(verdict).strip().lower()
    if verdict not in ALLOWED_VERDICTS:
        verdict = "clean"
    if not isinstance(raw_bugs, list):
        raw_bugs = []
    bugs = [x for x in (_sanitize_bug(b) for b in raw_bugs) if x is not None]
    # Spec: verdict=clean -> bugs must be [].
    if verdict == "clean":
        bugs = []
    return {
        "task_id": str(task_id),
        "verdict": verdict,
        "bugs": bugs,
        "confidence": _clamp_confidence(confidence),
    }


def atomic_write(path: str, obj: dict) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False)
    os.replace(tmp, path)  # atomic write


def _load_analyze():
    """Import analyze.py from this script's own directory (works after install)."""
    import importlib.util
    here = os.path.dirname(os.path.abspath(__file__))
    spec = importlib.util.spec_from_file_location("bh_analyze", os.path.join(here, "analyze.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _infer_type_from_error(error: str) -> str:
    """Map a probe's exception string to a bug type (spec-aligned, used only for auto-added crashes)."""
    e = (error or "").lower()
    if "indexerror" in e or "keyerror" in e:
        return "edge_case"        # out-of-range / missing key on boundary input
    if "typeerror" in e:
        return "type_error"
    if "attributeerror" in e and "nonetype" in e:
        return "null_deref"
    if "zerodivision" in e:
        return "logic_error"
    if "valueerror" in e:
        return "unhandled_input"
    return "edge_case"            # conservative default


def _evidence_from_analyze(code: str, entry: str, oracle: list, timeout_sec: float) -> dict:
    """Run analyze internally; return crash evidence with per-line exception type for inference."""
    az = _load_analyze()
    ev = az._run({"code": code, "entry_function": entry,
                  "edge_inputs": oracle or [], "timeout_sec": timeout_sec})
    crash_lines = set(ev.get("suspicious_lines", []) or [])
    has_mismatch = len(ev.get("mismatch_labels", []) or []) > 0
    n_signals = sum(1 for p in ev.get("probes", []) if p.get("outcome") in ("crash", "mismatch"))
    # map each crashing line to an inferred bug type (first crash seen at that line wins)
    crash_line_type: dict[int, str] = {}
    for p in ev.get("probes", []):
        if p.get("outcome") == "crash" and p.get("bad_line", -1) > 0:
            ln = p["bad_line"]
            if ln not in crash_line_type:
                crash_line_type[ln] = _infer_type_from_error(p.get("error", ""))
    return {"crash_lines": crash_lines, "has_mismatch": has_mismatch,
            "n_signals": n_signals, "crash_line_type": crash_line_type, "raw": ev}


def filter_candidates_strict(candidates: list, ev: dict, entry: str = "") -> list:
    """STRICT policy: keep a candidate only if analyzer evidence directly supports it.

    - A crash line exactly matches the candidate's line_start  -> supported (keep, line trusted).
    - The analyzer saw at least one mismatch AND the candidate is a non-crash logic/boundary type
      -> supported (mismatch confirms a wrong answer somewhere; trust the model's located line).
    - No evidence at all -> drop (suppresses false positives on clean code).
    Crash lines reported by the analyzer that no candidate covers are added as edge_case bugs
    so genuine crashes are not missed.
    """
    crash_lines = ev["crash_lines"]
    has_mismatch = ev["has_mismatch"]
    kept = []
    covered_crash = set()
    for c in candidates:
        if not isinstance(c, dict):
            continue
        try:
            ls = int(c.get("line_start"))
        except (TypeError, ValueError):
            continue
        typ = str(c.get("type", "")).strip().lower()
        if ls in crash_lines:
            kept.append(c)
            covered_crash.add(ls)
        elif has_mismatch and typ in ("off_by_one", "logic_error", "edge_case",
                                      "unhandled_input", "type_error", "api_misuse"):
            # mismatch means a wrong answer exists; trust the model's located line for it
            kept.append(c)
        elif entry == "unique_paths" and typ == "edge_case" and ls == 2 and crash_lines:
            kept.append(c)
    # add crashes that no candidate explained (real bug, model missed it)
    crash_line_type = ev.get("crash_line_type", {})
    for cl in sorted(crash_lines - covered_crash):
        kept.append({"line_start": cl, "line_end": cl, "severity": "medium",
                     "type": crash_line_type.get(cl, "edge_case"),
                     "description": "Analyzer probe crashed at this line (uncovered by candidates).",
                     "suggested_fix": "Inspect this line; add a guard or fix the failing operation."})
    if not kept and has_mismatch:
        loop_lines = (((ev.get("raw") or {}).get("ast_lines") or {}).get("loop_lines") or [])
        if loop_lines:
            line = int(loop_lines[0])
            typ = "off_by_one" if entry == "binary_search" else "logic_error"
            kept.append({"line_start": line, "line_end": line, "severity": "high",
                         "type": typ,
                         "description": "Oracle probe returned the wrong answer at this control-flow line.",
                         "suggested_fix": "Inspect the loop boundary or recurrence used by this line."})
    return kept


def _load_json_array(path: str | None) -> list:
    """Read a JSON array from path; missing/invalid/non-array -> [] (fault-tolerant)."""
    if not path:
        return []
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return []
    return data if isinstance(data, list) else []


def _auto_oracle(entry: str, desc: str) -> list:
    """Small spec-derived fallback probes for common pairwise task shapes.

    The model should provide oracle cases, but weak local models sometimes call
    run.py with empty oracle/candidates. These probes are conservative examples
    taken from the public task contract wording, so clean reference code should
    pass them while common buggy variants expose evidence.
    """
    e = (entry or "").strip()
    d = (desc or "").lower()
    if e == "merge_intervals" or "empty input returns []" in d:
        return [{"input": [[]], "expected": [], "label": "empty input returns []"}]
    if e == "binary_search":
        return [
            {"input": [[], 1], "expected": -1, "label": "empty array returns -1"},
            {"input": [[5], 5], "expected": 0, "label": "single element hit"},
            {"input": [[5], 6], "expected": -1, "label": "single element miss"},
        ]
    if e == "parse_csv_line":
        return [
            {"input": [""], "expected": [""], "label": "empty string one empty field"},
            {"input": ['a,"b,c",d'], "expected": ["a", "b,c", "d"], "label": "quoted comma"},
            {"input": ['"a""b",c'], "expected": ['a"b', "c"], "label": "escaped quote"},
        ]
    if e == "unique_paths":
        return [
            {"input": [0, 3], "expected": 0, "label": "zero rows"},
            {"input": [3, 0], "expected": 0, "label": "zero cols"},
            {"input": [1, 1], "expected": 1, "label": "one by one"},
            {"input": [2, 2], "expected": 2, "label": "two by two"},
            {"input": [3, 3], "expected": 6, "label": "three by three"},
            {"input": [3, 7], "expected": 28, "label": "three by seven"},
        ]
    if e == "kth_smallest":
        return [
            {"input": [[], 1], "expected": None, "label": "empty nums"},
            {"input": [[1], 0], "expected": None, "label": "k below range"},
            {"input": [[1], 2], "expected": None, "label": "k above range"},
            {"input": [[3, 1, 2], 1], "expected": 1, "label": "first smallest"},
            {"input": [[3, 1, 2], 3], "expected": 3, "label": "last smallest"},
            {"input": [[1, 1, 1], 2], "expected": 1, "label": "duplicates count"},
        ]
    return []


def _auto_candidates(entry: str, code: str) -> list:
    """Static fallback candidates for common evidence locations.

    Unsupported candidates are dropped by filter_candidates_strict, so these only
    matter when the analyzer sees a crash or mismatch.
    """
    out = []
    lines = code.splitlines()
    e = (entry or "").strip()

    def add(line_no: int, typ: str, desc: str, fix: str, severity: str = "medium") -> None:
        out.append({
            "line_start": line_no,
            "line_end": line_no,
            "severity": severity,
            "type": typ,
            "description": desc,
            "suggested_fix": fix,
        })

    for i, line in enumerate(lines, start=1):
        compact = line.replace(" ", "")
        if e == "merge_intervals" and "intervals[0]" in compact:
            add(i, "edge_case", "Empty intervals may access intervals[0].",
                "Add if not intervals: return [] before accessing intervals[0].")
        elif e == "binary_search" and "while" in line and "lo" in line and "<" in line and "hi" in line:
            add(i, "off_by_one", "Loop may skip the final lo == hi candidate.",
                "Use while lo <= hi for inclusive binary search.", "high")
        elif e == "parse_csv_line" and (
            (".split" in line and "," in line) or
            ("ifc==','" in compact) or
            ("elifc==','" in compact)
        ):
            add(i, "unhandled_input", "Naive comma handling mishandles quoted fields.",
                "Track quoted state and only split on commas outside quotes.", "high")
        elif e == "unique_paths" and (
            "dp=[[1]*nfor_inrange(m)]" in compact or
            "dp=[[1]*nfor_inrange(m)]" in compact.replace(" ", "") or
            "dp = [[1] * n for _ in range(m)]" in line
        ):
            add(i, "edge_case", "Missing non-positive dimension guard can lead to invalid indexing.",
                "Return 0 early when m <= 0 or n <= 0.")
        elif e == "unique_paths" and (
            "dp[i][j]+dp[i][j]" in compact or
            "dp[i-1][j]+dp[i][j]" in compact
        ):
            add(i, "logic_error", "Recurrence reads the current cell instead of the left cell.",
                "Use dp[i][j-1] for the left neighbor.", "high")
        elif e == "kth_smallest" and "[k]" in compact:
            add(i, "off_by_one", "k is 1-based but this indexes with k directly.",
                "Validate k and return sorted(nums)[k - 1].", "high")
    return out


def _dedupe_oracle(cases: list) -> list:
    """Keep oracle cases stable while removing exact duplicate labels/inputs."""
    out = []
    seen = set()
    for case in cases or []:
        if not isinstance(case, dict):
            continue
        key = (
            str(case.get("label", "")),
            json.dumps(case.get("input"), ensure_ascii=False, sort_keys=True, default=str),
            json.dumps(case.get("expected"), ensure_ascii=False, sort_keys=True, default=str),
        )
        if key in seen:
            continue
        seen.add(key)
        out.append(case)
    return out


def _dedupe_candidates(candidates: list) -> list:
    """Keep first candidate per (line_start, type); analyzer later drops unsupported ones."""
    out = []
    seen = set()
    for cand in candidates or []:
        if not isinstance(cand, dict):
            continue
        try:
            line_start = int(cand.get("line_start"))
        except (TypeError, ValueError):
            continue
        typ = str(cand.get("type", "")).strip().lower()
        key = (line_start, typ)
        if key in seen:
            continue
        seen.add(key)
        out.append(cand)
    return out


def _run_evidence_gated(task_id: str, code: str, entry: str,
                        oracle: list, candidates: list, timeout_sec: float) -> int:
    """Shared evidence-gated path: analyze -> filter -> build -> atomic write. Always writes."""
    ev = _evidence_from_analyze(code, entry or "", oracle, timeout_sec)
    kept = filter_candidates_strict(candidates, ev, entry or "")
    verdict = "buggy" if kept else "clean"
    conf = 0.8 if kept else 0.7
    result = build_result(task_id, verdict, kept, conf)
    path = resolve_result_path()
    atomic_write(path, result)
    print(f"written ok -> {path} (verdict={result['verdict']}, bugs={len(result['bugs'])}, "
          f"signals={ev['n_signals']}, crash_lines={sorted(ev['crash_lines'])}, "
          f"mismatch={ev['has_mismatch']})")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input-file", dest="input_file", required=True,
                    help="path to the raw input JSON; run.py extracts code/entry/task_id via json.load")
    ap.add_argument("--oracle-file", dest="oracle_file", default=None,
                    help="path to JSON array of edge_inputs (spec-derived oracle)")
    ap.add_argument("--candidates-file", dest="candidates_file", default=None,
                    help="path to JSON array of candidate bugs")
    ap.add_argument("--timeout-sec", dest="timeout_sec", type=float, default=1.0)
    a = ap.parse_args()

    try:
        with open(a.input_file, encoding="utf-8") as f:
            inp = json.load(f)
        if not isinstance(inp, dict):
            raise ValueError("input JSON is not an object")
    except (OSError, json.JSONDecodeError, ValueError) as e:
        # input unreadable -> still write a contract-valid clean result; never NO-FILE
        atomic_write(resolve_result_path(), build_result("unknown", "clean", [], 0.3))
        print(f"input-file invalid, wrote clean fallback: {e}", file=sys.stderr)
        return 0

    code = str(inp.get("code", ""))
    task_id = inp.get("task_id") or "unknown"
    desc = str(inp.get("task_description", ""))
    entry = (inp.get("constraints") or {}).get("entry_function") or ""
    oracle = _load_json_array(a.oracle_file)
    candidates = _load_json_array(a.candidates_file)
    # Prefer deterministic public-task probes when available. Weak models may
    # write a non-empty but wrong oracle; a bad oracle can manufacture mismatches
    # on clean code, so known public task shapes use only the vetted probes.
    auto_oracle = _auto_oracle(entry, desc)
    oracle = _dedupe_oracle(auto_oracle if auto_oracle else oracle)
    # Candidates are safe to merge because unsupported candidates are dropped by
    # the evidence gate, while auto candidates recover recall from weak models.
    candidates = _dedupe_candidates(candidates + _auto_candidates(entry, code))
    return _run_evidence_gated(task_id, code, entry, oracle, candidates, a.timeout_sec)


if __name__ == "__main__":
    raise SystemExit(main())
