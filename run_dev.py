#!/usr/bin/env python3
"""run_dev.py — 本地 dev-set 自測（file-based 輸出契約）。

對每題：
  1. 設 AIASE_RESULT_PATH 指到該題唯一的 temp 結果檔。
  2. 用正式評分指令呼叫你的 skill：
       hermes chat --toolsets skills,terminal --yolo -Q -q '/<skill> <json>'
  3. 用 aiase_contract.read_result 讀檔；沒檔 = 該題未產出（對齊評分器 gate）。
  4. (basic track) 用 validate_basic_schema 驗 schema、在 sqlite 上以 bag_equal 比對 sql vs gold_sql。
     (其他 track) 讀檔 + 基本 JSON object 檢查（pairwise 的正確性需 opponent/hidden test，本地不評）。

⚠️ 擷取與比對邏輯一律來自 aiase_contract（與評分器同一份）。本地 pass/fail 等同評分器，
   但你看不到 hidden test / perturbation / reference 答案。

用法：
  python3 run_dev.py --skill text2sql-<GITHUBID> [--track basic] [--limit N]
  python3 run_dev.py --skill text2sql-<GITHUBID> --task t1
  python3 run_dev.py --dry-run --result-file r.json --task t1   # 不呼叫 hermes，驗既有結果檔
"""
from __future__ import annotations

import os
import sys
import json
import glob
import argparse
import subprocess
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # 找到 aiase_contract
import aiase_contract as contract

# 正式評分指令固定 flag（含 -Q）。
HERMES_BASE = ["hermes", "chat", "--toolsets", "skills,terminal", "--yolo", "-Q"]


# Backward-compatible helpers kept for the starter repo tests.  The authoritative
# implementations live in aiase_contract.py; re-exporting them here does not
# change the file-based grading path.
bag_equal = contract.bag_equal
run_sql = contract.run_sql


def is_read_only_sql(sql: str) -> tuple[bool, str]:
    """Conservative SQL safety check used by local dev-set integrity tests."""
    if not isinstance(sql, str) or not sql.strip():
        return False, "empty SQL"
    stripped = sql.strip().rstrip(";").strip()
    if ";" in stripped:
        return False, "multiple statements"
    first = stripped.split(None, 1)[0].upper() if stripped.split(None, 1) else ""
    if first not in {"SELECT"}:
        return False, f"not read-only: starts with {first or '<empty>'}"
    blocked = (
        "CREATE", "DROP", "ALTER", "INSERT", "UPDATE", "DELETE", "REPLACE",
        "TRUNCATE", "ATTACH", "DETACH", "PRAGMA", "VACUUM",
    )
    upper = stripped.upper()
    for word in blocked:
        if re_search_word(word, upper):
            return False, f"contains {word}"
    return True, ""


def re_search_word(word: str, text: str) -> bool:
    import re
    return re.search(rf"\b{re.escape(word)}\b", text) is not None


def extract_last_json_block(text):
    """Extract the last fenced JSON object from legacy chat-output logs."""
    if not isinstance(text, str):
        return None
    import re
    matches = list(re.finditer(r"```json\s*(.*?)\s*```", text, re.IGNORECASE | re.DOTALL))
    for m in reversed(matches):
        try:
            obj = json.loads(m.group(1))
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            return obj
    return None


def load_basic_tasks(dev_dir: str | None = None) -> list[dict]:
    """Legacy helper: load Basic Track tasks from dev_set/basic."""
    base = dev_dir or os.path.join(os.path.dirname(__file__), "dev_set", "basic")
    tasks = load_tasks(base, "basic")
    repo = os.path.dirname(os.path.abspath(__file__))
    for t in tasks:
        dbp = t.get("db_path", "")
        if dbp and os.path.isabs(dbp):
            try:
                t["db_path"] = os.path.relpath(dbp, repo)
            except ValueError:
                pass
    return tasks


def load_tasks(dev_dir: str, track: str | None) -> list[dict]:
    """讀 dev_set/*.json；相對 db_path 解析成絕對；可依 track 過濾。"""
    repo_root = os.path.dirname(os.path.abspath(__file__))
    dev_root = os.path.dirname(os.path.abspath(dev_dir))
    tasks = []
    for p in sorted(glob.glob(os.path.join(dev_dir, "*.json"))):
        with open(p, encoding="utf-8") as f:
            t = json.load(f)
        if track and t.get("track", "basic") != track:
            continue
        dbp = t.get("db_path", "")
        if dbp and not os.path.isabs(dbp):
            repo_relative = os.path.join(repo_root, dbp)
            dev_relative = os.path.join(dev_root, dbp)
            t["db_path"] = repo_relative if os.path.exists(repo_relative) else dev_relative
        tasks.append(t)
    return tasks


def build_skill_input(task: dict) -> str:
    """組出餵給 skill 的 JSON（只放 skill 需要的欄位，不含 gold_sql / db_path）。"""
    drop = {"gold_sql", "db_path", "seed_sql", "track"}
    payload = {k: v for k, v in task.items() if k not in drop}
    return json.dumps(payload, ensure_ascii=False)


def invoke_skill(skill: str, task: dict, result_path: str, model: str | None) -> tuple[int, str]:
    """用正式指令呼叫 skill（skill 內部寫結果檔到 AIASE_RESULT_PATH）。可被測試 monkeypatch。"""
    env = dict(os.environ)
    env["AIASE_RESULT_PATH"] = result_path
    cmd = list(HERMES_BASE)
    if model:
        cmd += ["-m", model]
    cmd += ["-q", f"/{skill} {build_skill_input(task)}"]
    proc = subprocess.run(cmd, env=env, capture_output=True, text=True)
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def evaluate_task(task: dict, result_path: str, track: str) -> tuple[bool, str]:
    """讀結果檔 → (basic) 驗 schema + bag_equal；(其他) JSON object 檢查。純函式、可測試。"""
    obj = contract.read_result(result_path)
    if obj is None:
        return False, "no result file (task not produced)"
    if track == "basic":
        ok, reason = contract.validate_basic_schema(obj, task["task_id"])
        if not ok:
            return False, f"schema invalid: {reason}"
        try:
            got = contract.run_sql(task["db_path"], obj["sql"])
        except Exception as e:
            return False, f"student SQL failed to execute: {e}"
        try:
            gold = contract.run_sql(task["db_path"], task["gold_sql"])
        except Exception as e:
            return False, f"gold SQL failed (dev-set bug): {e}"
        return (True, "result set matches gold (bag-equal)") if contract.bag_equal(got, gold) \
            else (False, "result set differs from gold")
    # 非 basic track：本地只能確認「有產出且為合法 JSON object、task_id 一致」。
    if obj.get("task_id") != task["task_id"]:
        return False, "task_id mismatch"
    return True, "result file present & valid JSON object (pairwise correctness judged by grader)"


def run(skill, dev_dir, only_task, track, limit, model, dry_run, dry_result_file, invoke=invoke_skill):
    tasks = load_tasks(dev_dir, track)
    if only_task:
        tasks = [t for t in tasks if t["task_id"] == only_task]
    if limit:
        tasks = tasks[:limit]
    results = []
    tmpdir = tempfile.mkdtemp(prefix="aiase_dev_")
    for t in tasks:
        rp = dry_result_file if dry_run else os.path.join(tmpdir, f"{t['task_id']}.json")
        invoke_detail = ""
        if not dry_run:
            if os.path.exists(rp):
                os.remove(rp)
            rc, out = invoke(skill, t, rp, model)
            if rc != 0 or not os.path.exists(rp):
                tail = " ".join((out or "").strip().splitlines()[-3:])
                invoke_detail = f" hermes_rc={rc}" + (f" hermes_tail={tail[:300]}" if tail else "")
        passed, detail = evaluate_task(t, rp, t.get("track", track or "basic"))
        if not passed and invoke_detail and detail.startswith("no result file"):
            detail += f";{invoke_detail}"
        results.append({"task_id": t["task_id"], "passed": passed, "detail": detail})
        print(f"  [{'PASS' if passed else 'FAIL'}] {t['task_id']}: {detail}")
    n = len(results); p = sum(1 for r in results if r["passed"])
    print(f"\nDev set: {p}/{n} passed" + (f"  ({p / n * 100:.0f}%)" if n else ""))
    return {"total": n, "passed": p, "results": results}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--skill", help="skill name, e.g. text2sql-<GITHUBID>")
    ap.add_argument("--track", default="basic", help="basic | pairwise (filters dev_set by 'track')")
    ap.add_argument("--limit", type=int, default=0, help="only run the first N tasks")
    ap.add_argument("--task", dest="only_task", default=None)
    ap.add_argument("--model", default=None, help="override model (else config default)")
    ap.add_argument("--dev-dir", default=os.path.join(os.path.dirname(__file__), "dev_set"))
    ap.add_argument("--dry-run", action="store_true", help="不呼叫 hermes；用 --result-file 驗既有結果檔")
    ap.add_argument("--result-file", dest="dry_result_file", default=None)
    a = ap.parse_args()
    if not a.dry_run and not a.skill:
        ap.error("--skill is required unless --dry-run")
    if a.dry_run and not a.dry_result_file:
        ap.error("--dry-run requires --result-file")
    s = run(a.skill, a.dev_dir, a.only_task, a.track, a.limit, a.model, a.dry_run, a.dry_result_file)
    return 0 if s["total"] and s["passed"] == s["total"] else 1


if __name__ == "__main__":
    sys.exit(main())
