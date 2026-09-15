#!/usr/bin/env python3
"""code-author / scripts/run.py — file-based 輸出契約入口（原子寫入結果檔）。

⚠️ 自帶 resolve_result_path，不依賴 repo-root contract module（安裝後找不到 repo 根模組）。

設計重點（結構性保證 emit）：
  - 程式碼以 --code-file 讀檔傳入（heredoc 寫 .py，原始換行/引號全合法），
    避免在命令列或 JSON 字串中跳脫多行程式碼。仍相容舊的 --code 字串。
  - --selftest-file 指向 selftest.py 的輸出，會自動帶入真實的
    loc(sloc) / self_test_passed(checks_passed) / self_test_failed(checks_failed)，
    模型不需手打數字。
  - 任何欄位讀取失敗都採安全預設，"一定寫出結果檔"（沒檔=該題0分）。
  - 底線參數同時接受連字號寫法。
"""
import os, json, argparse


def resolve_result_path() -> str:
    return os.environ.get("AIASE_RESULT_PATH") or os.path.join(os.getcwd(), "aiase_result.json")


def _load_code(a) -> str:
    if a.code_file:
        try:
            with open(a.code_file, encoding="utf-8") as f:
                return f.read()
        except OSError:
            pass
    return a.code or ""


def _apply_selftest(a):
    """若提供 --selftest-file，用其中的 checks_passed/checks_failed/sloc 覆寫對應欄位。讀不到就維持原值。"""
    if not a.selftest_file:
        return a.loc, a.self_test_passed, a.self_test_failed
    try:
        with open(a.selftest_file, encoding="utf-8") as f:
            txt = f.read().strip()
        if txt.startswith("```"):  # 容忍 fenced JSON
            txt = txt.strip("`")
            txt = txt[4:] if txt[:4].lower() == "json" else txt
        st = json.loads(txt)
        loc = int(st.get("sloc", a.loc))
        passed = int(st.get("checks_passed", a.self_test_passed))
        failed = int(st.get("checks_failed", a.self_test_failed))
        return loc, passed, failed
    except (OSError, json.JSONDecodeError, ValueError, TypeError):
        return a.loc, a.self_test_passed, a.self_test_failed


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--task_id", "--task-id", dest="task_id", required=True)
    ap.add_argument("--code", default="")
    ap.add_argument("--code-file", "--code_file", dest="code_file", default="")
    ap.add_argument("--selftest-file", "--selftest_file", dest="selftest_file", default="")
    ap.add_argument("--loc", type=int, default=0)
    ap.add_argument("--self_test_passed", "--self-test-passed", dest="self_test_passed", type=int, default=0)
    ap.add_argument("--self_test_failed", "--self-test-failed", dest="self_test_failed", type=int, default=0)
    ap.add_argument("--rationale", default="")
    ap.add_argument("--confidence", type=float, default=0.5)
    a, _unknown = ap.parse_known_args()

    code = _load_code(a)
    loc, passed, failed = _apply_selftest(a)

    # confidence clamp 到 [0,1]
    try:
        conf = min(1.0, max(0.0, float(a.confidence)))
    except (TypeError, ValueError):
        conf = 0.5

    result = {
        "task_id": a.task_id,
        "code": code,
        "loc": loc,
        "self_test_results": {"passed": passed, "failed": failed},
        "rationale": a.rationale,
        "confidence": conf,
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
