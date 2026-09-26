# Benchmark results (eval split)

Model `gpt-4.1-mini` | 3 run(s) per case | step budget 10 tool calls | started 20260925-113329

| Architecture | Accuracy | Cases correct in every run | False Diagnosis | Premature Diagnosis | Unknown | Avg Tool Calls | Avg Tokens | Cost / Case | Avg Time |
|---|---|---|---|---|---|---|---|---|---|
| ReAct baseline | 35/36 (97%) | 11/12 | 3% | 8% | 0% | 6.8 | 15,678 | $0.0068 | 28.3s |
| Planner + Hypothesis + Verifier | 25/36 (69%) | 7/12 | 14% | 25% | 17% | 6.5 | 38,931 | $0.0181 | 283.4s |

## Accuracy by root cause

| Root cause | ReAct baseline | Planner + Hypothesis + Verifier |
|---|---|---|
| bad_config_deploy | 5/6 | 3/6 |
| cpu_hot_loop | 3/3 | 3/3 |
| db_pool_exhaustion | 6/6 | 6/6 |
| dependency_unavailable | 6/6 | 5/6 |
| expired_credential | 3/3 | 0/3 |
| memory_leak | 3/3 | 0/3 |
| missing_env_var | 3/3 | 3/3 |
| slow_db_query | 6/6 | 5/6 |

## Misdiagnoses (truth -> predicted)

- **ReAct baseline:** bad_config_deploy -> memory_leak x1
- **Planner + Hypothesis + Verifier:** memory_leak -> unknown x3, bad_config_deploy -> dependency_unavailable x2, expired_credential -> dependency_unavailable x2, bad_config_deploy -> unknown x1, slow_db_query -> db_pool_exhaustion x1, expired_credential -> unknown x1, dependency_unavailable -> unknown x1

Definitions: *False Diagnosis* = wrong label with confidence >= 0.8. *Premature Diagnosis* = a (non-unknown) diagnosis given before the case's key discriminating evidence was queried, regardless of correctness. *Unknown* = no diagnosis within the step budget.
