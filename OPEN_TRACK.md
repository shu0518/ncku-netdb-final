<!--
   Open Track 宣告 — 七個 heading 請照抄,順序也別動。
   合規判定會自動解析這七節;少一節就 fail gate。
   詳細要求見規格書 §2.4 與 §4.3。
-->

## 1. Skill 簡介

`open-unittest-shu0518` 為給定的 Python 函式自動產生單元測試,並以 **mutation
testing** 客觀衡量這些測試的偵錯能力:測試須在正確的參考實作上全數通過,且能殺死
對該實作做單點變異(mutant)後的錯誤版本。

## 2. Skill 名稱與目錄

- Skill 名稱:`open-unittest-shu0518`
- 路徑:`skills/open-unittest-shu0518/`
- 主要受評 skill:即上述路徑(本 Open Track 只有此一 skill;不重用其他 Track 的 skill)。

## 3. 呼叫方式

**Slash command:**

```
/open-unittest-shu0518
```

正式評分指令(file-based 輸出,含 `-Q`):

```bash
hermes chat --toolsets skills,terminal --yolo -Q -q '/open-unittest-shu0518 {json}'
```

**輸入 JSON 範例:**

```json
{
  "task_id": "open_ut_clamp",
  "entry_function": "clamp",
  "description": "Clamp x into [lo, hi]; if lo > hi the bounds are swapped.",
  "code": "def clamp(x, lo, hi):\n    if lo > hi:\n        lo, hi = hi, lo\n    if x < lo:\n        return lo\n    if x > hi:\n        return hi\n    return x\n"
}
```

欄位:`task_id`(必填,輸出須回填相同值)、`entry_function`(必填,受測函式名)、
`code`(必填,定義該函式的 Python 原始碼)、`description`(選填,正確行為說明)。

skill 由 `scripts/run.py` 將結果**寫入** `AIASE_RESULT_PATH`(未設定則
`./aiase_result.json`),不在對話輸出 JSON。

**輸出 JSON 範例(此即輸出 schema):**

```json
{
  "task_id": "open_ut_clamp",
  "entry_function": "clamp",
  "tests": "def test_inside():\n    assert clamp(5, 0, 10) == 5\n...",
  "self_report": {
    "tests_pass_on_reference": true,
    "coverage_pct": 100.0,
    "mutants_total": 3,
    "mutants_killed": 3,
    "mutation_score": 1.0
  },
  "error": ""
}
```

`tests` 為產生的測試原始碼字串;`self_report` 為 skill 端自測數據(評分以 §4 的
deterministic evaluator 重新計算為準,非以 `self_report` 為準)。

## 4. 自定 Verifiable Scenario

**Scenarios(至少 3 個,公開可執行,位於 `skills/open-unittest-shu0518/scripts/examples/`):**

- Scenario 1 — `s1_clamp.json`:`clamp(x, lo, hi)`,含邊界與 `lo>hi` 交換分支。
- Scenario 2 — `s2_grade_letter.json`:`grade_letter(score)`,多段 `>=` 比較邊界。
- Scenario 3 — `s3_is_leap_year.json`:`is_leap_year(year)`,`and/or` + `%` 布林邏輯。

每個 example 含 `code` 與一組 `reference_tests` 供 metric 自測重現。

**Metric:** 由 `scripts/score.py`(共用 `scripts/muteval.py`)從輸出的 `tests`
欄位**重新計算**,流程確定性、純 stdlib:

1. 將「參考程式 + 產生的測試」組成單一模組執行,跑所有 `test_*()`。
2. `tests_pass_on_reference`:測試是否在**未變異參考實作**上全通過。
   否則 `scenario_score = 0`(在正確程式上失敗的測試不可信)。
3. 以 AST 對參考實作產生**單點變異** mutant(算術 `+`↔`-`、比較 `<`↔`>=`、
   布林 `and`↔`or`、常數翻轉等),逐一以通過的測試重跑;任一測試在 mutant 上
   失敗 → 該 mutant 被 killed。
4. `mutation_score = mutants_killed / mutants_total`;
   `scenario_score = mutation_score`(tests pass on reference 時,否則 0)。
   本地 pass 門檻 `PASS_THRESHOLD = 0.70`。

評分指令:
```bash
python3 skills/open-unittest-shu0518/scripts/score.py \
    --task-file <task.json> --result-file <aiase_result.json>
```
輸出機器可讀 JSON(`passed`、`scenario_score`、`mutation_score` …),exit 0 = pass;
批次自測 `python3 scripts/score.py --self-test`。

**Ground truth 從何而來:** 輸入提供的 `code` 即正確實作,其行為就是 ground truth;
mutant 由該實作確定性衍生,不需外部答案。

**哪些輸入變化仍視為同一能力(staff perturbation):** 改函式名、改參數名、語意等價
改寫(`for`↔`while`、`if/elif`↔查表)、調整邊界值、加入無關函式。只要受測函式可
觀察行為不變,好測試應仍能通過參考並殺死同類 mutant。

**為何不可 gameable:**

- 對固定 `task_id` 硬編答案無效——分數由 mutant 殺傷率決定,與 `task_id` 無關;
  perturbation 換掉函式後,硬編測試會在新參考上失敗(`scenario_score = 0`)。
- 覆蓋率灌水無效——已實測:只呼叫不斷言的測試覆蓋率 85.71% 但 `mutation_score = 0`。
- `self_report` 灌水無效——`score.py` 由 `tests` 重算,不採信 skill 自報數字。
- 無關鍵字比對、無人工主觀——全程確定性程式比對。

## 5. 預期失敗模式

(對應規格書 §4.4 MAST 分類)

- 失敗 1 — **輸出契約失敗 / turn-budget 耗盡(MAST 3 驗證與品質)**:模型把測試碼
  塞進 JSON 字串造成跳脫錯誤、或反覆重試到回合耗盡而未寫結果檔。
  *處理*:Procedure 採單次 bash + 單引號 heredoc,測試以**原生 Python** 寫檔(無
  JSON 跳脫);`run.py` 必定寫出合法結果檔並 `exit 0`,即使測試有錯,杜絕重試迴圈。
- 失敗 2 — **測試在參考上失敗 / skill 未照規格(MAST 1 規格與角色)**:模型誤判
  函式行為,產生在正確程式上就失敗的測試。
  *處理*:metric 將 `tests_pass_on_reference=False` 直接判 `scenario_score=0`;
  SKILL.md 要求測試須在參考實作上全通過,並提供 branch/boundary 指引;`run.py`
  回報 `pass_on_ref` 供模型自我修正一次。
- 失敗 3 — **弱測試(MAST 3 品質)**:測試通過參考但殺不掉 mutant。
  *處理*:`mutation_score` 量化此弱點;SKILL.md 要求對每個分支與比較邊界做精確斷言。

## 6. 互動對象

本 skill 為單人、stateless 設計,**不**依賴其他同學或 staff reference skill,亦**不**
使用 Hermes subagent。互動對象僅為:評分環境(提供輸入 JSON)與本 skill 自身的
`scripts/` 確定性 harness。無跨 skill 協作宣告,故無需對方在其 OPEN_TRACK.md 對接。

## 7. Token Budget 估算

單次呼叫含一次自我修正重試;`scripts/` 為本機確定性執行,不消耗 token。皆遠低於
50k/scenario 上限。

| Scenario | 預估 input tokens | 預估 output tokens | 預估 total |
|---|---:|---:|---:|
| Scenario 1 (s1_clamp) | ~1500 | ~400 | ~1900 |
| Scenario 2 (s2_grade_letter) | ~1500 | ~450 | ~1950 |
| Scenario 3 (s3_is_leap_year) | ~1400 | ~350 | ~1750 |