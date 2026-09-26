# Agentic Incident Response

An LLM agent that investigates production incidents the way an on-call SRE does: it chooses
which observability data to pull, records structured evidence, maintains competing root-cause
hypotheses, and **refuses to conclude until a verifier accepts the evidence**. Fixes are only
applied after human approval.

Built with **LangGraph** (explicit state machine), **MCP** (tools served by a separate
observability server), and evaluated on a **fault-injection benchmark with held-out cases and
red-herring signals** against a ReAct baseline.

## Results (held-out set, 12 cases × 3 runs, `gpt-4.1-mini`)

| Architecture | Accuracy | Cases correct in every run | False Diagnosis | Premature Diagnosis | Unknown | Avg Tool Calls | Cost / Case |
|---|---|---|---|---|---|---|---|
| ReAct baseline | **35/36 (97%)** | **11/12** | **3%** | **8%** | 0% | 6.8 | **$0.007** |
| Planner + Hypothesis + Verifier | 25/36 (69%) | 7/12 | 14% | 25% | 17% | 6.5 | $0.018 |

Full output: [evaluation/results/eval_20260925-113329/summary.md](evaluation/results/eval_20260925-113329/summary.md)

**On the held-out set the structured verifier pipeline did not beat the ReAct baseline.** It reached
8/8 on the development set after four tuning iterations (see *Development log*), and the drop on held-out
cases is the overfitting the dev/held-out split exists to catch. Failure analysis of the 11 wrong runs:

- **Correct answer blocked (5 runs, reported *unknown*).** The top hypothesis was already right at
  ≥ 0.92, but a competitor stayed at 0.5-0.65, so hard rule 3 kept failing. The planner did not find a
  discriminating check and spent the rest of the budget re-querying the same service.
- **Wrong answer accepted (6 runs).** For example, an expired client certificate was accepted as
  `dependency_unavailable` after 3 calls, without the failing service's logs being read. The reviewer's
  "inspected directly" judgment is itself an LLM call and was wrong.
- **Takeaway:** with a small model, splitting reasoning across several structured LLM calls
  (extract → rank → review) compounds per-call noise. The verifier's hard rules are only as good as the
  LLM-produced confidences and labels they check. A single ReAct context with the same domain prompt was
  both more accurate and 2.6× cheaper. Deterministic guards worked where their inputs were deterministic
  (duplicate-call blocking, objection filtering, ground-truth isolation), but not on top of LLM-estimated
  confidences.

## Why this is not a chatbot

| Chatbot / single-shot | This system |
|---|---|
| You paste logs, it guesses | Agent decides what to query next (metrics, logs, traces, config) |
| Conversation history is the only state | Typed `IncidentState`: evidence log, ranked hypotheses, tool calls, verifier feedback |
| Answers as soon as something looks wrong | Hard verifier rules + skeptical reviewer must accept before a diagnosis is reported |
| Can't be trusted to act | Write actions go through a LangGraph `interrupt()` for human approval |
| "Seems to work" | Accuracy, false / premature diagnosis rate, tool calls and cost on a held-out benchmark |

## Architecture

```
 scenarios/case_XXX.json ──► MCP observability server (stdio)
 (observable data only)       tools:  get_service_metrics  search_logs  get_trace
                                      get_service_config   apply_fix (write, simulated)
                              resource: alert://current
                                         │ MCP
                                         ▼
 ┌──────────────────────── LangGraph agent ────────────────────────┐
 │ triage → planner → executor → hypothesis → verifier ─┐          │
 │             ▲                                        │ not yet   │
 │             └──────────── feedback ──────────────────┘           │
 │ verifier ─accepted─► remediation → human_approval ─► apply_fix   │
 │ verifier ─budget exhausted─► report (undetermined)   → report    │
 └───────────────────────────────────────────────────────────────────┘
                                         │
 evaluation/labels.json ───────────► evaluation harness (only reader of ground truth)
```

| Node | LLM | Responsibility |
|---|---|---|
| `triage` | yes | Alert → service, symptoms, severity |
| `planner` | yes | Pick the single most informative next check (tool + args + reason) |
| `executor` | no | Call the MCP tool; block duplicate calls |
| `hypothesis` | yes | Extract grounded evidence (`source`, `supports`, `contradicts`) and re-rank hypotheses |
| `verifier` | rules + LLM | Hard rules first, then a skeptical reviewer; otherwise feedback goes back to the planner |
| `remediation` | yes | One-line concrete change + follow-up steps |
| `human_approval` | no | `interrupt()`; resumes with approve / reject |
| `apply_fix` | no | Calls the (simulated) write tool over MCP |
| `report` | no | Markdown incident report |

### Verifier

A diagnosis is accepted only if **all** hard rules pass ([agent/verifier.py](agent/verifier.py)):

1. top hypothesis confidence ≥ 0.8
2. its supporting evidence comes from ≥ 2 different source types (metrics / logs / traces / config)
3. no competing hypothesis ≥ 0.5

**and** an LLM reviewer confirms that the evidence matches the label's definition, that the faulty
component was inspected directly, and that no alternative label is still consistent with all
evidence. Otherwise the reasons are fed back to the planner. After 10 tool calls the agent
reports *undetermined* with its best hypothesis instead of guessing.

### Structured state

```python
class Evidence(TypedDict):
    source: Literal["metrics", "logs", "traces", "config"]   # set from the tool, not by the LLM
    service: str
    observation: str
    supports: list[str]      # root-cause labels
    contradicts: list[str]
    step: int
```

Because evidence carries its source, rule 2 is checked in code, and every conclusion in the report
is traceable to the tool call that produced it.

## Benchmark

`evaluation/generate_scenarios.py` builds a simulated 6-service system
(api-gateway → checkout → inventory / payment / PostgreSQL / Redis), injects one fault per case,
and adds unrelated anomalies as red herrings (cache-miss spikes, unrelated deploys, mild DB CPU,
Redis evictions, noisy warnings).

- **8 root causes:** `db_pool_exhaustion`, `slow_db_query`, `missing_env_var`,
  `dependency_unavailable`, `memory_leak`, `cpu_hot_loop`, `expired_credential`, `bad_config_deploy`
- **20 cases: 8 development / 12 held-out.** Prompts and thresholds were tuned on the dev set
  only; the held-out set was run once at the end.
- **Confusable pairs on purpose**, e.g. pool exhaustion vs. slow query (both fill the pool; only
  traces / DB metrics tell them apart), dependency down vs. expired credential vs. bad config.
- **Faults surface away from their origin**: many alerts fire on `api-gateway` or `checkout` while the
  fault lives in `inventory`, `payment` or the database.

### Development log (dev set only)

Every change below was driven by failures on the **8 dev cases**; the held-out set was not looked
at until the design was frozen.

| Version | Failure found on dev | Change | Dev accuracy | Premature |
|---|---|---|---|---|
| v1 | Concluded after 2-3 calls. Evidence was not grounded (the planner's log *query* was recorded as log *content*); every item "contradicted" 6-8 causes, so competitors dropped to ~0 and verifier rule 3 passed trivially | - | 5/8 | 50% |
| v2 | - | Evidence must quote the latest tool output; skeptic checks definition match, direct inspection and remaining alternatives | 2/8 | 25% |
| v2 → v3 | Over-correction: 5 runs exhausted the budget. The skeptic kept raising objections no tool could settle ("do CPU profiling") | **Objections must name a not-yet-run check (tool + service); objections whose check was already run are dropped in code** ([`open_objections`](agent/verifier.py)) | 5/8 | 12% |
| v3 → v4 | Information loss: nodes only saw one-line evidence summaries, so details in raw outputs (a slow downstream span, a deploy that removed a variable) were lost between steps | Keep the full raw observation history in state alongside the evidence index; cap `supports` / `contradicts` at 2 labels per item | **8/8** | **0%** |

### Ground-truth isolation

Observable data (`scenarios/`) and answers (`evaluation/labels.json`) are separate files. The MCP
server only reads `scenarios/`, the agent only talks to the MCP server, and only the evaluation
harness reads the labels. Case ids are shuffled, and
[tests/test_isolation.py](tests/test_isolation.py) asserts that no agent / server module
references the labels and that no scenario contains a label name.

### Metrics

| Metric | Definition |
|---|---|
| Accuracy | predicted label == ground truth (reported as correct runs / total runs) |
| Cases correct in every run | robustness across repeated runs |
| False Diagnosis Rate | wrong label with confidence ≥ 0.8 |
| Premature Diagnosis Rate | a diagnosis given before the case's key discriminating evidence was queried (right or wrong) |
| Avg tool calls / tokens / cost / time | efficiency |

Premature diagnosis is judged against per-case `key_evidence` in `labels.json`, which is independent of
either architecture, so the verifier-based system gets no built-in advantage from it.

### Baseline

**ReAct-style baseline:** a single LLM agent iteratively selects observability tools based on tool
outputs until it produces a root-cause diagnosis, without explicit planner, hypothesis tracking, or
verifier nodes ([agent/baseline_react.py](agent/baseline_react.py)). It uses the same model, the
same MCP tools, the same domain prompt (service catalog, investigation principles, taxonomy), the
same 10-call budget and the same output schema; only the graph differs.

## Running it

```bash
pip install -r requirements.txt
cp .env.example .env            # add OPENAI_API_KEY

python -m evaluation.generate_scenarios          # (re)build the benchmark
python main.py --case case_010                   # watch one investigation; asks for approval
python main.py --case case_010 --agent react     # same incident, ReAct baseline

python -m evaluation.run_eval --split dev --runs 1              # tuning loop
python -m evaluation.run_eval --split eval --runs 3             # held-out results
python -m pytest                                                 # unit tests (no LLM calls)
```

## Project layout

```
agent/
  graph.py           LangGraph workflow (Planner + Hypothesis + Verifier)
  baseline_react.py  ReAct baseline
  state.py           IncidentState / Evidence / Hypothesis / ToolCall
  schemas.py         Pydantic structured outputs
  verifier.py        deterministic verifier rules
  prompts.py         prompts (shared domain blocks for both architectures)
  taxonomy.py        root-cause labels and definitions
  mcp_client.py      launches the MCP server, loads tools + alert resource
  runner.py          runs one incident; tracks tokens, cost, time
mcp_server/
  observability_server.py   FastMCP server (tools + alert resource)
  backend.py                simulated metrics / logs / traces / config backend
evaluation/
  generate_scenarios.py     fault injection + red herrings → scenarios + labels
  labels.json               ground truth, dev/eval split, key evidence
  run_eval.py / metrics.py / report.py
  results/                  raw runs (jsonl) and summaries
scenarios/                  20 observable-only incident scenarios
tests/                      verifier, backend, metrics, isolation tests
main.py                     CLI demo
```

## Limitations and future work

- Telemetry is simulated from scenario files; the backend interface is designed so that
  Prometheus / Loki / Jaeger could replace it without touching the agent.
- `apply_fix` only records the action; verifying recovery after a real fix is future work.
- 12 held-out cases is a small benchmark; one case is ~8 percentage points.
- Future: real services with OpenTelemetry, incident memory (vector store of past postmortems),
  post-fix verification loop.
