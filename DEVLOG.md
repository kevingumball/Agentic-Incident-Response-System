# 開發紀錄：困難、問題與結果

> 日期：2026-09-25
> 對應程式碼：commit `0aa5232`
> 這份紀錄保存開發過程中遇到的問題、每次修改的原因，以及最終的實驗結果，方便之後回顧與準備面試。

---

## 1. 總結

| 項目 | 結果 |
|------|------|
| 實作範圍 | 規格書（SPEC.md）全部完成：模擬資料層、MCP server、LangGraph agent、Human Approval、ReAct baseline、Evaluation、單元測試、README |
| 開發集（8 題）最終成績 | 本系統 8/8，Premature Diagnosis 0% |
| **Held-out 集（12 題 × 3 次）最終成績** | **ReAct 35/36 (97%)；本系統 25/36 (69%)** |
| 核心結論 | 規格書的假設「Planner + Verifier 會比 ReAct 好」**在 gpt-4.1-mini 上不成立** |
| 總 API 花費 | 120 次 run，約 **$1.39** |
| 單元測試 | 26 個，全部通過，不呼叫 LLM |

---

## 2. 實作流程

照規格書第 10 節的順序，一個做完再做下一個：

1. **Taxonomy**（`agent/taxonomy.py`）：8 種 root cause 的精確定義，避免類別互相重疊（例如 `missing_env_var` 優先於 `bad_config_deploy`）。
2. **Benchmark 產生器**（`evaluation/generate_scenarios.py`）：建一個健康的 6 服務系統，對每題注入一種故障與干擾訊號，輸出 20 個情境檔。答案另存 `evaluation/labels.json`。
3. **MCP server**（`mcp_server/`）：4 個唯讀工具、1 個模擬寫入工具，alert 以 MCP resource（`alert://current`）提供。
4. **Agent 核心**：`state.py`、`schemas.py`、`verifier.py`（硬規則）、`prompts.py`、`graph.py`。
5. **MCP client**、**runner**（統一執行介面、token 與成本統計）、**CLI demo**（`main.py`）。
6. **ReAct baseline**（`agent/baseline_react.py`）：由 `testingcalculator.py` 的 `agent ↔ tools` 迴圈改寫。
7. **Evaluation**：`metrics.py`（純函式）、`run_eval.py`、`report.py`。
8. **單元測試**、`requirements.txt`、`.env.example`、`.gitignore`、README。
9. 開發集調整 4 輪 → 凍結設計 → held-out 只跑一次。
10. 安裝 Git、建立 repo、推上 GitHub。

---

## 3. 工程問題與解法

開發過程中遇到的技術問題，依發生順序：

| # | 問題 | 原因 | 解法 |
|---|------|------|------|
| 1 | 環境缺少 `mcp`、`langchain-mcp-adapters`、`rich`、`pytest` | 原本只裝了 LangGraph / LangChain | `pip install` 補齊，並寫進 `requirements.txt` |
| 2 | MCP 每次呼叫工具都會重開一個 server 行程 | `MultiServerMCPClient.get_tools()` 預設每次 tool call 建新 session | 改用 `client.session(...)` + `load_mcp_tools(session)`，每個 incident 只開一個 server 行程 |
| 3 | Alert 文字出現 `181.2345 ms` 之類的長小數 | Alert 在數值四捨五入**之前**就產生 | 改成先 `finalize()` 四捨五入，再用結果產生 alert |
| 4 | MCP server 的 INFO log 洗版 CLI | FastMCP 預設 log level 是 INFO | `FastMCP(..., log_level="WARNING")` |
| 5 | 第一次執行只看到 `ExceptionGroup: unhandled errors in a TaskGroup` | MCP 底層用 anyio task group，真正的錯誤被包在裡面 | runner 中把 `BaseExceptionGroup` 一層層拆開，記錄真正的例外 |
| 6 | `ValidationError: PlannerDecision.query Field required` | LLM 省略了用不到的選填欄位 | `metric`、`query` 加上 `default=""` |
| 7 | 一次 run 顯示耗時 27,187 秒 | `time.perf_counter()` 在 Windows 上電腦睡眠時仍會計時 | 改用 `time.time()`（實際經過的牆鐘時間） |
| 8 | 報告的 Markdown 全部擠成一段 | 缺少換行與清單符號 | `build_report()` 改用 `-` 清單與空行 |
| 9 | Ground-truth 隔離測試失敗 | MCP server 的 docstring 裡提到了 `labels.json` 這個檔名 | 修改 docstring。測試本身正確，維持嚴格檢查 |
| 10 | 不小心在專案外建立了一個多餘的檔案 | 操作失誤 | 立即刪除 |
| 11 | Git 無法推送：`Cannot prompt because user interactivity has been disabled` | 推送需要在瀏覽器登入 GitHub，自動化的終端機無法開啟 | 由使用者在 VS Code 終端機手動執行 `git push` 完成登入 |
| 12 | 本系統單題平均約 280 秒，ReAct 約 28 秒 | 每一步要呼叫 3 次 LLM，prompt 很大，再加上 OpenAI rate limit 的重試 | 尚未解決，記錄為限制 |

---

## 4. 開發集調整過程（只看 dev set）

整個調整過程只看 8 題開發集，held-out 在設計凍結前完全沒看。

| 版本 | 在 dev 上發現的問題 | 修改內容 | Dev Accuracy | Premature |
|------|------------------|---------|-------------|-----------|
| v1 | 2–3 次工具呼叫就下結論 | （初始版本） | 5/8 | 50% |
| v2 | 見下方 v1 的三個問題 | 證據必須引用工具輸出；skeptic 檢查定義、直接檢查、剩餘候選 | **2/8**（5 題 unknown） | 25% |
| v3 | v2 矯枉過正 | Skeptic 的反對必須指名一個「還沒做過的檢查」 | 5/8 | 12% |
| v4 | 資訊在節點間流失 | 保留完整原始輸出；supports/contradicts 最多 2 個 | **8/8** | **0%** |

同一時期 ReAct 在 dev 上兩次都是 8/8。

### v1 的三個問題

1. **證據沒有根據工具輸出**（case_001）
   Planner 把假設寫進 log 搜尋關鍵字（`"KeyError required setting not found"`）。因為搜尋是「任一關鍵字符合」，回傳的其實是另一條 log（`timed out after 50ms`），但 LLM 把**搜尋關鍵字**當成 **log 內容**記成證據，最後誤判為 `missing_env_var`。
2. **證據來源被亂標、`contradicts` 被濫用**（case_015）
   舊的 metrics 觀察被重複記成 logs 證據，灌水了「來源種類數」，等於繞過 Verifier 規則 2。每條證據都標「反對」6–8 個原因，把所有競爭假設壓到接近 0，規則 3 形同虛設。更糟的是，trace 顯示 `normalize_sku` 佔 98% 時間，卻被標成**反對** `cpu_hot_loop`。
3. **Skeptic 太寬鬆**（case_002）
   接受了 `dependency_unavailable`，但 payment 的 3 個 instance 都正常，根本不符合定義（服務掛掉或連不上），而且從沒看過 payment 自己的 log。

### v2：矯枉過正

加強證據規則與 skeptic 之後，**正確答案已經 0.95–0.99**，skeptic 還是一直挑剔，提出工具根本做不到的要求（「做 CPU profiling」、「為什麼缺少某個 metric」），直到步數用完回報 unknown。問題在於「列出還沒排除的候選」這個要求**沒有停止條件**。

### v3：讓反對意見「可驗證」

設計了一個可以用程式檢查的約束：**每個反對意見都必須指名一個還沒做過的檢查（工具 + 服務）**。程式（`agent/verifier.py` 的 `open_objections`）會自動丟掉「那個檢查已經做過」的反對。

- 避免無止境的挑剔
- 每個有效的反對都直接變成 Planner 的下一步行動

### v4：資訊流失

各節點只看得到「一句話的證據摘要」，原始工具輸出用完就丟。ReAct 則是把所有原始輸出都留在 context 裡。

- case_015：Planner 看不到 trace 裡 `inventory.reserve` 很慢，所以沒有往下游追。
- case_006：payment 設定裡「剛部署就少了 `PAYMENT_PROVIDER_URL`」這個細節在摘要時遺失。

修改：state 新增 `observations`（完整原始輸出歷史），證據變成建立在原始輸出之上的「註記索引」，而不是唯一的記憶；`supports`/`contradicts` 在程式中限制最多 2 個。

---

## 5. 最終結果：Held-out 集

設計凍結後只跑一次：12 題 × 3 次 × 2 種架構 = 72 次 run。

| 架構 | Accuracy | 每次都答對的題數 | False Diagnosis | Premature Diagnosis | Unknown | 平均工具呼叫 | 平均 Token | 成本/題 | 平均時間 |
|------|----------|----------------|-----------------|---------------------|---------|------------|-----------|--------|---------|
| ReAct baseline | **35/36 (97%)** | **11/12** | **3%** | **8%** | 0% | 6.8 | 15,678 | **$0.0068** | 28s |
| Planner + Hypothesis + Verifier | 25/36 (69%) | 7/12 | 14% | 25% | 17% | 6.5 | 38,931 | $0.0181 | 283s |

各 root cause 的正確次數：

| Root cause | ReAct | 本系統 |
|-----------|-------|--------|
| bad_config_deploy | 5/6 | 3/6 |
| cpu_hot_loop | 3/3 | 3/3 |
| db_pool_exhaustion | 6/6 | 6/6 |
| dependency_unavailable | 6/6 | 5/6 |
| expired_credential | 3/3 | **0/3** |
| memory_leak | 3/3 | **0/3** |
| missing_env_var | 3/3 | 3/3 |
| slow_db_query | 6/6 | 5/6 |

完整結果：`evaluation/results/eval_20260925-113329/summary.md`

### 失敗分析（本系統 11 次答錯）

**類型 A：正確答案被擋住，回報 unknown（5 次）**

- 最高假設已經正確且 ≥ 0.92，但某個競爭假設一直卡在 0.5–0.65，Verifier 規則 3 永遠不通過。
- Planner 找不到能區分兩者的檢查，只在同一個服務上重複查不同 metric，直到 10 步用完。
- 例：case_018（inventory 記憶體洩漏）3 次都 unknown，`cpu_hot_loop` 卡在 0.60–0.65。
- 原因：v3 加的「沒驗證過的候選保持 0.3–0.6」讓競爭假設太黏，在新題目上反而成為障礙。

**類型 B：錯誤答案被接受（6 次）**

- 例：case_013（inventory 的客戶端憑證過期）有 2 次只用 3 個工具呼叫就被判成 `dependency_unavailable`，從頭到尾沒看過 inventory 的 log。
- 例：case_004（gateway 設定錯誤的 upstream URL）被判成 `dependency_unavailable`，但 inventory 其實正常。
- 原因：Skeptic 的「是否直接檢查過故障元件」本身也是 LLM 判斷，而 gpt-4.1-mini 判斷錯了。

### 為什麼 dev 8/8，held-out 只有 69%？

4 輪調整都針對同樣 8 題，prompt 與規則逐漸貼合這 8 題的特性，也就是**過度擬合開發集**。規格書要求切出 held-out，正是為了抓到這種情況，而它確實抓到了。如果沒有 held-out，這份專案會宣稱「100% 準確、0% 過早診斷」，而那是錯的。

---

## 6. 學到的事

1. **把推理拆成多個結構化 LLM 呼叫，雜訊會累加。**
   萃取證據 → 排序假設 → 審查，每一步都有誤差，小模型尤其明顯。單一 ReAct context 用同樣的領域 prompt，反而更準、便宜 2.6 倍、快 10 倍。
2. **硬規則的可靠度取決於它的輸入。**
   Verifier 規則是確定性的，但它檢查的 confidence 和 label 都是 LLM 產生的。垃圾進、垃圾出。
3. **確定性的防護在輸入也確定時才真正有效。**
   重複呼叫阻擋、反對意見過濾（`open_objections`）、ground-truth 隔離都確實發揮作用，因為它們檢查的是程式可以確認的事實（呼叫過哪個工具），不是 LLM 的估計值。
4. **不能只看工具輸出的摘要。**
   v4 最大的改善來自保留原始輸出，說明「資訊壓縮」本身就是多節點架構的成本。
5. **Held-out 評估是必要的。**
   開發集上的 100% 完全不能代表實力。
6. **Premature Diagnosis 必須用與架構無關的標準定義。**
   如果用本系統自己的 Verifier 條件來判斷，本系統天生滿分。改用 `labels.json` 中的 `key_evidence` 後，兩種架構才能公平比較，也才量得出本系統其實有 25% 過早診斷。

---

## 7. 已知限制

- 遙測資料是模擬的（情境檔），不是真實服務。
- `apply_fix` 只記錄動作，沒有驗證修復後指標是否恢復。
- Held-out 只有 12 題，1 題約等於 8 個百分點，統計意義有限。
- 本系統速度慢（約 280 秒/題），不適合真正的值班情境。
- 只測了 gpt-4.1-mini 一種模型。
- Held-out 集現在已經被看過，**不能再拿來調整**，否則成績會失真。

---

## 8. 後續方向

1. **維持目前結果**：誠實的負面結果搭配嚴謹評估本身就有價值。履歷可寫：
   > Built and evaluated a verifier-based incident agent against a ReAct baseline on a held-out fault-injection benchmark; found it overfit the dev set (100% → 69% held-out) and traced the failures to confidence estimates across chained LLM calls.
2. **繼續改進**：必須先產生一批**新的** held-out 題目。最有希望的方向是用「由證據計算出的確定性分數」取代 LLM 自己給的 confidence。
3. **換更強的模型**（例如 gpt-4.1）重跑兩種架構，看模型變強後 Verifier 架構是否有優勢，預估花費 $3–5。
4. **速度優化**：合併 hypothesis 與 skeptic 的呼叫、只在規則通過時才送原始輸出，降低 token 與延遲。

---

# 第二階段：歸因、Ablation 與更難的 Benchmark

> 開始日期：2026-09-26
> 起點：第一階段 held-out 結果 ReAct 97% vs 本系統 69%。

## 9. 第二階段計畫（追蹤清單）

目標不是「硬調到贏過 ReAct」，而是**找出是哪一層讓準確率下降**，並檢驗「在容易誤導的難題上，驗證機制是否有價值」。

- [x] **Step 0 逐步紀錄**：每一步記下 planner 的選擇、新增的證據、假設排名、verifier 的決定與原因、耗時
- [x] **Step 1 Benchmark v2**：更難、更有鑑別力的題目（強干擾、第一眼會指錯、線索不直白、資料缺失、正確答案是 unknown），分 easy / medium / hard 等級；新的 dev 集與新的 held-out 集，**held-out 在最終評估前不看**
- [x] **Step 2 Ablation**（只在 v2 dev 上）：A ReAct / B Planner+Hypothesis（無 verifier）/ C +硬規則 / D +LLM skeptic（= 原系統）
- [x] **Step 3 歸因與修正**：依逐步紀錄找出每個失敗案例「第一個出錯的節點」，據此修改，只在 dev 上驗證
- [x] **Step 4 最終評估**（中途因 API 額度用完中斷，加值後以 `--resume` 補完，見 10.5–10.6）：在全新的 v2 held-out 上只跑一次
- [x] **Step 5 文件**（README、DEVLOG 已更新為最終數字）：更新 README、DEVLOG

規則：
1. 第一階段的 held-out（`evaluation/labels.json` 的 eval split）不再用於任何決策。
2. v2 題目依「真實情境的模糊性」設計，在跑本系統**之前**定稿，不根據本系統的表現回頭改題目。
3. v1 的 benchmark 與結果保持可重現，不覆蓋。

## 10. 第二階段過程紀錄

### 10.1 Step 0：逐步紀錄（完成）

**做了什麼**
- `IncidentState` 新增 `trace`。每個節點經過 `_traced()` 包裝後，自動記下：節點名稱、第幾步、耗時，以及該節點的決定（planner 的動作與理由、新增的證據、假設排名、verifier 的決定與回饋）。
- ReAct 也記錄每次 agent / tools 呼叫的時間點與動作。
- 結果寫進 `runs.jsonl` 的 `trace` 欄位，之後用來找「第一個出錯的節點」。
- `IncidentAgent` 新增 `verification` 參數，一套程式碼支援 ablation 的各個版本：
  - `plan_hyp`（B）：沒有 verifier，由 planner 決定何時 `conclude`；到步數上限時和 ReAct 一樣採用當下最佳答案
  - `plan_hyp_rules`（C）：只有硬規則
  - `verifier`（D）：硬規則 + LLM skeptic（第一階段的系統）
- Benchmark 支援多個 suite（`--suite v1|v2`），v1 的資料與結果不受影響。

**遇到的問題**
- 用 heredoc 包 Python 修改檔案時出現 `SyntaxWarning: invalid escape sequence '\d'`。檢查後確認是修改腳本本身的字串，寫進檔案的 regex `case_\d{3}` 正確，26 個測試全過。

**意外發現：速度問題的真正原因**
- 第一階段記錄本系統平均 283 秒/題，以為是架構造成的（每步 3 次 LLM 呼叫）。
- Step 0 單獨執行一題（case_010）時，本系統只花 **16.5 秒**，每次 LLM 呼叫約 1–2 秒。
- 所以慢的主因是**多個 run 同時執行時的 API 等待（rate limit 重試）**，不是架構本身。第一階段的「平均時間」欄位在並行評估下不可靠，之後報告時間要特別註明。

### 10.2 Step 1：Benchmark v2（完成，已凍結）

**為什麼要重做**：v1 的 held-out 上 ReAct 已經 97%，題目到頂，分不出架構好壞。v1 的 log 常常直接寫出答案（例如 `total=20, active=20`）。

**v2 的設計原則**（寫在 `evaluation/generate_scenarios_v2.py` 開頭，在跑本系統之前定稿）：
1. **線索不直白**：log 不再點名原因。例如 missing env var 變成 `base_url must be a string, got None`，必須再去看 config 才知道是哪個變數不見了。
2. **同一分鐘的無害部署**：永遠放在「不是故障」的服務上，避免答案有爭議。
3. **第一眼會指錯**：例如 slow query 題目中，pool timeout 的錯誤（1400 筆）遠多於慢查詢警告（300 筆）。
4. **資料缺失**：故障服務的 tracing 關閉，或少一個 metric。
5. **距離更遠**：故障在 1–2 跳之外。
6. **Taxonomy 以外的事故**（磁碟滿、Redis 無法持久化），正確答案是 `unknown`。

**規模**：45 題。dev 18 題（9 種答案 × medium/hard），held-out 27 題（9 種答案 × easy/medium/hard）。case id 全部打亂。新增測試確認 v2 的隔離與平衡（每個 tier 每種答案剛好一題）。v1 的產生器與資料完全沒動。

**難度確認（只跑 ReAct，只在 dev）**：
| | v1 held-out | v2 dev |
|---|---|---|
| ReAct Accuracy | 97% | **72% (13/18)** |
| ReAct False Diagnosis | 3% | **28%** |

ReAct 的錯誤剛好落在設計的陷阱上：`missing_env_var → bad_config_deploy` ×2（看到部署，沒發現變數「不見」）、`unknown → dependency_unavailable` ×2（把磁碟滿硬套成依賴服務掛掉）、`memory_leak → cpu_hot_loop` ×1。

**遇到的問題：LLM 請求卡住**
- 前 7 題每題約 8 秒，之後突然變成約 280 秒。
- 查 trace 發現：某一次 LLM 呼叫卡了 91 秒、下一次卡 183 秒，正好是 timeout（90 秒）的 1 倍和 2 倍，代表**請求在並行負載下卡到 timeout 才重試**。
- 這也解釋了第一階段 283 秒的平均時間。
- 解法：timeout 90 → 30 秒、重試 3 → 6 次（`config.LLM_TIMEOUT_S`、`LLM_MAX_RETRIES`）。正常呼叫只要 1–5 秒，不影響模型行為，只限制卡住的代價。

### 10.3 Step 2：Ablation（v2 dev，每種架構 18 題 × 2 次）

結果：`evaluation/results/v2_dev_20260926-031351/`（`summary.md`、`attribution.md`）

| 架構 | Accuracy | False Diagnosis | Premature | 工具呼叫 | Token |
|---|---|---|---|---|---|
| A. ReAct | **26/36 (72%)** | 25% | 6% | 7.7 | 18k |
| B. Planner + Hypothesis（無 verifier） | 24/36 (67%) | 33% | **0%** | 8.3 | 48k |
| C. B + 硬規則 | 14/36 (39%) | 47% | **56%** | 4.3 | 21k |
| D. C + LLM skeptic（第一階段系統） | 17/36 (47%) | 33% | 19% | 6.9 | 40k |

**失敗歸因（`evaluation/attribution.py`）**

| 類別 | A | B | C | D |
|---|---|---|---|---|
| planner 沒查關鍵證據就結束 | – | – | **15** | 5 |
| hypothesis 從未把正解排第一 | – | 9 | – | – |
| 正解曾在第一、後來被帶走 | – | 3 | 1 | 2 |
| verifier 接受了錯誤答案 | – | – | 1 | 5 |
| 正解在第一，卻被規則擋到步數用完 | – | – | 4 | 3 |
| 步數用完且第一名是錯的 | – | – | 1 | 3 |
| ReAct 查了關鍵證據仍答錯 | 9 | – | – | – |
| **總錯誤** | 9 | 12 | 22 | 18 |

**發現**
1. **最大的下降來自硬規則（B→C，−28 分），而且原因跟設計初衷相反。** 硬規則本來是要「防止過早下結論」，實際上卻變成「提早結束的觸發條件」：LLM 自報的 confidence 很快就衝到 0.8，規則一通過就結束。Premature 從 0% 暴增到 56%，工具呼叫從 8.3 降到 4.3。沒有規則的 B 反而查得最完整（premature 0%）。
2. **結構本身沒有幫助（A→B，−5 分）。** 獨立的 hypothesis 節點會誤讀證據（例如把 401 invalid_token 排成 dependency_unavailable，9 次「從未把正解排第一」），token 是 ReAct 的 2.7 倍。
3. **Skeptic 修回一部分（C→D，+8 分）**，但也會擋掉正確答案。
4. **所有架構在 `missing_env_var` 都是 0/4。** 看到「剛部署 + 設定值是 None」時，模型一致判成 `bad_config_deploy`。要推論「某個變數不見了」，必須知道服務原本需要 `PAYMENT_PROVIDER_URL`，但題目裡沒有任何地方說明這點，**這題可能本身有歧義**。因為 benchmark 已凍結，而且四種架構同樣答錯、不偏袒任何一方，所以不修改，記錄為已知限制。
5. **Taxonomy 以外的事故（unknown）幾乎全錯**，模型傾向把磁碟滿硬套成 `dependency_unavailable`。

**遇到的問題**
- Ablation 中 ReAct 與 D 各有 1 次 run 出錯（計為答錯），另外檢查原因。

### 10.4 Step 3：依歸因結果修改

**修 bug**
- D 有 1 次 run 崩潰：skeptic 編了一個不存在的工具名稱 `get_service_logs`，Pydantic 的 `Literal` 驗證失敗，整個 run 中止。改成 `check_tool: str`，`open_objections` 丟掉工具名稱無效的反對意見，不讓單一欄位錯誤毀掉整個 run。
- ReAct 有 1 次在重試 6 次後仍 timeout，屬於 API 端偶發問題，不處理。

**新的驗證階段（E / F）**，針對 Step 2 找到的主因：「停止條件依賴 LLM 自報、快速膨脹的 confidence」。
1. **每種原因一份證據檢查表（checklist），由程式判斷**（`agent/verifier.py` 的 `CHECKLISTS`）。性質類似 runbook：要判定 `bad_config_deploy`，必須看過那個服務的 config；要怪 DB，必須看過 DB metrics 或 trace。假設多了「故障在哪個服務」欄位，讓檢查表知道要查誰。
2. **Rule 3 改成差距規則**：第一名必須領先第二名 ≥ 0.3，取代「第二名 < 0.5」。後者會讓黏著在 0.5–0.6 的競爭假設一直擋住正確答案。
3. **不通過時，回饋直接列出還缺哪個工具呼叫**，讓 planner 知道下一步要做什麼。
4. 保留 source 種類 ≥ 2 與 confidence ≥ 0.8。

兩個新架構：
- **E. `plan_hyp_checklist`**：B + 上述規則（沒有 skeptic）
- **F. `verifier_v2`**：E + skeptic（只看定義是否符合與反對意見；「是否直接檢查過」改由檢查表在程式中判斷）

**要誠實註明的地方**
- 檢查表和評估用的 `key_evidence` 背後是同一套領域常識（「要判斷 X，就要看 Y」）。所以 E/F 的 Premature Diagnosis 會**部分因設計而下降**，不能拿這個指標當作 E/F 比較好的主要證據。**真正的檢驗是 Accuracy 與 False Diagnosis。**
- 檢查表寫的是「每種原因」的通用規則，不是針對個別題目的答案。
- 為了讓 hypothesis 輸出「故障服務」，hypothesis prompt 多了一行，這也會影響 B/C/D。最終 held-out 評估時所有架構都用同一份最終程式碼，比較仍然公平。

**E / F 在 v2 dev 的結果**（`evaluation/results/v2_dev_20260926-040832/`）

| 架構 | Accuracy | False Diag. | Premature | 工具呼叫 |
|---|---|---|---|---|
| A. ReAct | **72%** | 25% | 6% | 7.7 |
| B. Planner + Hypothesis | 67% | 33% | 0% | 8.3 |
| C. B + 第一階段硬規則 | 39% | 47% | 56% | 4.3 |
| **E. B + 檢查表 & 差距規則** | **64%**（比 C **+25**） | 28% | 25% | 5.3 |
| D. C + skeptic | 47% | 33% | 19% | 6.9 |
| **F. E + skeptic** | **64%**（比 D **+17**） | 31% | 22% | 6.3 |

- 修改有效：把規則層換掉後，verifier 架構從 39% / 47% 回升到 64%，證實 Step 2 的歸因正確（問題出在「依賴 LLM confidence 的停止條件」）。
- 但仍然**沒有超過 B（無 verifier）或 ReAct**。剩下的錯誤主要是模型把證據讀錯（`missing_env_var` 全錯、`unknown` 多半錯），這類錯誤任何驗證規則都攔不到：規則只能要求「查過」，不能保證「讀對」。
- E/F 仍有 22–25% premature：它們查了**自己答案**要求的證據，但答案本身是錯的，所以沒查到**正確答案**需要的證據。

**決定：停止調整，直接做最終評估。** dev 只有 18 題，再調下去會重演第一階段「對 dev 過度擬合」的錯誤。設計在此凍結。

### 10.5 Step 4：最終評估（中斷：API 額度用完）

**執行內容**：在 v2 held-out（27 題，之前從未跑過）上跑 A / B / D / E / F，每題 2 次，共 270 次 run。設計在啟動前已凍結。
結果目錄：`evaluation/results/v2_heldout_20260926-043327/`

**遇到的問題 1：OpenAI 額度用完**
- 跑到一半，OpenAI 回傳 `429 insufficient_quota`（"You have no credits remaining"）。之後的每一次呼叫都失敗。
- 結果：ReAct 54/54 完成；B 44/54 完成；**D、E、F 全部 54 次都失敗**。
- 這不是程式錯誤，但這次最終評估**沒有完成**。

**遇到的問題 2：計分 bug（因此被發現並修正）**
- 失敗的 run 預設答案是 `unknown`。在「正確答案本來就是 unknown」的題目上，失敗的 run 被算成**答對**，D/E/F 因此在 unknown 題目上出現 6/6。
- 修正：`score_run` 規定失敗的 run 永遠不算答對；各種表格改為把失敗顯示成 `ERROR`。新增測試。
- 重新計算所有 v2 結果：dev 的數字不變（dev 的 2 次失敗剛好都不在 unknown 題目上）；held-out 的 B 從 34 修正為 32。

**新增功能：可續跑的評估**
- `python -m evaluation.run_eval --resume <結果目錄>`：保留成功的 run，只重跑缺少或失敗的，設定沿用原本的 `meta.json`。
- 偵測到 `insufficient_quota` 就立刻停止派新的 run，而且不記錄這些失敗，避免再產生幾百筆無用的錯誤紀錄。
- 用假的 `run_incident` 寫了 2 個測試（不需要呼叫 API）。

**目前已完成部分的 held-out 結果（尚不完整，不能下最終結論）**
| 架構 | Accuracy | False Diag. | Premature |
|---|---|---|---|
| A. ReAct | 41/54 (76%) | 19% | 9% |
| B. Planner + Hypothesis | 32/54（10 次失敗計為錯；有效 run 為 32/44） | 19% | 4% |
| D / E / F | 尚未執行 | | |

**為什麼補跑仍然合法**：held-out 的 ReAct 與 B 結果雖然已經看到，但 D/E/F 的設計在 held-out 開跑之前就已凍結，補跑時**不會修改任何程式或 prompt**，只是把同一個實驗跑完。

**下一步**（需要使用者操作）：到 OpenAI 帳戶加值後，執行
```
python -m evaluation.run_eval --resume evaluation/results/v2_heldout_20260926-043327
```
預估補跑 172 次，約 $3。

**第二階段 API 花費（到目前為止）**：約 $4.63。

### 10.6 Step 4：補跑完成與最終結果

**補跑過程**
1. 使用者加值後，先用一次簡單呼叫確認 API 可用。
2. `--resume` 保留原本 98 次成功的 run，補跑 172 次，**沒有修改任何程式或 prompt**。
3. 補跑後又出現 15 次錯誤：14 次是**速率限制**（每分鐘 token 用量超過帳戶上限，重試 6 次仍失敗），1 次是 skeptic 少填一個欄位（`objections.0.why`）。這些都和架構好壞無關，所以把並行數從 4 降到 2，再用 `--resume` 重跑這 15 次，全部成功。
   - 先排除錯誤計算時，排名已經是 A > B > D > E > F；重跑後只有數字變乾淨，排名沒有翻轉。
4. 最後 270 次 run 全部成功。

**最終結果（v2 held-out，27 題 × 2 次）**
`evaluation/results/v2_heldout_20260926-043327/`

| 架構 | Dev | **Held-out** | False Diag. | Premature | 每次都答對 |
|---|---|---|---|---|---|
| A. ReAct | 72% | **76%** | 19% | 9% | 18/27 |
| B. Planner + Hypothesis | 67% | **70%** | 24% | 4% | 17/27 |
| D. 第一階段系統 | 47% | **56%** | 26% | 9% | 11/27 |
| E. 檢查表 & 差距規則 | 64% | **50%** | 44% | 31% | 13/27 |
| F. E + skeptic | 64% | **52%** | 37% | 19% | 10/27 |

依難度：ReAct 在 easy / medium / hard 分別答對 15 / 13 / 13（每級 18 次）；所有 verifier 版本在 hard 只有 7–8。

**失敗歸因（held-out）**：E 的 27 次錯誤中有 15 次是「沒查關鍵證據就下結論」。

### 10.7 第二階段結論

1. **在兩套 benchmark、dev 與 held-out 上，排名都一致：ReAct 最好，無 verifier 的結構化版本第二，任何 verifier 版本最差。** 用 gpt-4.1-mini 時，加上驗證關卡沒有幫助。
2. **我的修改（E/F）沒有泛化。** 在 dev 上從 39% 救回 64%，到 held-out 只剩 50–52%，甚至沒有贏過第一階段的 D（56%）。E/F 是依據 dev 的錯誤設計出來的，18 題的 dev 又一次被過度擬合，和第一階段一樣，也同樣是被 held-out 抓到。
3. **檢查表為什麼失效**：它檢查的是「有沒有查過**你自己的答案**需要的證據」。錯誤的答案一樣能滿足。例如把憑證過期誤判成 `dependency_unavailable`，只要看過那個服務的 log，檢查表就通過了。E 的「沒查關鍵證據」錯誤因此高達 15 次。
4. **驗證關卡在難題上傷害最大**（hard：ReAct 13/18 vs verifier 7–8/18），而難題正是原本期待驗證機制發揮作用的地方。
5. **確實有效的部分**：逐步紀錄 + 失敗歸因讓每個結論都能追溯；ablation 正確找出「依賴 LLM confidence 的停止條件」會讓 agent 提早結束；可續跑的評估讓中斷的實驗能在不改設計的前提下補完。
6. **下一步若要繼續**：信心度改用多次抽樣的一致性（self-consistency），並且 ReAct 也要一起加上以保持公平；需要一批全新的 held-out 題目。研究文獻支持這個方向：LLM 自報的信心度偏高（Xiong et al., ICLR 2024），沒有外部回饋時 LLM 很難自我修正（Huang et al., ICLR 2024）。

**第二階段 API 花費**：約 $7.3（只計算最後保留的 run；因額度用完或速率限制而失敗、後來重跑的 run 未計入，實際帳單會略高）。

**履歷可用的描述**
> Built a LangGraph + MCP incident-response agent and two fault-injection benchmarks (65 scenarios, frozen dev/held-out splits, ground-truth isolation). Ran a 6-variant ablation with per-node failure attribution: an LLM-confidence stopping gate cut dev accuracy from 67% to 39%; a checklist fix recovered it on dev but not on held-out (50% vs ReAct 76%), which traced the gap to verification gates built on LLM judgments.

