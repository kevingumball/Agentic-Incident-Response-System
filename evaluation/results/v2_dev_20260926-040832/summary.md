# Benchmark results (suite v2, dev split)

Model `gpt-4.1-mini` | 2 run(s) per case | step budget 10 tool calls | started 20260926-040832

| Architecture | Accuracy | Cases correct in every run | False Diagnosis | Premature Diagnosis | Unknown | Avg Tool Calls | Avg Tokens | Cost / Case | Avg Time |
|---|---|---|---|---|---|---|---|---|---|
| E. B + checklist & margin rules | 23/36 (64%) | 9/18 | 28% | 25% | 14% | 5.3 | 26,130 | $0.0124 | 67.1s |
| F. E + LLM skeptic | 23/36 (64%) | 9/18 | 31% | 22% | 8% | 6.3 | 36,273 | $0.0169 | 68.2s |

## Accuracy by difficulty tier

| Tier | E. B + checklist & margin rules | F. E + LLM skeptic |
|---|---|---|
| easy | - | - |
| medium | 15/18 | 12/18 |
| hard | 8/18 | 11/18 |

## Accuracy by root cause

| Root cause | E. B + checklist & margin rules | F. E + LLM skeptic |
|---|---|---|
| bad_config_deploy | 2/4 | 4/4 |
| cpu_hot_loop | 4/4 | 4/4 |
| db_pool_exhaustion | 3/4 | 3/4 |
| dependency_unavailable | 4/4 | 4/4 |
| expired_credential | 2/4 | 3/4 |
| memory_leak | 3/4 | 1/4 |
| missing_env_var | 0/4 | 0/4 |
| slow_db_query | 3/4 | 3/4 |
| unknown | 2/4 | 1/4 |

## Misdiagnoses (truth -> predicted)

- **E. B + checklist & margin rules:** missing_env_var -> bad_config_deploy x3, expired_credential -> dependency_unavailable x2, unknown -> dependency_unavailable x2, missing_env_var -> dependency_unavailable x1, db_pool_exhaustion -> unknown x1, memory_leak -> unknown x1, slow_db_query -> db_pool_exhaustion x1, bad_config_deploy -> dependency_unavailable x1, bad_config_deploy -> unknown x1
- **F. E + LLM skeptic:** missing_env_var -> dependency_unavailable x3, unknown -> dependency_unavailable x3, memory_leak -> unknown x2, missing_env_var -> bad_config_deploy x1, expired_credential -> dependency_unavailable x1, db_pool_exhaustion -> bad_config_deploy x1, memory_leak -> cpu_hot_loop x1, slow_db_query -> db_pool_exhaustion x1

Definitions: *False Diagnosis* = wrong label with confidence >= 0.8. *Premature Diagnosis* = a (non-unknown) diagnosis given before the case's key discriminating evidence was queried, regardless of correctness. *Unknown* = the run answered 'unknown' (correct only when the true cause is outside the taxonomy). *Avg Time* is wall-clock under concurrent runs and includes API rate-limit waits.
