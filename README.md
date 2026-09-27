# Agentic Incident Response

An LLM agent that investigates production incidents the way an on-call SRE does: it chooses
which observability data to pull, records structured evidence, maintains competing root-cause
hypotheses, and **refuses to conclude until a verifier accepts the evidence**. Fixes are only
applied after human approval.

Built with **LangGraph** (explicit state machine), **MCP** (tools served by a separate
observability server), and evaluated on a **fault-injection benchmark with held-out cases and
red-herring signals** against a ReAct baseline.

## Key findings

1. **More agentic structure did not beat a plain ReAct loop** with `gpt-4.1-mini`, on either benchmark.
2. **Held-out evaluation caught dev-set overfitting**: the phase-1 verifier went 8/8 on dev → 69% on held-out.
3. **An ablation isolated the harmful layer**: hard rules gated on LLM-reported confidence became an
   *early-exit trigger*. Adding them dropped dev accuracy 67% → 39% and raised premature diagnoses 0% → 56%.
4. **The fix did not generalize.** Replacing that gate with a deterministic evidence checklist + margin
   rule recovered +25 points on dev (39% → 64%), but only reached 50-52% on the v2 held-out set, no
   better than the phase-1 system (56%). The same dev-set overfitting as phase 1, caught the same way.
5. **Final v2 held-out ranking: ReAct 76% > no-verifier 70% > every verifier variant 50-56%.** The gap is
   largest on hard cases (ReAct 13/18 vs 7-8/18), exactly where verification was supposed to help.
6. A checklist of "did you check the evidence for your answer" is satisfied by a wrong answer too; gates
   built on LLM judgments (confidence, hypothesis labels) did not help with `gpt-4.1-mini`.

The full process, including every problem hit along the way, is in [DEVLOG.md](DEVLOG.md).

## Phase 1 results (v1 held-out set, 12 cases × 3 runs, `gpt-4.1-mini`)

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

## Phase 2: ablation on a harder benchmark

v1 saturated (ReAct 97%), so it could not tell architectures apart. **Benchmark v2**
([generator](evaluation/generate_scenarios_v2.py)) was designed and frozen before any architecture ran on it:
evidence no longer names the cause, harmless deploys land in the same minute as the fault, the first
signal points the wrong way (pool-timeout errors outnumber slow-query warnings), tracing or metrics are
missing on the faulty service, and some incidents fall outside the taxonomy (correct answer: `unknown`).
45 cases in easy / medium / hard tiers: 18 dev, 27 held-out. ReAct drops from 97% to 72% on v2 dev.

Every node now writes a trace, and [evaluation/attribution.py](evaluation/attribution.py) assigns each
wrong run to the first node that went wrong.

**Ablation on v2 dev (18 cases × 2 runs)**

| Architecture | Accuracy | False Diagnosis | Premature Diagnosis | Tool calls |
|---|---|---|---|---|
| A. ReAct | **26/36 (72%)** | 25% | 6% | 7.7 |
| B. Planner + Hypothesis, no verifier | 24/36 (67%) | 33% | **0%** | 8.3 |
| C. B + phase-1 hard rules | 14/36 (39%) | 47% | 56% | 4.3 |
| D. C + LLM skeptic (phase-1 system) | 17/36 (47%) | 33% | 19% | 6.9 |
| E. B + evidence checklist & margin rule | 23/36 (64%) | 28% | 25% | 5.3 |
| F. E + LLM skeptic | 23/36 (64%) | 31% | 22% | 6.3 |

- **B → C (−28 points):** the hard rules were meant to prevent premature conclusions, but in practice
  they fired as soon as the LLM's self-reported confidence reached 0.8. Runs stopped after 4.3 calls
  instead of 8.3; 15 of C's 22 errors concluded without the key evidence.
- **C → E (+25 points):** the fix replaces "second place < 0.5" with a margin rule, and adds a per-label
  evidence checklist checked in code against the calls actually made (e.g. no `bad_config_deploy`
  without reading that service's config). Caveat: the checklist and the evaluation's key-evidence
  definitions share the same domain logic, so E/F's premature rate is partly lower by construction;
  accuracy and false diagnosis are the real test.
- **A → B (−5 points, 2.7× tokens):** a separate hypothesis-tracking LLM call misreads evidence that
  ReAct reads correctly in one context.
- Every architecture scores 0/4 on the dev `missing_env_var` cases. This is recorded as a likely
  benchmark ambiguity; it was left unchanged because the benchmark was frozen and the error affects all
  architectures equally.

**v2 held-out (27 cases × 2 runs, run once after the design was frozen)**

| Architecture | Dev accuracy | **Held-out accuracy** | False Diagnosis | Premature | Cases correct in every run |
|---|---|---|---|---|---|
| A. ReAct | 72% | **41/54 (76%)** | 19% | 9% | 18/27 |
| B. Planner + Hypothesis, no verifier | 67% | **38/54 (70%)** | 24% | 4% | 17/27 |
| D. phase-1 verifier | 47% | **30/54 (56%)** | 26% | 9% | 11/27 |
| E. checklist & margin rule | 64% | **27/54 (50%)** | 44% | 31% | 13/27 |
| F. E + LLM skeptic | 64% | **28/54 (52%)** | 37% | 19% | 10/27 |

By tier, ReAct scores 15 / 13 / 13 of 18 on easy / medium / hard; the verifier variants score 7-8 of 18 on
hard. Full output: [summary](evaluation/results/v2_heldout_20260926-043327/summary.md),
[attribution](evaluation/results/v2_heldout_20260926-043327/attribution.md).

- E and F, designed from the dev failures, fell from 64% to 50-52%: the dev set (18 cases) was overfit again.
- E's 15 "concluded without key evidence" errors show why the checklist failed: it verifies that the
  agent looked at the evidence for **its own** answer (e.g. a dependency's logs for `dependency_unavailable`),
  which a wrong answer satisfies just as well.
- The run was interrupted once by exhausted API credits and later hit 14 rate-limit errors; all were
  re-run unchanged with `--resume` (see DEVLOG 10.5).

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

python -m evaluation.run_eval --split dev --runs 1              # v1 tuning loop
python -m evaluation.run_eval --split eval --runs 3             # v1 held-out results

python -m evaluation.generate_scenarios_v2                       # (re)build benchmark v2
python -m evaluation.run_eval --suite v2 --split dev --runs 2     --arch react,plan_hyp,plan_hyp_rules,verifier,plan_hyp_checklist,verifier_v2   # ablation
python -m evaluation.run_eval --resume evaluation/results/<run_dir>              # finish an interrupted run
python -m evaluation.attribution evaluation/results/<run_dir>                    # first-wrong-node analysis
python -m pytest                                                 # unit tests (no LLM calls)
```

## Project layout

```
agent/
  graph.py           LangGraph workflow (Planner + Hypothesis + configurable verification; per-node trace)
  baseline_react.py  ReAct baseline
  state.py           IncidentState / Evidence / Hypothesis / ToolCall
  schemas.py         Pydantic structured outputs
  verifier.py        deterministic rules: phase-1 rules, evidence checklist, margin rule, objection filter
  prompts.py         prompts (shared domain blocks for both architectures)
  taxonomy.py        root-cause labels and definitions
  mcp_client.py      launches the MCP server, loads tools + alert resource
  runner.py          runs one incident with any architecture (A-F); tracks tokens, cost, time, trace
mcp_server/
  observability_server.py   FastMCP server (tools + alert resource)
  backend.py                simulated metrics / logs / traces / config backend
evaluation/
  generate_scenarios.py     benchmark v1: fault injection + red herrings → scenarios + labels
  generate_scenarios_v2.py  benchmark v2: subtle evidence, coincident deploys, missing data, unknown cases
  labels.json / labels_v2.json   ground truth, splits, tiers, key evidence
  run_eval.py / metrics.py / report.py   benchmark runner (resumable) and summaries
  attribution.py            first-wrong-node failure attribution
  results/                  raw runs (jsonl) and summaries
scenarios/  scenarios_v2/  observable-only incident scenarios (20 + 45)
tests/                      verifier, backend, metrics, attribution, runner, isolation tests
main.py                     CLI demo
```

## Limitations and future work

- Telemetry is simulated from scenario files; the backend interface is designed so that
  Prometheus / Loki / Jaeger could replace it without touching the agent.
- `apply_fix` only records the action; verifying recovery after a real fix is future work.
- Benchmarks are small (v1 held-out 12 cases, v2 held-out 27 cases); one v2 case is ~4 percentage points.
- Only one model (`gpt-4.1-mini`) was tested; a stronger model may change which architecture wins.
- v2 `missing_env_var` cases may be ambiguous (nothing states which variables the service requires).
- Future: real services with OpenTelemetry, incident memory (vector store of past postmortems),
  post-fix verification loop, a stronger model run, and replacing LLM-reported confidence with
  sampling-based agreement (self-consistency), evaluated on a fresh held-out set.
