# Benchmark results (suite v2, heldout split)

Model `gpt-4.1-mini` | 2 run(s) per case | step budget 10 tool calls | started 20260926-043327

| Architecture | Accuracy | Cases correct in every run | False Diagnosis | Premature Diagnosis | Unknown | Avg Tool Calls | Avg Tokens | Cost / Case | Avg Time |
|---|---|---|---|---|---|---|---|---|---|
| A. ReAct baseline | 41/54 (76%) | 18/27 | 19% | 9% | 4% | 7.4 | 17,185 | $0.0074 | 28.5s |
| B. Planner + Hypothesis (no verifier) | 38/54 (70%) | 17/27 | 24% | 4% | 0% | 8.1 | 47,606 | $0.0220 | 85.9s |
| D. C + LLM skeptic (phase-1 system) | 30/54 (56%) | 11/27 | 26% | 9% | 19% | 6.9 | 40,004 | $0.0187 | 54.2s |
| E. B + checklist & margin rules | 27/54 (50%) | 13/27 | 44% | 31% | 6% | 4.4 | 20,983 | $0.0100 | 29.9s |
| F. E + LLM skeptic | 28/54 (52%) | 10/27 | 37% | 19% | 13% | 5.9 | 34,225 | $0.0160 | 49.2s |

## Accuracy by difficulty tier

| Tier | A. ReAct baseline | B. Planner + Hypothesis (no verifier) | D. C + LLM skeptic (phase-1 system) | E. B + checklist & margin rules | F. E + LLM skeptic |
|---|---|---|---|---|---|
| easy | 15/18 | 14/18 | 12/18 | 12/18 | 11/18 |
| medium | 13/18 | 12/18 | 11/18 | 8/18 | 9/18 |
| hard | 13/18 | 12/18 | 7/18 | 7/18 | 8/18 |

## Accuracy by root cause

| Root cause | A. ReAct baseline | B. Planner + Hypothesis (no verifier) | D. C + LLM skeptic (phase-1 system) | E. B + checklist & margin rules | F. E + LLM skeptic |
|---|---|---|---|---|---|
| bad_config_deploy | 1/6 | 2/6 | 3/6 | 4/6 | 3/6 |
| cpu_hot_loop | 5/6 | 6/6 | 5/6 | 6/6 | 6/6 |
| db_pool_exhaustion | 6/6 | 4/6 | 5/6 | 4/6 | 4/6 |
| dependency_unavailable | 6/6 | 6/6 | 5/6 | 6/6 | 5/6 |
| expired_credential | 6/6 | 6/6 | 3/6 | 0/6 | 1/6 |
| memory_leak | 6/6 | 6/6 | 5/6 | 3/6 | 4/6 |
| missing_env_var | 4/6 | 2/6 | 0/6 | 0/6 | 1/6 |
| slow_db_query | 6/6 | 6/6 | 4/6 | 4/6 | 3/6 |
| unknown | 1/6 | 0/6 | 0/6 | 0/6 | 1/6 |

## Misdiagnoses (truth -> predicted)

- **A. ReAct baseline:** unknown -> dependency_unavailable x4, bad_config_deploy -> dependency_unavailable x4, missing_env_var -> bad_config_deploy x2, bad_config_deploy -> unknown x1, cpu_hot_loop -> bad_config_deploy x1, unknown -> bad_config_deploy x1
- **B. Planner + Hypothesis (no verifier):** missing_env_var -> bad_config_deploy x4, unknown -> dependency_unavailable x4, bad_config_deploy -> dependency_unavailable x4, unknown -> bad_config_deploy x2, db_pool_exhaustion -> dependency_unavailable x1, db_pool_exhaustion -> cpu_hot_loop x1
- **D. C + LLM skeptic (phase-1 system):** unknown -> dependency_unavailable x5, missing_env_var -> dependency_unavailable x3, missing_env_var -> bad_config_deploy x2, slow_db_query -> unknown x2, bad_config_deploy -> unknown x2, expired_credential -> unknown x2, dependency_unavailable -> unknown x1, bad_config_deploy -> dependency_unavailable x1, expired_credential -> dependency_unavailable x1, missing_env_var -> unknown x1, cpu_hot_loop -> unknown x1, unknown -> db_pool_exhaustion x1, db_pool_exhaustion -> dependency_unavailable x1, memory_leak -> unknown x1
- **E. B + checklist & margin rules:** expired_credential -> dependency_unavailable x6, missing_env_var -> unknown x3, unknown -> dependency_unavailable x3, memory_leak -> cpu_hot_loop x3, slow_db_query -> db_pool_exhaustion x2, unknown -> bad_config_deploy x2, missing_env_var -> dependency_unavailable x2, bad_config_deploy -> dependency_unavailable x2, db_pool_exhaustion -> dependency_unavailable x2, missing_env_var -> bad_config_deploy x1, unknown -> slow_db_query x1
- **F. E + LLM skeptic:** unknown -> dependency_unavailable x5, expired_credential -> dependency_unavailable x3, missing_env_var -> bad_config_deploy x2, missing_env_var -> unknown x2, memory_leak -> cpu_hot_loop x2, bad_config_deploy -> unknown x2, db_pool_exhaustion -> dependency_unavailable x2, expired_credential -> unknown x2, slow_db_query -> db_pool_exhaustion x1, dependency_unavailable -> bad_config_deploy x1, missing_env_var -> dependency_unavailable x1, slow_db_query -> dependency_unavailable x1, bad_config_deploy -> dependency_unavailable x1, slow_db_query -> bad_config_deploy x1

Definitions: *False Diagnosis* = wrong label with confidence >= 0.8. *Premature Diagnosis* = a (non-unknown) diagnosis given before the case's key discriminating evidence was queried, regardless of correctness. *Unknown* = the run answered 'unknown' (correct only when the true cause is outside the taxonomy). *Avg Time* is wall-clock under concurrent runs and includes API rate-limit waits.
