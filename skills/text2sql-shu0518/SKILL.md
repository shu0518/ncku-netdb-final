---
name: text2sql-shu0518
description: Convert a natural-language question + SQLite schema into a verified read-only SQL query, then write the result via scripts/run.py (file-based output contract). AIASE 2026 Basic Track.
version: 0.5.0
metadata:
  hermes:
    tags: [sql, text2sql, data, aiase-2026]
    category: data
    requires_toolsets: [terminal]
---

# Text2SQL Skill (Basic Track)

## When to Use

When the user sends a JSON payload with `question`, `db_schema` (SQLite DDL), and optional `task_id` + `dialect`. Produce one read-only SQLite query whose result on the hidden DB matches the gold answer under bag (multiset) equality.

Trigger example:

```
/text2sql-shu0518 {"task_id":"task_nl2sql_017",
  "question":"List the names of all students who scored above 90 ...",
  "db_schema":"CREATE TABLE Students(...); ...", "dialect":"sqlite"}
```

## Hard rules (read before anything else)

- **RULE 1 — ONE command form, never improvise.** You call `run.py` with argv flags
  (step 5 below). If the command errors, fix the **SQL content** and re-run the
  **same form** at most once. Do NOT switch to heredoc, `echo |`, `python3 -c`,
  temp files, or any other approach. Changing invocation form is what causes
  agent spirals and timeouts.

- **RULE 2 — After `run.py` exits, you are done.** `run.py` writes the result file
  silently. Do NOT output any JSON block, SQL block, summary, or prose after it.
  The grader reads the file — not the conversation.

## Procedure

Steps 1–4 happen **in your reasoning** (no commands). Step 5 is the **single**
terminal command you run.

**TIME CONTROL:** Keep reasoning tight. Do the schema inventory in step 2 (prevents
wrong-column errors), then draft SQL directly. Skip verbose narration and do not
list multiple candidate queries to compare.

1. **Parse** the payload: `task_id`, `question`, `db_schema`, `dialect`.

2. **Inventory the schema BEFORE writing any SQL.** From `db_schema`, confirm:
   - every table name (verbatim, correct casing);
   - the exact column names of each table (verbatim from the DDL — no guessing);
   - **Explicit PK/FK relations only.** Identify the declared join keys. Do NOT
     invent join conditions. Missing an explicit key causes a Cartesian product
     that inflates rows and triggers bag-equality failure.

3. **Map the question onto the schema, then draft ONE query.** Decide:
   - which tables are needed and how they join (only verified keys from step 2);
   - filters (`WHERE` for rows, `HAVING` for groups);
   - whether an aggregate / GROUP BY is required;
   - **DISTINCT Decision (two-way trap):**
     * Distinct entities / unique categories / set semantics ("which departments",
       "distinct names", "students who scored above 90 in *any* course") → **MUST
       use DISTINCT**.
     * Transactional history / running logs / records where duplicates are valid
       → **DO NOT use DISTINCT**.
     * `validate_sql.py` has no data and **cannot** catch wrong-DISTINCT errors —
       you must decide correctly here.

4. **Self-check the draft** (in reasoning, before running):
   - every column/table appears verbatim in step 2's list;
   - every JOIN uses a validated PK/FK key (no Cartesian product risk);
   - no `WITH`/CTE, no window functions (`OVER`), no recursion (SQLite Basic envelope);
   - exactly one statement, read-only;
   - DISTINCT logic matches the question semantics.

5. **Run ONE terminal command** using the **absolute path** Hermes provides in
   `[Skill directory: /abs/path]` (copy that path verbatim — do not hardcode or
   search for it). Use the `terminal` tool (not `process` or background tools):

   ```
   python3 <skill_dir>/scripts/run.py \
     --task_id "<input task_id>" \
     --sql "<your SQL, single line>" \
     --rationale "<strictly under 10 words, no newlines>" \
     --confidence <0.0..1.0>
   ```

   `run.py` atomically writes the result file to `AIASE_RESULT_PATH` (or
   `./aiase_result.json` if unset) and prints `written ok -> <path>`.

   Handle the outcome:
   - **`written ok`** → done. Per RULE 2, stop immediately.
   - **Any Python error / non-zero exit** → fix the **specific** issue in the SQL
     (change only the identified token — do NOT rewrite from scratch). Re-run the
     **same command form** **once** (RULE 1). After that one retry, stop regardless.

## Pitfalls

- **Reference only columns/tables that exist** in `db_schema` (verbatim, correct
  casing). #1 cause of failure — step 2 prevents it.
- **Use only real join keys** from the DDL. Never invent a join condition.
- **Cartesian product row inflation:** joining without explicit PK/FK creates extra
  duplicate rows → bag-equality failure.
- **DISTINCT is a two-way trap.** Decide in step 3. `validate_sql.py` cannot catch
  a wrong DISTINCT decision.
- **WHERE filters rows; HAVING filters groups.**
- **No CTE/`WITH`, no window functions, no recursion.** SQLite Basic envelope.
- **One statement, read-only.**
- **task_id out == task_id in.**
- **Use `terminal` tool, not `process`/background.**
- **Nothing after `run.py` exits (RULE 2).** No JSON block, no prose.

## Verification

`scripts/run.py` receives SQL via `--sql` argv, writes a result file atomically to
`AIASE_RESULT_PATH`, and prints `written ok`. The grader reads that file — not the
conversation output. The file must be a valid JSON object with `task_id` matching
input, non-empty `sql`, and `confidence` in 0..1.

`scripts/validate_sql.py` remains independently runnable for manual checks. It
uses SQLite `EXPLAIN` on an in-memory schema: catches bad syntax and references to
non-existent tables/columns; cannot verify result correctness (no data locally).