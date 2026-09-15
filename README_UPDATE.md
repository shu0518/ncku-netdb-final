# AIASE 2026 期末專案 — file-based 輸出更新包（增補，非取代）

> 這是**增補包**。它**不取代**你原本的 starter repo —— 你原本的 reference skills、dev set、
> PAIRWISE_ROLE.md、OPEN_TRACK.md、report.md、build_dbs.py 等**全部照舊保留**。
> 本包只更新「輸出方式」相關的檔案：改成 **file-based（skill 寫結果檔、評分器讀檔）** + 評分指令加 **`-Q`**。

---

## 一句話

以前 skill 把答案「說」出來（印在對話）；現在 skill 把答案「寫」下來（寫進結果檔）。
評分器只看你寫的檔，不看你說什麼。

---

## 各檔案放哪

| 本包檔案 | 放到你 repo 的位置 | 動作 |
|---|---|---|
| `aiase_contract.py` | repo 根目錄（與 `run_dev.py` 同層） | 新增 |
| `run_dev.py` | repo 根目錄 | **覆蓋**舊的 |
| `skills/<name>/SKILL.md` | 對應 skill 資料夾 | 當範本，對照修改你自己的 |
| `skills/<name>/scripts/run.py` | 對應 skill 的 `scripts/` | 當範本，對照修改你自己的 |
| `CHANGELOG_filebased.md` | 任意（參考用） | 閱讀 |

> `aiase_contract.py` 是 `run_dev.py` 與評分器**共用的同一份比對核心**，所以你本地跑出來的
> pass/fail 等同評分判定。**務必放在 repo 根目錄、與 `run_dev.py` 同層**，否則 `run_dev.py` 會 import 失敗。

---

## 你的 skill 要改的三件事

1. **評分指令一律加 `-Q`**：
   `hermes chat --toolsets skills,terminal --yolo -Q -q '/skill-name {json}'`

2. **SKILL.md 的 Procedure**：把「在最後訊息輸出一段 ```json``` 區塊」改成
   「執行 `scripts/run.py` 把最終結果**寫入結果檔**，不必在對話再輸出 JSON」。

3. **scripts/run.py**：改成寫檔版（照本包範例）。結果檔路徑用環境變數 `AIASE_RESULT_PATH`，
   讀不到就 fallback 到 `./aiase_result.json`。
   ⚠️ **不要 `import aiase_contract`** —— skill 安裝到 `~/.hermes/skills/` 後會找不到該模組；
   寫檔那幾行請自己帶在 `run.py` 裡（範例已寫好，照抄即可）。

---

## 怎麼確認改對了

從 **repo 根目錄**執行（確認 `aiase_contract.py` 在同一層）：

```
python run_dev.py --skill text2sql-<github_id> --track basic
```

- 顯示讀到結果檔、有比對結果 → 你已接上 file-based ✅
- 一直顯示「沒有結果檔」→ 你的 skill 還沒改成寫檔，回到上面第 2、3 點。

---

## 不變的東西（照舊，不受本次更新影響）

三個 Track 的任務內容、bag equality、Difficulty Envelope、Pairwise 兩角色與隨機抽評、
Open Track 結構、500 S-LOC、120 秒 timeout、reference skills、dev set —— 全部照舊。
