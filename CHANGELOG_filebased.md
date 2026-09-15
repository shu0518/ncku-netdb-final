# CHANGELOG — 輸出方式改為 file-based（請務必詳閱）

## 改了什麼
1. **評分指令一律加 `-Q`**：
   ```
   hermes chat --toolsets skills,terminal --yolo -Q -q '/skill-name {json}'
   ```
   沒有 `-Q` 時 `hermes chat` 會美化最終訊息、把 ```` ``` ```` 標記吃掉，導致輸出抓不到。
2. **輸出改用 file-based（寫結果檔）**：skill 由 `scripts/run.py` 把最終結果**原子寫入**約定檔案
   （路徑取自環境變數 `AIASE_RESULT_PATH`，未設定則 `./aiase_result.json`）；評分器**讀檔**評分，
   **不再從對話訊息擷取 JSON**。沒有結果檔 = 該題 0 分。
3. 新增 `aiase_contract.py`（共用比對核心）；`run_dev.py` 改成讀檔 + 用 `aiase_contract` 比對。

## 你需要重做的動作
1. **重抓（或 merge）starter repo**，取得 `aiase_contract.py`、新版 `run_dev.py`、四個新版範例 skill。
2. **把你的 skill 改成寫結果檔**：對照 `skills/` 範例，
   - `scripts/run.py`：自帶 `resolve_result_path()`（優先 `AIASE_RESULT_PATH`，否則 cwd），原子寫入結果 JSON；
     **不要 import `aiase_contract`**（安裝後找不到模組）。
   - `SKILL.md` 的 Procedure 最後一步改成「執行 `scripts/run.py` 寫結果檔；不需在對話訊息輸出 JSON」，
     並明確要求「用 terminal 工具、絕對路徑執行 `python3 <skill_dir>/scripts/run.py ...`」。
3. 本地用 `python3 run_dev.py --skill <你的skill>` 自測（會用含 `-Q` 的正式指令）。

## 一句保證
> **`run_dev.py` 使用與評分器相同的 `aiase_contract.py` 讀檔與比對邏輯。**
> 你本地的 pass/fail 等同評分器判定；但你看不到 hidden test、perturbation 與 reference 答案。

## 不影響的既有契約
bag equality 定義、Difficulty Envelope、Pairwise 雙角色隨機抽評、Open Track 結構、500 S-LOC、
120 秒 timeout、LiteLLM URL、provider id 等一律不變。
