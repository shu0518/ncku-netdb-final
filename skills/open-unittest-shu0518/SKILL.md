---
name: open-unittest-shu0518
description: >-
  Generate a battery of unit tests for a given Python function. Use when the
  input JSON contains an `entry_function` name and its `code` (source of a single
  Python function) and asks for unit tests. The skill writes `test_*()` assertion
  functions that pin the function's behaviour, then runs a deterministic harness
  (scripts/run.py) that checks the tests pass on the reference implementation,
  measures line coverage, and computes a mutation-kill score. Result is written
  to a file (AIASE_RESULT_PATH), not printed to chat.
version: 0.1.0
category: testing
license: MIT
---

# open-unittest-shu0518 — Verifiable Unit-Test Generation

Given a Python function, produce unit tests strong enough to **detect behaviour
changes** in it. Quality is measured by mutation testing: tests must pass on the
correct (reference) code and fail on automatically mutated variants. Coverage or
trivial `assert True` tests do not score.

## When to Use

Trigger when the input JSON has `entry_function` (a function name) and `code`
(the source defining that function), optionally a `description`/`spec`. The task
is: write unit tests for that function.

## Input

A single JSON object passed on the slash command, e.g.:

```json
{"task_id": "open_ut_clamp", "entry_function": "clamp",
 "description": "Clamp x into [lo, hi]; if lo > hi the bounds are swapped.",
 "code": "def clamp(x, lo, hi):\n    if lo > hi:\n        lo, hi = hi, lo\n    if x < lo:\n        return lo\n    if x > hi:\n        return hi\n    return x\n"}
```

Fields you must read: `task_id`, `entry_function`, `code`. `description` (or
`spec`) is guidance for what correct behaviour is.

## How to write good tests (what actually scores)

The harness mutates the reference code (swaps `+`/`-`, `<`/`>=`, `and`/`or`,
flips constants, etc.) and counts how many mutants your tests catch. To score:

- Call `entry_function` **directly by name** and assert on its **return value**
  (or raised exception). Reference code and your tests run in one namespace, so
  the function is already defined — do **not** import or redefine it.
- Cover **every branch and boundary**: each `if`/`elif`/`else`, each comparison
  edge (e.g. for `>= 90` test 89, 90, 91), empty/typical/extreme inputs.
- Make assertions **exact** (`== 5`, `is True`), never `assert True` or a bare
  call with no assertion — those catch no mutants and score 0.
- All your tests must **pass on the given (correct) reference code**. Tests that
  fail on the reference are treated as wrong and earn nothing.
- 5–10 focused tests is usually enough; one assertion per behaviour is clearer
  than many in one test.

## Procedure

Do all of this in **one** terminal command (a single `bash` tool call). This
avoids shell-quoting failures and means the harness runs once, deterministically.
Hermes prints the skill's absolute directory as `[Skill directory: /abs/path]`
when the skill loads — use that path for `scripts/run.py`.

1. Read `task_id`, `entry_function`, `code`, `description` from the input JSON.
2. Design `test_*()` functions per the guidance above (raw Python).
3. Run the single command below, substituting:
   - the **exact input JSON** you received between the `TASK_EOF` markers, and
   - **your generated tests** (raw Python, real newlines) between the
     `TESTS_EOF` markers, and
   - `<SKILL_DIR>` with the absolute skill directory Hermes printed.

```bash
cat > /tmp/aiase_ut_task.json <<'TASK_EOF'
{...paste the EXACT input JSON object here...}
TASK_EOF
cat > /tmp/aiase_ut_tests.py <<'TESTS_EOF'
def test_<name>():
    assert <entry_function>(<args>) == <expected>
# ... more test_*() functions ...
TESTS_EOF
python3 "<SKILL_DIR>/scripts/run.py" --task-file /tmp/aiase_ut_task.json --tests-file /tmp/aiase_ut_tests.py
```

Notes that make this robust:
- Both heredocs are **single-quoted** (`'TASK_EOF'`, `'TESTS_EOF'`): the body is
  written verbatim with no shell expansion. The tests are plain Python with real
  newlines — there is **no JSON string to escape**.
- Paste the input JSON **exactly as you received it, on a single line**. Do not
  reflow, re-indent, or pretty-print it, and do not turn `\n` inside the `code`
  string into real line breaks — keep every `\n` as the two characters `\` `n`.
  (`run.py` auto-repairs the most common slip where `\n` becomes a backslash +
  real newline, but writing it verbatim avoids the problem entirely.)
- `run.py` always writes a valid result file and exits 0, even if your tests have
  an error. Read the printed `mutation_score` / `pass_on_ref`. If
  `pass_on_ref` is `False` or `mutation_score` is low, you may rewrite
  `/tmp/aiase_ut_tests.py` and re-run the `python3 ...` line **once** to improve
  — but do not loop indefinitely; a written result is better than none.

## Output (file-based)

`scripts/run.py` writes the result JSON to `AIASE_RESULT_PATH` (fallback
`./aiase_result.json`) atomically. **Do not print the result JSON in chat.**
The result schema:

```json
{
  "task_id": "<same as input>",
  "entry_function": "clamp",
  "tests": "<the generated test source>",
  "self_report": {
    "tests_pass_on_reference": true,
    "coverage_pct": 100.0,
    "mutants_total": 3,
    "mutants_killed": 3,
    "mutation_score": 1.0
  },
  "error": ""
}
```

`task_id` in the output always equals `task_id` in the input.

## Verification

`scripts/run.py` (harness) and `scripts/score.py` (standalone evaluator) share
`scripts/muteval.py`, a stdlib-only deterministic verifier:
- builds `reference code + your tests` into one module and runs every `test_*()`;
- a scenario only counts if **all** tests pass on the reference;
- generates single-point AST mutants of the reference and re-runs the tests;
- `mutation_score = mutants_killed / mutants_total`.

Self-test the metric on the bundled public scenarios:

```bash
python3 scripts/score.py --self-test
```

Grade one result file the way staff do (recomputes from your tests, not from
`self_report`):

```bash
python3 scripts/score.py --task-file scripts/examples/s1_clamp.json \
                         --result-file aiase_result.json
```

## Dependencies

`scripts/requirements.txt` — none beyond the Python standard library (Python ≥ 3.9
for `ast.unparse`). No network, no MCP, no absolute paths.
