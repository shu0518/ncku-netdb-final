# Verifiable Skills for the Hermes Agent

> Three Hermes agent skills (Basic Text2SQL, Pairwise Code-Author/Bug-Hunter, Open Track unit-test generator) built around one shared contract: a skill's last action is always a script that writes the result to a file, so grading never depends on parsing the model's conversational output.

`Course project` · Netdb Lab, NCKU · AIASE 2026 · Individual
**Stack:** Python · Hermes agent framework · pytest · AST-based mutation testing (stdlib only)

## Overview

Each of the three tracks pairs a `SKILL.md` procedure (what the model should do) with a `scripts/` harness (what actually gets checked). Basic Track (`text2sql-shu0518`) makes the model enumerate the schema before emitting one read-only SQL statement. Pairwise Track submits both roles: `code-author-shu0518` writes candidate code and routes it through `scripts/selftest.py` before scoring, and `bug-hunter-shu0518` only reports a bug when its analyzer finds crash or mismatch evidence, defaulting to `clean` otherwise. Open Track (`open-unittest-shu0518`) generates unit tests for a given Python function and scores them by mutation testing rather than coverage. In every track, the skill's final step calls `scripts/run.py`, which writes the result to `$AIASE_RESULT_PATH`; the grader reads that file, not the chat transcript.

## Key Design Decisions

| Decision | Rationale |
| --- | --- |
| File-based output contract (`scripts/run.py` -> `$AIASE_RESULT_PATH`) instead of trailing fenced JSON in chat | Early Text2SQL relied on a fenced JSON block at the end of the conversation; the model sometimes ran the script correctly but then appended its own SQL or prose, so the grader found no valid trailing JSON (see Challenges) |
| `text2sql-shu0518` forbids CTEs, window functions, multi-statement SQL, and DDL/DML | Keeps the output space small enough to verify deterministically, and matches the read-only, single-statement assumption the grader checks against |
| `bug-hunter-shu0518` is evidence-gated: a bug is only reported when the analyzer finds crash or mismatch evidence | Defaults to `clean` instead of a guessed bug report, which lowers false positives compared to letting the model report on intuition |
| `open-unittest-shu0518` is scored by mutation score, not coverage | Measured directly: an assert-free test suite that only calls the function under test reached 85.71% line coverage but killed zero mutants (`mutation_score = 0`) — coverage alone doesn't prove the tests catch bugs |
| `code-author-shu0518` routes candidate code through `scripts/selftest.py` (checks S-LOC, forbidden imports, sandbox risk) before `run.py` | Avoids the model hand-typing `loc` or test counts into the result schema, which is a source of schema errors if done manually |

## Challenges

**Problem.** The original Text2SQL skill asked the model to end its turn with a fenced JSON block. In practice, the model sometimes called the script and got a correct answer, then appended its own SQL or an English explanation afterward — the grader's log showed `no valid fenced JSON in stdout`, or found a ` ```sql ` block where it expected ` ```json `. The SQL itself wasn't wrong; the output contract was.
**Approach.** Rewrote all three tracks so the skill's last action is always `scripts/run.py`, which writes the result to `$AIASE_RESULT_PATH` and is the only thing the grader reads — the conversational transcript is no longer scored.
**Result.** This removed the "unstable conversational contract" failure mode across Basic, Pairwise, and Open Track at once, since all three now share the same file-based contract (`aiase_contract.py`).

## Limitations

- Local development testing under-measures quality: a 12B model on 12GB VRAM offloads to CPU, and simple single-table Text2SQL queries were observed taking ~66s locally with some dev-set items hitting a 120s timeout that the actual grading gateway would not hit.
- `bug-hunter-shu0518`'s oracle still depends on the model deriving expected behavior from the task description; there's no structured parser yet to auto-generate empty/boundary/out-of-range cases (noted as a TODO in `report.md`).
- Mutation operators in `open-unittest-shu0518` cover arithmetic, comparison, boolean, and constant flips only — list slicing, loop-boundary, and dict-key mutations aren't implemented yet.
- The Open Track pass threshold (`mutation_score >= 0.70`) is a single fixed value applied to every function regardless of its branching complexity.

## Running It

```bash
python -m pip install -r requirements.txt
hermes skills list                                    # confirm skills are visible

# Smoke test
AIASE_RESULT_PATH=/tmp/hello_probe.json \
hermes chat --toolsets skills,terminal --yolo -Q \
  -q '/hello-aiase {"task_id":"probe","name":"shu"}'

# Basic Track
python dev_set/basic/build_dbs.py
python3 run_dev.py --skill text2sql-shu0518 --track basic --dev-dir dev_set/basic

# Pairwise Track
python3 grade_bughunter_local.py --skill bug-hunter-shu0518

# Open Track
bash verify_open.sh

# Repo gate (structure / schema / no hardcoded tokens or paths)
python3 verify_repo.py --github-id shu0518
python3 -m pytest -q
```

## Structure

    skills/text2sql-shu0518/        Basic Track: schema-grounded, single-statement, read-only SQL
    skills/code-author-shu0518/     Pairwise: candidate code -> scripts/selftest.py -> run.py
    skills/bug-hunter-shu0518/      Pairwise: evidence-gated bug reports (crash/mismatch required)
    skills/open-unittest-shu0518/   Open Track: unit-test generator, scored by mutation testing
    dev_set/basic/                  20 Text2SQL dev tasks with answers + build_dbs.py
    dev_set/pairwise/reference_tasks/   5 reference task pairs with ground-truth bug annotations
    aiase_contract.py, run_dev.py   Shared file-based output contract + local test driver
