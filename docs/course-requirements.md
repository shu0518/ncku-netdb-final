[![Review Assignment Due Date](https://classroom.github.com/assets/deadline-readme-button-22041afd0340ce965d47ae6ef1cefeee28c7c493a6346c4f15d667ab976d596c.svg)](https://classroom.github.com/a/0_h2Gwpe)
# AIASE 2026 期末專案 - shu0518

> 在 Hermes Agent 上打造可驗證的 Skill。此 repo 已完成 Basic / Pairwise / Open 三個 track，並採用 file-based output contract。

---

## 本地測試

先安裝 Python dependency:

```bash
python -m pip install -r requirements.txt
```

確認 Hermes 看得到 skill:

```bash
hermes skills list
```

煙霧測試:

```bash
AIASE_RESULT_PATH=/tmp/hello_probe.json \
hermes chat --toolsets skills,terminal --yolo -Q \
  -q '/hello-aiase {"task_id":"probe","name":"shu"}'
cat /tmp/hello_probe.json
```

Basic Track:

```bash
python dev_set/basic/build_dbs.py
python3 run_dev.py --skill text2sql-shu0518 --track basic --dev-dir dev_set/basic
```

Pairwise Track:

```bash
python3 grade_bughunter_local.py --skill bug-hunter-shu0518
```

Open Track:

```bash
bash verify_open.sh
```

Repo gate:

```bash
python3 verify_repo.py --github-id shu0518
python3 -m pytest -q
```

---

## 倉庫結構

```
.
├── README.md                              ← 你正在看
├── requirements.txt                       ← 本地 dev 用,radon/pytest/PyYAML
├── run_dev.py                             ← 本地自測:驅動 hermes chat -q + 比對
├── verify_repo.py                         ← 繳交前自我檢查
├── PAIRWISE_ROLE.md                       ← 必交,宣告 Pairwise 角色
├── OPEN_TRACK.md                          ← 必交,Open Track 七區塊宣告
├── report.md                              ← 必交,設計決策 + 失敗分析
├── docs/                                  ← gateway / env 範例
│   ├── hermes-config.example.yaml
│   └── hermes-env.example
├── skills/                                ← 你的 skill 與 reference 對手
│   ├── hello-aiase/                       ← 煙霧測試,勿改
│   ├── text2sql-shu0518/                 ← Basic Track 骨架,改名後填邏輯
│   ├── code-author-shu0518/              ← Pairwise Code Author 骨架
│   ├── bug-hunter-shu0518/               ← Pairwise Bug Hunter 骨架
│   ├── open-unittest-shu0518/             ← Open Track skill
│   ├── reference-bug-hunter-conservative/ ← 課程提供,本機自測 Pairwise 對手
│   ├── reference-bug-hunter-aggressive/
│   ├── reference-bug-hunter-noisy/
│   ├── reference-author-clean/
│   ├── reference-author-buggy/
│   └── reference-author-tricky/
├── dev_set/
│   ├── basic/                             ← Basic Track 公開 dev set(含答案)
│   │   ├── task_nl2sql_*.json
│   │   ├── dbs/                           ← 對應 sqlite(用 build_dbs.py 生)
│   │   └── build_dbs.py
│   └── pairwise/
│       ├── task_pairwise_EXAMPLE.json
│       └── reference_tasks/               ← 含 ground-truth bug 標註
└── tests/                                 ← 確定性元件的 pytest
```

---

## 必交檔案清單

繳交 deadline(2026/6/16 23:59 Asia/Taipei)前,確認 default branch 上有:

- [ ] `skills/text2sql-shu0518/SKILL.md` + scripts(Basic Track)
- [ ] `skills/code-author-shu0518/` 與 `skills/bug-hunter-shu0518/`(Pairwise 兩角色皆提交)
- [ ] `skills/open-unittest-shu0518/`(Open Track)
- [ ] `PAIRWISE_ROLE.md`(同時宣告 Code Author 與 Bug Hunter)
- [ ] `OPEN_TRACK.md`(七區塊齊全)
- [ ] `report.md`

---

## 繳交前自我檢查

```bash
python3 verify_repo.py --github-id shu0518
```

會檢查 folder name 一致性、`SKILL.md` 必填欄位、`OPEN_TRACK.md` 七區塊、無疑似 token、無絕對路徑。輸出 `verify_report.json`。

詳細檢查清單見規格書 §5.7。

---

## 重要規則(摘要,以規格書為準)

1. **不用 MCP**:本地確定性 helper 一律放 `scripts/`,不可以額外起 MCP server。
2. **輸出契約**:每個 skill 的最後一個動作 = 執行 `scripts/run.py` 將結果寫入 `AIASE_RESULT_PATH`；評分器讀結果檔，不靠對話中的 fenced JSON。
3. **無外網**:評分環境無外網;只允許課程的 LiteLLM Gateway。
4. **無絕對路徑**:禁止寫死個人電腦、家目錄、下載資料夾等 machine-specific path；請用相對路徑、`__file__` 推導或 `AIASE_RESULT_PATH`。
5. **dependency pin 版本**:`scripts/requirements.txt` 必須 pin 版本。
6. **task_id**:輸入有 `task_id`,輸出的 `task_id` 必須完全相同。
7. **model-agnostic**:評分模型為 held-out,別寫死在某顆模型的脾氣上。

---

## 開發策略(建議)

1. **先用 `gemma4` 反覆迭代**(免費,不耗你的 2 美元上限)。
2. 基礎穩了再切 `gemini-2.5-flash` 驗一輪跨模型不退步(計入 2 美元)。
3. `claude-haiku-4-5` 是 held-out,**開發期取不到**(別賭它的脾氣)。
4. 多用 `run_dev.py` —— dev set 含答案,是你唯一可靠的自我檢驗工具。
