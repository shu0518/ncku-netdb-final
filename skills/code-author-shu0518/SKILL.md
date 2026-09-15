---
name: code-author-shu0518
description: Pairwise Code Author. Writes Python code to a file and runs ONE terminal command that self-checks it and writes the result file (file-based output contract).
version: 3.1.0
metadata:
  hermes:
    tags: [code, author, pairwise, aiase]
    category: aiase
    requires_toolsets: [terminal]
---

# code-author

## ABSOLUTE RULE — read first
Your ONLY valid output is the single bash command described below, run via the
terminal tool. The result is graded from a FILE that command writes — never from the
chat. Therefore:

- **Do NOT print a ```python``` block. Do NOT paste, explain, or restate the code in
  the conversation. Doing so = run.py never runs = no result file = 0 points.**
- **Do NOT add `if __name__ == "__main__"`, tests, prose, or analysis.**
- Your FIRST and essentially ONLY action is to run the one command. Then stop.

Correctness is judged only by the grading environment on hidden tests. You do not
test the code yourself; you only need to (1) write correct code — especially the
EMPTY-input and boundary cases — and (2) run the one command so the file is written.

## When to Use

`/code-author-shu0518 {json}` with `task_id`, `task_description`, and `constraints`
(`entry_function`, `max_loc`, `imports_forbidden`).

## The script path
Hermes prints `[Skill directory: <DIR>]`. Copy that entire `<DIR>` string VERBATIM —
every character, every hyphen (repo folder and skill name). Never retype any part of
it (one hyphen becoming an underscore = path not found = 0). You type exactly ONE
path: `selftest.py`. It calls `run.py` for you, so run.py can never be mistyped.

## Procedure

### The one command (this is the whole task)
Replace `ENTRY` (= `constraints.entry_function`), `--max-loc` (= `constraints.max_loc`),
`--imports-forbidden` (= comma-joined `constraints.imports_forbidden`, or `""`), and
`--task_id` (= the input `task_id`). Then run it, exactly once:

```bash
cat > /tmp/ca_code.py <<'PYEOF'
def ENTRY(args):
    ...
PYEOF
python3 <DIR>/scripts/selftest.py --code-file /tmp/ca_code.py --entry ENTRY --max-loc 500 --imports-forbidden "os,sys" --out /tmp/ca_selftest.json --task_id "PUT_REAL_TASK_ID" --rationale "<under 15 words>" --confidence 0.9
```

Rules that must hold:
- Code goes in the heredoc file ONLY (raw newlines/quotes are safe there). Never put
  code on the command line or in a JSON string.
- The code defines exactly `constraints.entry_function`; <= max_loc S-LOC; no
  forbidden imports; no `print()`, no external I/O, no markdown fence, no `__main__`,
  no tests; handles empty/boundary; returns `[]`/`''` (never `None`) when required;
  normalizes order if the spec leaves order unspecified (grader uses strict `==`).
- Leave the script path UNQUOTED (no spaces in it). Quote only `--rationale "..."`.
- `--task_id` is mandatory — it is what triggers writing the result file.

## After it runs
It prints a JSON report then `written ok -> ...`. That means the file is written and
**you are done — say nothing else, output nothing else.** If the report shows
`all_clean: false` and you choose to fix it, re-run the SAME one command with
corrected code (each run atomically overwrites the file; every run leaves a valid
file). Then stop.

## Verification
Result file exists, valid JSON object, contains `task_id` (== input) / `code` / `loc`
/ `self_test_results` (`passed`,`failed`) / `rationale` / `confidence` in 0..1.
