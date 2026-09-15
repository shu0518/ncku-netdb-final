# AIASE 2026 期末專案 — AI 評閱回饋

**GitHub ID:** `shu0518`

## 成績摘要

| 軌道 | 分數 |
|---|---|
| Basic Track(text2sql) | 29.0 / 30 |
| Pairwise Track(角色:Bug Hunter) | 5.0 / 10 |
| Open Track(設計 40% + 執行 60%) | 68.6 / 100 |
| 基礎加分(nano 第二參考) | 24.0 / 30 |
| Pairwise 加分(nano CA) | 1.25 / 10 |
| **Project 總分** | **72.75** |

- 額外榮譽 / 加分:—
- 評分重試次數:Basic **0 次**(一次到位);Pairwise 採統一重試政策(no-result 重試 1 次、flaky 受害者重評取最佳),未逐人記錄次數。

## Open Track 計分明細(透明拆解)

Open 總分 = **設計審查 × 40% + 實跑驗證(60 分制)** = **68.6 / 100**

**① 設計審查(占 40 分)= 33.6 分**(LLM 閱讀你的 skill 評分:84.0/100)

- **可驗證性:9/10** — 評分核心由 `muteval.py` 的 AST mutation pipeline 純確定性實現，`score.py` 獨立重算分數而不採信 `self_report`，明確防止灌水。`examples/` 內每個 scenario JSON 含 `reference_tests` 可直接 `--self-test` 重現，ground truth 來自輸入 code 本身而非人工標注，設計嚴謹。唯一小缺憾是 example JSON 的實際內容未隨素材提供，無法確認 `reference_tests` 已寫完整。
- **完整與清晰:8/10** — OPEN_TRACK.md 七節齊全，SKILL.md 含 Procedure / Input / Output / Verification 各節，`run.py`、`muteval.py`、`score.py` 三支 script 邏輯完整且互相呼應。缺少 `scripts/examples/` 三個 JSON 檔案的實際內容（s1_clamp.json、s2_grade_letter.json、s3_is_leap_year.json），評審無法驗證 `reference_tests` 品質；`requirements.txt` 被提及但未附上（即使僅為空文件）。
- **方法正確性:9/10** — `muteval.py` 的 `_apply` 邏輯與 `_mutables` 列舉方式經閱讀確認邏輯正確，`bool` 常數在 `Constant` 節點優先判斷以避免與 `int` 衝突，`_executable_lines` 排除 def header 與 docstring，coverage trace 正確限制在 `ref_lines` 內。`atomic_write_json` 使用 `os.replace` 保證原子性，`load_task` 有三層容錯解析。細節上 `_describe` 對普通常數的描述訊息 `{node.value}->{node.value}+1` 只是字串描述而非實際值（+1 未計算），屬顯示小瑕疵，不影響正確性。
- **失敗模式/穩健:8/10** — `run.py` 的設計宗旨「always exit 0 / always write a result」有效防止 agent retry loop，`load_task` 三段容錯解析處理了模型常見的 heredoc 毀損。`MAX_MUTANTS=60` 限制防止爆炸性耗時，測試執行包裹於 try/except。但 `coverage()` 使用 `sys.settrace` 存在 thread safety 問題（若並發執行），且若測試有 infinite loop 或 subprocess 呼叫等情況無 timeout 保護。
- **工程嚴謹度:8/10** — Metric 設計有理論依據：mutation testing 比覆蓋率更能量化測試品質，且明確說明「只呼叫不斷言」的情況下覆蓋率可達 85.71% 但 mutation_score=0。PASS_THRESHOLD=0.70 有合理設定。但未說明多次執行的穩定性（mutant 順序依 `ast.walk` 決定，理論上穩定；惟 Python 版本差異可能影響 AST walk 順序），且對「語意等價改寫」的 perturbation 情境僅在 OPEN_TRACK.md 文字宣告，未見實際 perturbation test case。
- **難度與原創:7/10** — 以 mutation testing 作為 LLM 產生測試的客觀評分機制，在 Open Track 設計中屬於思路清晰且具實踐價值的方案，勝過單純覆蓋率或 I/O 比對。設計整體紮實但非研究突破；mutation 類型（`+`↔`-`、`<`↔`>=`、`and`↔`or`、常數 +1）為教科書標準集合，未加入更多 mutant 類型（如 return value deletion、statement deletion 等）。

**② 實跑驗證(占 60 分)= 35 分**
- 可實際執行、輸出合法:✓ +20(滿 20)
- **確定性**(同輸入跑兩次結果一致):✗ +0(滿 25)
- 對自宣告 gold 正確:✓ +15(滿 15)

> 為何採「設計 + 實跑」雙軌:對齊公告「open in design, strict in verification」——設計分肯定你的構想,實跑分檢驗它**真的可重現、可驗證**(確定性 / 對得上自己的 gold)。

## 評語

---

你的 **Basic Track** 表現相當亮眼，29/30 題通過，僅 `task_nl2sql_h10` 因 SQL 語法錯誤（near "." syntax error）未能執行，整體已充分展現 text2sql 的掌握度。

**Open Track** 的設計尤其值得稱讚：以純 stdlib 的 AST mutation testing pipeline 作為客觀評分核心，`score.py` 獨立重算、`run.py` 防止 retry loop、四類 mutant 涵蓋完整，防 gameable 論述具體有力，是本屆設計品質偏高的提交。

**以下三點建議可進一步提升成績：**

1. **補齊範例素材**：`scripts/examples/` 三個 JSON（含 `reference_tests`）未隨評審素材提供，導致公開 scenario 完整性無法確認；下次請確保範例檔案一併 commit。

2. **強化確定性**：兩次執行結果不一致，請檢查是否有隨機種子、檔案寫入順序或浮點排序等問題，確保每次輸出完全可重現。

3. **提升 Bug Hunter 偵測率**：Pairwise 偵測 buggy 的 F1 為 0.0，表示 buggy 程式均未被標記。建議重新審視你的偵測邏輯，確認對帶有 bug 的提交是否有實際觸發判斷條件。

---
> 本評閱由 AIASE 2026 自動化評分系統產生,供學習回饋參考。
> 方法對齊課程公告精神「**open in design, strict in verification**」:
> Open Track 以 **LLM 設計審查(40%)+ 確定性實跑驗證(60%)** 評分;Basic 對齊權威 `run_dev.py`;Pairwise 以 sandbox 跑題與 bug 偵測 F1 計分。
> 各軌分數與權重以課程最終公告為準;加分項獨立計算。
