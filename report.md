# 期末報告 - AIASE 2026 Final Project

> 學生: 李映澍 / GitHub: `shu0518`

---

## 1. 設計決策

本專案的核心設計原則是把不穩定的 LLM 推理限制在清楚的 procedure 內，並把可驗證、可重跑、可落檔的部分放進 `scripts/`。更新後四個 skill 都改成 file-based output：skill 最後呼叫 `scripts/run.py`，由腳本把結果寫入 `AIASE_RESULT_PATH`，評分器只讀結果檔，不再依賴對話輸出的 fenced JSON。

### 1.1 Basic - Text2SQL Skill

`text2sql-shu0518` 的重點不是讓模型自由發揮，而是要求它先盤點 `db_schema` 裡的表、欄位、PK/FK，再產生單一 read-only SQL。`SKILL.md` 明確禁止 CTE、window function、多 statement 與 DDL/DML，並要求模型只呼叫一次固定形式的 `scripts/run.py`。

我把輸出封裝在 `scripts/run.py`，欄位固定為 `task_id`、`sql`、`rationale`、`confidence`。這樣即使模型最後沒有漂亮地說明答案，只要腳本有執行，就會有可驗證結果檔。

### 1.2 Pairwise - Code Author + Bug Hunter

Pairwise 兩個角色都實作並在 `PAIRWISE_ROLE.md` 宣告。

`code-author-shu0518` 使用 `scripts/selftest.py` 作為中介：模型只需要把候選 code 寫入檔案，再呼叫 selftest。selftest 會檢查 S-LOC、forbidden imports、sandbox 風險，最後鏈到 `run.py` 寫出結果檔。這避免模型手動填 `loc` 或測試數字造成 schema 錯誤。

`bug-hunter-shu0518` 則採 evidence-gated 設計。模型可提供 oracle 和 candidate bugs，但最後由 `scripts/run.py` 執行 analyzer，只保留有 crash 或 mismatch 證據支持的 bug。這個設計的目標是降低 false positive：沒有證據時輸出 `clean`，而不是讓模型靠直覺亂報。

### 1.3 Open Track - open-unittest-shu0518

Open Track 選擇做 unit-test generator。輸入是一個 Python function，skill 產生 `test_*()` 測試，`scripts/run.py` 會檢查測試是否能在 reference code 上通過，並用 mutation testing 衡量測試品質。

我選 mutation score 當 metric，因為它比 coverage 更不容易被 game。只呼叫函式、不 assert 的測試即使 coverage 高，也殺不死 mutant，分數仍低。`scripts/score.py` 會從結果檔中的 `tests` 欄位重新計算，不採信 skill 自報的 `self_report`，避免 self-report 灌水。

---

## 2. 實際遭遇之失敗與分析

### 失敗 1 - 同一份 SKILL.md 在不同模型上的行為差異

- 觸發場景: 同一個 skill 在 `gemma4:12b` 與 `qwen3.5:9b` 上測試。
- log 片段: `qwen3.5:9b` 把指令中的 `python` / `terminal` 誤判為工具名，回報 `Unknown tool`，retry 3 次後失敗。
- 成因分析: 兩個模型對「shell 指令」與「工具呼叫」的理解不同。較弱模型容易把 procedure 裡的文字當成工具名稱，而不是要在 terminal 裡執行的命令。
- 修正方式: 在 `SKILL.md` 中明示「使用 terminal tool 執行」，並降低 heredoc / shell escaping 的複雜度；對需要寫檔的 skill 改成固定單一路徑與固定指令形狀。
- MAST 分類: (1) 規格與角色、(3) 驗證與品質。

### 失敗 2 - 本地 12GB VRAM 跑 12B 模型造成 timeout

- 觸發場景: 本地用 Windows Ollama + WSL Hermes 跑 `gemma4:12b`。
- log 片段: Text2SQL dev set 出現多題 `hermes timed out after 120s`；簡單單表查詢也可能耗時約 66 秒。
- 成因分析: 11.9B 模型在 12GB VRAM 環境下容易 offload 到 CPU，推理延遲遠高於 gateway。這會讓本地 timeout 低估 skill 真實品質。
- 修正方式: 本地只做 smoke test 與少量 sanity check，正式正確性以課程 gateway 模型測試；`run_dev.py` 與 `verify_open.sh` 都保留 file-based 檢查，確認流程正確。
- MAST 分類: (3) 驗證與品質。

### 失敗 3 - 缺少 terminal toolset 導致 scripts 無法執行

- 觸發場景: 早期只用 `hermes chat --toolsets skills` 呼叫 skill。
- log 片段: skill 能被載入，但沒有成功執行 `scripts/run.py`，最後表現為 timeout 或沒有結果檔。
- 成因分析: Hermes 的 `skills` toolset 只負責載入 skill，不等於允許 skill 執行本地腳本。作業更新後正式指令需要 `--toolsets skills,terminal --yolo -Q`。
- 修正方式: `run_dev.py`、`OPEN_TRACK.md`、`verify_open.sh` 全部改成 `hermes chat --toolsets skills,terminal --yolo -Q`。
- MAST 分類: (3) 驗證與品質。

### 失敗 4 - 舊版對話輸出契約不穩定

- 觸發場景: Text2SQL 早期版本要求模型最後輸出 fenced JSON。
- log 片段: 曾出現 `no valid fenced JSON in stdout`，或模型最後輸出 ` ```sql ` 區塊而不是 ` ```json `。
- 成因分析: 模型可能正確呼叫腳本並得到答案，但最後又自行補一段 SQL 或英文說明，導致評分器抓不到最後一段合法 JSON。這不是 SQL 錯，而是 output contract 錯。
- 修正方式: 全部 track 改成 file-based output；`scripts/run.py` 原子寫入 `AIASE_RESULT_PATH`，對話輸出不再是評分依據。
- MAST 分類: (3) 驗證與品質。

### 失敗 5 - Shell quoting 讓弱模型陷入重試螺旋

- 觸發場景: 模型需要把 schema DDL、SQL、多行 code 或 tests 穿過 shell 傳給腳本。
- log 片段: 模型反覆改寫 shell 語法，例如 heredoc delimiter、`echo |`、`python3 -c`、inline Python 等，最後產生破碎 SQL 或 timeout。
- 成因分析: 問題不是 SQL 邏輯本身，而是多層 escaping 對弱模型太不友善。模型一旦第一種寫法失敗，就會開始改 invocation form，越改越偏。
- 修正方式: `SKILL.md` 規定固定命令形狀，出錯時只修正內容、不換 invocation form；Code Author / Open UnitTest 使用檔案傳遞 raw code/tests，避免把多行程式塞進 JSON 字串。
- MAST 分類: (3) 驗證與品質。

---

## 3. 改進方向

1. Basic Track 可再加入更多 schema-grounded few-shot examples，特別是 DISTINCT、GROUP BY、JOIN key 的判斷案例。
2. Text2SQL 可在 `scripts/validate_sql.py` 裡加入更完整的 envelope 檢查，例如 reject `WITH`、window functions、多 statement，讓本地錯誤更早暴露。
3. Bug Hunter 的 oracle 目前仍依賴模型從 spec 推導，未來可加入更結構化的 task_description parser，主動產生 empty、boundary、out-of-range 測試。
4. Open Track 的 mutation operator 可再擴充，例如 list slicing、loop boundary、dictionary key handling，讓 metric 覆蓋更多常見 Python bug。
5. 本地測試流程可拆成兩層：第一層直接跑 `scripts/run.py` smoke test，第二層才跑 Hermes。這樣可以快速分辨是 harness 壞、Hermes 設定壞，還是模型推理壞。

---

## 4. 分工

本專案為個人作業，所有 Basic、Pairwise、Open Track skill、scripts harness、本地測試與報告整理皆由 `shu0518` 完成。

| 項目 | 實際分工 |
|---|---|
| Basic skill | shu0518 |
| Pairwise Code Author | shu0518 |
| Pairwise Bug Hunter | shu0518 |
| Open Track skill | shu0518 |
| Open Track evaluator / metric | shu0518 |
| `run_dev.py` 自測 / debug | shu0518 |
| 報告撰寫 | shu0518 |

---

## 5. 引用說明

- 課程 starter repo: 使用其 dev set、reference skills、測試架構與作業規格模板。
- 課程 file-based update 說明: 依照更新要求加入 `aiase_contract.py`、更新 `run_dev.py`，並將四個 skill 改成 `AIASE_RESULT_PATH` file-based output。
- AI 輔助: 使用 AI 協助整理 `SKILL.md` procedure、debug log 分析與本報告文字；最終內容與程式碼均由本人檢查、測試與提交。
