#!/usr/bin/env python3
"""text2sql-shu0518 / scripts/run.py — file-based 輸出契約入口（原子寫入結果檔）。

⚠️ 自帶 resolve_result_path,不依賴 repo-root contract module(安裝到 ~/.hermes/skills/ 後
   找不到 repo 根模組)。寫檔規則對齊評分器:
   - 路徑優先讀環境變數 AIASE_RESULT_PATH,讀不到 fallback 到 ./aiase_result.json。
   - 內容為單一 JSON object,含 task_id / sql / rationale / confidence。
   - 原子寫入(先寫 .tmp 再 os.replace),避免評分器讀到寫一半的檔。
"""
import os, json, argparse


def resolve_result_path() -> str:
    return os.environ.get("AIASE_RESULT_PATH") or os.path.join(os.getcwd(), "aiase_result.json")


def _clamp_confidence(v) -> float:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return 0.0
    return 0.0 if f < 0.0 else 1.0 if f > 1.0 else f


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--task_id", required=True)
    ap.add_argument("--sql", required=True)
    ap.add_argument("--rationale", default="")
    ap.add_argument("--confidence", type=float, default=0.5)
    a = ap.parse_args()

    result = {
        "task_id": a.task_id,
        "sql": a.sql.strip(),
        "rationale": a.rationale,
        "confidence": _clamp_confidence(a.confidence),
    }
    path = resolve_result_path()
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False)
    os.replace(tmp, path)  # 原子寫入
    print(f"written ok -> {path}")


if __name__ == "__main__":
    main()
