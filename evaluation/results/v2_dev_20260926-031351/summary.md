# Benchmark results (suite v2, dev split)

Model `gpt-4.1-mini` | 2 run(s) per case | step budget 10 tool calls | started 20260926-031351

| Architecture | Accuracy | Cases correct in every run | False Diagnosis | Premature Diagnosis | Unknown | Avg Tool Calls | Avg Tokens | Cost / Case | Avg Time |
|---|---|---|---|---|---|---|---|---|---|
| A. ReAct baseline | 26/36 (72%) | 11/18 | 25% | 6% | 3% | 7.7 | 17,935 | $0.0077 | 19.7s |
| B. Planner + Hypothesis (no verifier) | 24/36 (67%) | 11/18 | 33% | 0% | 0% | 8.3 | 48,448 | $0.0223 | 88.7s |
| C. B + hard rules | 14/36 (39%) | 5/18 | 47% | 56% | 14% | 4.3 | 20,898 | $0.0099 | 56.7s |
| D. C + LLM skeptic (phase-1 system) | 17/36 (47%) | 7/18 | 33% | 19% | 17% | 6.9 | 39,629 | $0.0184 | 66.8s |

Runs that errored (counted as wrong): {'react': 1, 'verifier': 1}

## Accuracy by difficulty tier

| Tier | A. ReAct baseline | B. Planner + Hypothesis (no verifier) | C. B + hard rules | D. C + LLM skeptic (phase-1 system) |
|---|---|---|---|---|
| easy | - | - | - | - |
| medium | 13/18 | 13/18 | 8/18 | 12/18 |
| hard | 13/18 | 11/18 | 6/18 | 5/18 |

## Accuracy by root cause

| Root cause | A. ReAct baseline | B. Planner + Hypothesis (no verifier) | C. B + hard rules | D. C + LLM skeptic (phase-1 system) |
|---|---|---|---|---|
| bad_config_deploy | 3/4 | 3/4 | 1/4 | 3/4 |
| cpu_hot_loop | 4/4 | 4/4 | 4/4 | 4/4 |
| db_pool_exhaustion | 4/4 | 4/4 | 0/4 | 2/4 |
| dependency_unavailable | 4/4 | 4/4 | 4/4 | 3/4 |
| expired_credential | 4/4 | 1/4 | 1/4 | 2/4 |
| memory_leak | 3/4 | 4/4 | 1/4 | 1/4 |
| missing_env_var | 0/4 | 0/4 | 0/4 | 0/4 |
| slow_db_query | 3/4 | 4/4 | 3/4 | 2/4 |
| unknown | 1/4 | 0/4 | 0/4 | 0/4 |

## Misdiagnoses (truth -> predicted)

- **A. ReAct baseline:** missing_env_var -> bad_config_deploy x4, unknown -> dependency_unavailable x2, unknown -> bad_config_deploy x1, slow_db_query -> db_pool_exhaustion x1, memory_leak -> cpu_hot_loop x1, bad_config_deploy -> ERROR x1
- **B. Planner + Hypothesis (no verifier):** missing_env_var -> bad_config_deploy x4, expired_credential -> dependency_unavailable x3, unknown -> dependency_unavailable x3, unknown -> bad_config_deploy x1, bad_config_deploy -> dependency_unavailable x1
- **C. B + hard rules:** unknown -> dependency_unavailable x4, bad_config_deploy -> dependency_unavailable x3, expired_credential -> dependency_unavailable x2, missing_env_var -> bad_config_deploy x2, db_pool_exhaustion -> unknown x2, expired_credential -> unknown x1, missing_env_var -> unknown x1, missing_env_var -> dependency_unavailable x1, db_pool_exhaustion -> dependency_unavailable x1, db_pool_exhaustion -> cpu_hot_loop x1, memory_leak -> unknown x1, memory_leak -> dependency_unavailable x1, memory_leak -> bad_config_deploy x1, slow_db_query -> dependency_unavailable x1
- **D. C + LLM skeptic (phase-1 system):** unknown -> dependency_unavailable x3, expired_credential -> dependency_unavailable x2, missing_env_var -> bad_config_deploy x2, memory_leak -> unknown x2, missing_env_var -> dependency_unavailable x1, missing_env_var -> unknown x1, db_pool_exhaustion -> cpu_hot_loop x1, db_pool_exhaustion -> dependency_unavailable x1, unknown -> slow_db_query x1, memory_leak -> dependency_unavailable x1, slow_db_query -> unknown x1, bad_config_deploy -> unknown x1, slow_db_query -> ERROR x1, dependency_unavailable -> unknown x1

Definitions: *False Diagnosis* = wrong label with confidence >= 0.8. *Premature Diagnosis* = a (non-unknown) diagnosis given before the case's key discriminating evidence was queried, regardless of correctness. *Unknown* = the run answered 'unknown' (correct only when the true cause is outside the taxonomy). *Avg Time* is wall-clock under concurrent runs and includes API rate-limit waits.
