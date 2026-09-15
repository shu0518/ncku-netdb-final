#!/usr/bin/env python3
"""score.py — standalone deterministic evaluator for open-unittest-shu0518.

This is the metric of record (declared in OPEN_TRACK.md). It RE-COMPUTES the
score from the task's reference code + the generated tests, independent of
whatever `self_report` the skill wrote — so a skill cannot win by writing an
inflated self_report. Staff (and you, locally) run this to grade a result file.

Usage:
    # grade a written result file against its task
    python3 score.py --task-file task.json --result-file aiase_result.json

    # grade a tests file directly against a task
    python3 score.py --task-file task.json --tests-file tests.py

    # run all bundled public scenarios as a self-test
    python3 score.py --self-test

A task PASSES when:
    tests_pass_on_reference is True   (tests are correct wrt the reference), AND
    mutation_score >= PASS_THRESHOLD  (tests actually detect behaviour changes).

`scenario_score` (0..1, used for the 70% performance component) = mutation_score
when tests pass on the reference, else 0.0 (tests that fail on correct code are
not trustworthy and earn nothing).
"""
from __future__ import annotations

import os
import sys
import json
import glob
import argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import muteval  # noqa: E402

PASS_THRESHOLD = 0.70  # min mutation score to count the scenario as passed


def grade(ref_src: str, test_src: str) -> dict:
    r = muteval.evaluate(ref_src, test_src)
    passed = bool(r["tests_pass_on_reference"]) and r["mutation_score"] >= PASS_THRESHOLD
    scenario_score = r["mutation_score"] if r["tests_pass_on_reference"] else 0.0
    return {
        "passed": passed,
        "scenario_score": round(scenario_score, 4),
        "tests_pass_on_reference": r["tests_pass_on_reference"],
        "mutation_score": r["mutation_score"],
        "mutants_killed": r["mutants_killed"],
        "mutants_total": r["mutants_total"],
        "coverage_pct": r["coverage_pct"],
        "n_tests": r["n_tests"],
        "build_error": r["build_error"],
        "surviving_mutants": r["surviving_mutants"],
    }


def _read(path: str) -> str:
    with open(path, encoding="utf-8") as f:
        return f.read()


def _task_code(task: dict) -> str:
    return task.get("code") or task.get("source") or ""


def self_test() -> int:
    here = os.path.dirname(os.path.abspath(__file__))
    files = sorted(glob.glob(os.path.join(here, "examples", "*.json")))
    if not files:
        print("no example scenarios found", file=sys.stderr)
        return 2
    total = 0.0
    n_pass = 0
    for p in files:
        task = json.loads(_read(p))
        ref = _task_code(task)
        tests = task.get("reference_tests", "")
        if not tests:
            print(f"[SKIP] {task.get('task_id')}: example has no reference_tests")
            continue
        g = grade(ref, tests)
        total += g["scenario_score"]
        n_pass += int(g["passed"])
        print(f"[{'PASS' if g['passed'] else 'FAIL'}] {task['task_id']}: "
              f"mutation={g['mutation_score']} "
              f"({g['mutants_killed']}/{g['mutants_total']}) "
              f"cov={g['coverage_pct']}% pass_on_ref={g['tests_pass_on_reference']}"
              + (f" survivors={g['surviving_mutants']}" if g['surviving_mutants'] else ""))
    n = len(files)
    print(f"\nScenarios: {n_pass}/{n} passed; mean scenario_score={total / n:.3f}")
    return 0 if n_pass == n else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--task-file")
    ap.add_argument("--result-file")
    ap.add_argument("--tests-file")
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args()

    if a.self_test:
        return self_test()

    if not a.task_file:
        ap.error("--task-file required (unless --self-test)")
    task = json.loads(_read(a.task_file))
    ref = _task_code(task)
    if not ref.strip():
        print(json.dumps({"passed": False, "error": "task has no reference code"}))
        return 2

    if a.tests_file:
        tests = _read(a.tests_file)
    elif a.result_file:
        res = json.loads(_read(a.result_file))
        if res.get("task_id") != task.get("task_id"):
            print(json.dumps({"passed": False, "error": "task_id mismatch"}))
            return 2
        tests = res.get("tests", "")
    else:
        ap.error("provide --tests-file or --result-file")

    verdict = grade(ref, tests)
    verdict["task_id"] = task.get("task_id")
    print(json.dumps(verdict, ensure_ascii=False, indent=2))
    return 0 if verdict["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())