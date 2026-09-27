# Benchmark results (suite v2, dev split)

Model `gpt-4.1-mini` | 1 run(s) per case | step budget 10 tool calls | started 20260926-024710

| Architecture | Accuracy | Cases correct in every run | False Diagnosis | Premature Diagnosis | Unknown | Avg Tool Calls | Avg Tokens | Cost / Case | Avg Time |
|---|---|---|---|---|---|---|---|---|---|
| A. ReAct baseline | 13/18 (72%) | 13/18 | 28% | 0% | 0% | 7.7 | 17,950 | $0.0077 | 154.7s |

## Accuracy by difficulty tier

| Tier | A. ReAct baseline |
|---|---|
| easy | - |
| medium | 6/9 |
| hard | 7/9 |

## Accuracy by root cause

| Root cause | A. ReAct baseline |
|---|---|
| bad_config_deploy | 2/2 |
| cpu_hot_loop | 2/2 |
| db_pool_exhaustion | 2/2 |
| dependency_unavailable | 2/2 |
| expired_credential | 2/2 |
| memory_leak | 1/2 |
| missing_env_var | 0/2 |
| slow_db_query | 2/2 |
| unknown | 0/2 |

## Misdiagnoses (truth -> predicted)

- **A. ReAct baseline:** missing_env_var -> bad_config_deploy x2, unknown -> dependency_unavailable x2, memory_leak -> cpu_hot_loop x1

Definitions: *False Diagnosis* = wrong label with confidence >= 0.8. *Premature Diagnosis* = a (non-unknown) diagnosis given before the case's key discriminating evidence was queried, regardless of correctness. *Unknown* = the run answered 'unknown' (correct only when the true cause is outside the taxonomy). *Avg Time* is wall-clock under concurrent runs and includes API rate-limit waits.
