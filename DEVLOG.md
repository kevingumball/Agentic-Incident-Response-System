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
