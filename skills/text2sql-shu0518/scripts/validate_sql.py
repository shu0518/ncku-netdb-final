#!/usr/bin/env python3
"""
Deterministic SQL validator for text2sql skill.

Input (either way works):
    # 推薦：用 stdin 餵 JSON（heredoc，不怕 SQL 裡的單引號）
    python validate_sql.py <<'JSON'
    {"schema_ddl": "CREATE TABLE ...", "sql": "SELECT ..."}
    JSON

    # 也可以用 argv（手動測試方便，但 SQL 含單引號時 shell 跳脫麻煩）
    python validate_sql.py '{"schema_ddl":"CREATE TABLE ...", "sql":"SELECT ..."}'

Prints validation JSON:
    {"ok": true|false, "error": "<sqlite error or rule violation>"}

Strategy:
1. Reject multiple statements / DDL / DML up front (cheap, no DB needed).
2. Build the schema in an in-memory sqlite (no data).
3. Run `EXPLAIN <sql>` — this parses & resolves column names without needing data.
4. On sqlite3.Error, return its message so the LLM can fix the draft.

驗得了：語法、表/欄位是否存在、單一 read-only statement。
驗不了：結果列對不對（本地沒有資料、沒有 ground truth）。
"""

from __future__ import annotations

import json
import re
import sqlite3
import sys


FORBIDDEN = re.compile(
    r"\b(INSERT|UPDATE|DELETE|CREATE|DROP|ALTER|ATTACH|DETACH|REPLACE|TRUNCATE|VACUUM|PRAGMA)\b",
    re.IGNORECASE,
)


def _emit(ok: bool, error: str = "") -> int:
    out = {"ok": bool(ok), "error": error}
    sys.stdout.write("```json\n")
    sys.stdout.write(json.dumps(out, ensure_ascii=False))
    sys.stdout.write("\n```\n")
    return 0 if ok else 1


def validate(schema_ddl: str, sql: str) -> tuple[bool, str]:
    sql_stripped = sql.strip().rstrip(";")
    if not sql_stripped:
        return False, "empty SQL"
    if ";" in sql_stripped:
        return False, "multiple SQL statements not allowed"
    if FORBIDDEN.search(sql_stripped):
        return False, "DDL/DML/PRAGMA not allowed; SELECT only"

    con = sqlite3.connect(":memory:")
    try:
        if schema_ddl:
            try:
                con.executescript(schema_ddl)
            except sqlite3.Error as e:
                return False, f"schema DDL did not parse: {e}"
        else:
            # schema 為空時，EXPLAIN 會以 "no such table" 失敗。明講出來，
            # 避免 LLM 誤以為是自己 SQL 寫錯（多半是漏傳 schema_ddl）。
            return False, "empty schema_ddl (did you pass db_schema under key 'schema_ddl'?)"
        try:
            con.execute(f"EXPLAIN {sql_stripped}")
        except sqlite3.Error as e:
            return False, f"SQL did not compile: {e}"
        return True, ""
    finally:
        con.close()


def _read_raw(argv: list[str]) -> str:
    """argv[1] 優先；沒有就讀 stdin。讓 heredoc / pipe / argv 三種都能用。"""
    if len(argv) >= 2 and argv[1].strip():
        return argv[1]
    return sys.stdin.read()


def main(argv: list[str]) -> int:
    raw = _read_raw(argv)
    if not raw.strip():
        return _emit(False, "no payload: pass JSON via stdin or argv[1]")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as e:
        return _emit(False, f"payload JSON invalid: {e}")
    ok, err = validate(str(payload.get("schema_ddl", "")), str(payload.get("sql", "")))
    return _emit(ok, err)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
