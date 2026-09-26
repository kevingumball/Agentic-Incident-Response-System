# Agentic Incident Response System — 規格書

> 版本：v0.2（精簡版）
> 日期：2026-09-25
> 作者：Kevin

---

## 1. 主題

**Agentic Incident Response System**

當服務發生異常（例如 latency 暴增、錯誤率上升）時，AI Agent 會自己查 metrics / logs / traces、提出假設、驗證假設，最後給出 root cause 與修復建議，修復動作須經人類核准。

重點：這不是「貼 log 問 chatbot」，而是 Agent **自己決定要查什麼、查到什麼再決定下一步**，證據不足時不下結論。

---

## 2. 目標

| # | 目標 |
|---|------|
| G1 | 收到 alert 後自主完成調查，輸出 root cause |
| G2 | 以 hypothesis-driven 方式調查：每個結論附支持 / 反對證據與 confidence |
| G3 | 修復動作必須經過 Human Approval |
| G4 | 用有標準答案的 benchmark 量化效果，並與 ReAct baseline 比較 |

**不做（Non-goals）**：不架真實微服務、不接 Prometheus / Grafana / OpenTelemetry、不做向量資料庫記憶。這些列在第 11 節「未來擴充」。

---

## 3. 使用工具

| 類別 | 選擇 |
|------|------|
| 語言 | Python 3.11+ |
| Agent 框架 | LangGraph |
| LLM | OpenAI `gpt-4.1-mini`（可在 config 切換） |
| 結構化輸出 | Pydantic + `with_structured_output` |
| 工具協定 | MCP（`mcp` Python SDK / FastMCP）+ `langchain-mcp-adapters` |
| 介面 | CLI（Rich 套件顯示每一步） |
| 評估 | 自寫 evaluation script |

---

## 4. 系統架構

```
 Incident 情境（JSON）
        │  產生
        ▼
 模擬觀測資料（metrics / logs / traces）
        │
        ▼
 MCP Server（observability tools）
        │  MCP
        ▼
 LangGraph Agent
 Triage → Planner → Tool → Hypothesis → Verifier ─┐
             ▲                                    │ 證據不足
             └────────────────────────────────────┘
        │ 證據充足
        ▼
 Root Cause → 修復建議 → Human Approval → 報告
        │
        ▼
 Evaluation（比對標準答案）
```

### 模擬資料層

不架真的服務，而是為每個 incident 寫一個情境檔，工具從情境檔讀資料回傳。

**情境檔（`scenarios/case_003.json`）只放觀測資料，不含答案：**

```json
{
  "case_id": "case_003",
  "alert": "checkout-service p95 latency 180ms → 3.4s, 5xx 0.3% → 8.7%",
  "metrics": {
    "checkout": {"latency_p95_ms": [180, 190, 3100, 3400], "error_rate": [0.003, 0.004, 0.08, 0.087]},
    "database": {"pool_in_use": [2, 3, 5, 5], "pool_size": 5, "cpu": [0.2, 0.2, 0.21, 0.19]}
  },
  "logs": {
    "checkout": [
      {"level": "ERROR", "msg": "timeout acquiring connection from pool after 3000ms"},
      {"level": "WARN", "msg": "cache miss rate elevated"}
    ]
  },
  "traces": {
    "slow_example": [
      {"span": "POST /checkout", "ms": 3400},
      {"span": "db.acquire_connection", "ms": 3100},
      {"span": "db.query", "ms": 40}
    ]
  },
  "config": {"checkout": {"DB_POOL_SIZE": 5}}
}
```

**標準答案另存於 `evaluation/labels.json`：**

```json
{
  "case_003": {
    "root_cause": "db_pool_exhaustion",
    "split": "eval",
    "key_evidence": [
      {"tool": "get_service_metrics", "service": "database"},
      {"tool": "search_logs", "service": "checkout"}
    ]
  }
}
```

`key_evidence`：要把這個 case 和症狀相似的其他 incident 區分開，**至少得查過的工具**（例如 pool 使用率與 DB CPU 才能分辨 `db_pool_exhaustion` 和 `slow_db_query`）。用來計算 Premature Diagnosis Rate（第 8 節）。

### Ground-truth 隔離

- 答案和觀測資料放在**不同檔案**，MCP server 只讀 `scenarios/`，程式碼中完全不 import `labels.json`
- 只有 `evaluation/run_eval.py` 會讀 `labels.json`
- 因此 Agent、Prompt、MCP Server、Tool output 都不可能接觸到答案
- README 可明確寫：*Ground-truth labels were isolated from the agent and tool layer.*

工具介面要設計成日後可直接換成真實後端（Prometheus 等）而不改 Agent。

---

## 5. Incident 類型

| Label | Agent 看得到的症狀 |
|-------|------------------|
| `db_pool_exhaustion` | latency ↑、pool 100%、connection timeout log、DB CPU 正常 |
| `slow_db_query` | latency ↑、db.query span 慢、DB CPU 高、pool 未滿 |
| `missing_env_var` | 特定 route 100% 500、`KeyError` log |
| `dependency_unavailable` | 下游呼叫 connection refused、下游 health 失敗 |
| `memory_leak` | memory 持續上升、OOM restart |
| `cpu_hot_loop` | CPU 飆高、所有 route 變慢 |
| `expired_credential` | 對外部服務 401/403 |
| `bad_config_deploy` | 最近一次 deploy 後開始出錯 |

**Benchmark**：以上 8 種 × 2–3 個變體 ≈ **20 個 case**，分成兩組：

| Split | 數量 | 用途 |
|-------|------|------|
| Development set | 8（每種 incident 各 1） | 寫 prompt、調 Verifier 門檻時**只看這組** |
| Held-out evaluation set | 12 | 所有調整完成後才跑，作為最終成績 |

避免「一直改 prompt 直到 20 題全對」的過度擬合。由於 eval set 只有 12 題（1 題 ≈ 8%），報告時同時列出答對題數，例如 `10/12`。

設計原則：
- log 不能直接寫出答案，要像真實系統的訊息
- 放入症狀相似的對照組（例如 `db_pool_exhaustion` vs `slow_db_query`）
- 大部分 case 加入**與 root cause 無關的異常訊號（red herring）**，測試 Agent 會不會因為看到第一個異常就下結論。例如：

```
Alert:   checkout latency ↑
Metrics: DB pool 100%，cache miss rate ↑      ← cache miss 是干擾
Logs:    "cache miss rate elevated"            ← 干擾
         "timeout acquiring connection"        ← 真正線索
Trace:   db.acquire_connection = 3.1s, db.query = 40ms
```

沒有干擾訊號的話題目太簡單，Verifier 也就沒有存在的必要。

---

## 6. Agent 工具（MCP Server）

| Tool | 類型 | 說明 |
|------|------|------|
| `get_service_metrics(service, metric)` | 唯讀 | 回傳時間序列摘要（baseline、目前值、變化倍數） |
| `search_logs(service, query)` | 唯讀 | 回傳符合的 log 與依錯誤類型的統計 |
| `get_trace(service)` | 唯讀 | 回傳慢 request 的 span 與各 span 耗時占比 |
| `get_service_config(service)` | 唯讀 | 設定值與最近 deploy 紀錄 |
| `apply_fix(service, change)` | **寫入（模擬）** | 只能在 Human Approval 後呼叫 |

工具回傳**摘要**而不是大量原始資料，避免塞爆 context。

`apply_fix` 只做模擬：不真的修改任何設定，只把動作記錄到 action log 並回傳「已套用（simulated）」。流程為 `Proposal → Human Approval → Simulated apply → Record action`。真正套用修復並驗證 metrics 恢復，放在第 11 節「未來擴充」。

---

## 7. Agent 設計

### 7.1 State

```python
class Evidence(TypedDict):
    source: Literal["metrics", "logs", "traces", "config"]
    service: str
    observation: str         # 一句話結論
    supports: list[str]      # 支持的 hypothesis labels
    contradicts: list[str]   # 反對的 hypothesis labels

class Hypothesis(TypedDict):
    label: str               # 必須是第 5 節的 label 或 "unknown"
    confidence: float

class ToolCall(TypedDict):
    tool: str
    args: dict               # e.g. {"service": "checkout", "query": "timeout"}
    reason: str              # Planner 選這個工具的理由
    step: int

class IncidentState(TypedDict):
    alert: str
    service: str
    symptoms: list[str]
    severity: str
    evidence: Annotated[list[Evidence], operator.add]
    hypotheses: list[Hypothesis]
    actions_taken: Annotated[list[ToolCall], operator.add]
    next_action: ToolCall | None
    last_observation: str
    verifier_feedback: str   # 回饋給 Planner 的「還缺什麼證據」
    step_count: int
    status: Literal["investigating", "diagnosed", "undetermined"]
    root_cause: Hypothesis | None
    remediation: dict | None
    approved: bool | None
    fix_result: str | None
    report: str
```

`actions_taken` 用結構化的 `ToolCall` 而不是字串，evaluation 才能判斷「有沒有查過某個 service 的某種資料」（Premature Diagnosis 需要）。

Evidence 範例：

```python
{
    "source": "traces",
    "service": "checkout",
    "observation": "db.acquire_connection consumed 91% of request time",
    "supports": ["db_pool_exhaustion"],
    "contradicts": ["slow_db_query"]
}
```

Evidence 帶有 `source` 與 `supports` / `contradicts`，Verifier 才能用程式判斷「支持證據來自幾種來源」，evaluation 與 debug 時也能看出每個結論是由哪些證據推出來的。Hypothesis 的支持 / 反對證據直接從 `evidence` 反查，不另外重複存。

和現有 calculator agent 的差別：calculator 只用 `MessagesState`（對話紀錄）；這裡把調查進度存成結構化欄位，每個 node 只讀寫自己負責的部分。

### 7.2 流程

```
START
  ↓
Triage          alert → service / symptoms
  ↓
Planner ◄─────────────────┐   決定下一個最有用的工具
  ↓                       │
Tool Executor             │   透過 MCP 執行
  ↓                       │
Hypothesis Updater        │   整理 evidence，更新假設與 confidence
  ↓                       │
Verifier ── 不足 ─────────┘
  │  └── 達步數上限 ──► Report（未確定，附目前最佳假設）
  ↓ 充足
Remediation     產生修復建議（例如 DB_POOL_SIZE 5 → 20）
  ↓
Human Approval  interrupt()，等待 approve / reject
  ↓
Report          root cause、證據、採取的動作
  ↓
END
```

### 7.3 Verifier 規則

LLM 判斷之外，還要**同時**通過硬規則才算證據充足：

1. 最高假設 confidence ≥ 0.8
2. 支持它的 evidence 至少來自 2 種不同 `source`（例如 metrics + logs）
3. 沒有尚未排除的高信心競爭假設：第二名 confidence < 0.5

```
H1 db_pool_exhaustion 0.91 / H2 slow_db_query 0.22  → 可以結束
H1 db_pool_exhaustion 0.82 / H2 slow_db_query 0.73  → 不能結束，繼續找區分兩者的證據
```

不強制「一定要排除一個假設」，避免很明顯的 case 為了湊證據多呼叫工具。規則 1、3 的門檻（0.8 / 0.5）只用 development set 調整。

### 7.4 Guardrails

- 最多 10 步，超過就輸出「未確定」報告並附目前最佳假設
- 同一工具 + 同參數不重複呼叫
- 寫入工具只在 Approval 節點之後可用

---

## 8. Evaluation

### 8.1 指標

| 指標 | 說明 |
|------|------|
| Root Cause Accuracy | 預測 label 是否等於標準答案 |
| False Diagnosis Rate | 高信心但答錯的比例 |
| Premature Diagnosis Rate | 在查過該 case 的 `key_evidence` 之前就輸出 diagnosis 的比例（不論答對或答錯） |
| Avg Tool Calls | 每個 case 平均工具呼叫數 |
| Tokens / Cost per Case | 每個 case 的 token 用量 |

**Premature Diagnosis Rate** 直接衡量本系統的核心主張：「證據不夠就不下結論」。它不是用本系統自己的 Verifier 條件來判斷（那樣本系統等於天生滿分，對 ReAct 不公平），而是用 `labels.json` 中與架構無關的 `key_evidence`，從兩種架構的 tool call 紀錄計算。猜對但沒查關鍵證據的情況也算 premature。

### 8.2 比較實驗

**ReAct-style baseline**：a single LLM agent iteratively selects observability tools based on tool outputs until it produces a root-cause diagnosis, without explicit planner, hypothesis tracking, or verifier nodes.

```
ReAct baseline                 本系統
START                          Planner
  ↓                              ↓
Agent ◄──────┐                 Tool
  ↓          │                   ↓
Tool? ─Yes─► Tool              Evidence
  ↓ No                           ↓
Diagnosis                      Hypothesis
                                 ↓
                               Verifier ──不足──► Re-plan（回 Planner）
```

（實作上可由現有 calculator agent 的 `agent ↔ tools` 迴圈改寫而來。）

為了公平比較，兩者使用**相同的模型、相同的 MCP 工具、相同的步數上限、相同的輸出格式**（root cause label + confidence），唯一差別是 graph 結構。

**最終成績只用 held-out evaluation set。** 每個 case 跑 3 次，用來衡量 run-to-run robustness（LLM 的隨機性），12 題 × 3 次 = 36 runs。報告時：

- Accuracy 以成功次數表示，例如 `30 / 36 runs (83%)`
- 另外列出 **3 次都答對的 case 數**，例如 `9 / 12 cases`，看出結果是否穩定

預期結果範例（數字為示意，實際以跑出來的為準）：

| 架構 | Accuracy | False Diagnosis | Premature Diagnosis | Avg Tool Calls | Cost / Case |
|------|----------|-----------------|---------------------|----------------|-------------|
| ReAct | 24/36 (67%) | 25% | 29% | 6.8 | $0.0x |
| Planner + Hypothesis + Verifier | 30/36 (83%) | 8% | 5% | 5.4 | $0.0x |

---

## 9. Repo 結構

```
agentic-incident-response/
├── agent/
│   ├── graph.py
│   ├── state.py
│   ├── nodes.py        # triage / planner / hypothesis / verifier / remediation
│   ├── prompts.py
│   └── baseline_react.py
├── mcp_server/
│   └── observability_server.py
├── scenarios/          # 每個 incident 一個 JSON（只有觀測資料）
├── evaluation/
│   ├── labels.json     # 標準答案 + dev/eval split（只有 run_eval.py 讀）
│   ├── run_eval.py
│   └── results/
├── main.py             # CLI demo
├── .env.example
└── README.md
```

---

## 10. 開發步驟（約 3–5 週）

| 週 | 內容 |
|----|------|
| 1 | 寫 3–4 個 scenario JSON；工具先用一般 `@tool` 讀 JSON；做出 ReAct 版本（改自 calculator） |
| 2 | 自訂 `IncidentState`，完成 Triage → Planner → Tool → Hypothesis → Verifier 迴圈 |
| 3 | 工具搬到 MCP server；加入 Remediation + Human Approval（`interrupt()`） |
| 4 | 擴充到 ~20 個 case；寫 evaluation script，跑 ReAct vs 本系統比較 |
| 5 | CLI demo 美化、README（架構圖、結果表、demo GIF） |

---

## 11. 未來擴充（非本次範圍）

- 用 FastAPI + PostgreSQL 建真實服務，實際注入故障
- 接 OpenTelemetry / Prometheus / Grafana，替換模擬資料層
- Qdrant 儲存歷史 incident 與 runbook 作為記憶
- 修復後重新查 metrics，確認 incident 已解除

---

## 12. 完成標準

- [ ] `python main.py --case case_003` 可跑完整流程並顯示每一步
- [ ] 修復動作必定經過 Human Approval
- [ ] 約 20 個 case 的 benchmark（dev 8 / held-out 12）與 evaluation script
- [ ] 標準答案與 Agent / 工具層完全隔離
- [ ] ReAct vs 本系統在 held-out set 上的比較結果表（Accuracy、False Diagnosis、Premature Diagnosis、Tool Calls、Cost）
- [ ] `apply_fix` 為模擬執行，只記錄動作
- [ ] README 含架構圖、demo、結果

---

## 13. 履歷描述範例

> Built an agentic incident-response system with LangGraph and MCP that autonomously diagnoses service incidents through hypothesis-driven investigation (planner / verifier loop, human-in-the-loop remediation). On held-out incident variants with injected red-herring signals, achieved X% root-cause accuracy vs Y% for a ReAct baseline, using Z% fewer tool calls.
