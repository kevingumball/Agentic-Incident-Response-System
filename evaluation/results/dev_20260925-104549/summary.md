# Benchmark results (dev split)

Model `gpt-4.1-mini` | 1 run(s) per case | step budget 10 tool calls | started 20260925-104549

| Architecture | Accuracy | Cases correct in every run | False Diagnosis | Premature Diagnosis | Unknown | Avg Tool Calls | Avg Tokens | Cost / Case | Avg Time |
|---|---|---|---|---|---|---|---|---|---|
| ReAct baseline | 8/8 (100%) | 8/8 | 0% | 12% | 0% | 6.5 | 14,911 | $0.0064 | 7.6s |
| Planner + Hypothesis + Verifier | 2/8 (25%) | 2/8 | 12% | 25% | 62% | 6.2 | 31,634 | $0.0154 | 352.9s |

## Accuracy by root cause

| Root cause | ReAct baseline | Planner + Hypothesis + Verifier |
|---|---|---|
| bad_config_deploy | 1/1 | 0/1 |
| cpu_hot_loop | 1/1 | 0/1 |
| db_pool_exhaustion | 1/1 | 1/1 |
| dependency_unavailable | 1/1 | 0/1 |
| expired_credential | 1/1 | 0/1 |
| memory_leak | 1/1 | 0/1 |
| missing_env_var | 1/1 | 0/1 |
| slow_db_query | 1/1 | 1/1 |

## Misdiagnoses (truth -> predicted)

- **ReAct baseline:** none
- **Planner + Hypothesis + Verifier:** bad_config_deploy -> dependency_unavailable x1, expired_credential -> unknown x1, memory_leak -> unknown x1, missing_env_var -> unknown x1, cpu_hot_loop -> unknown x1, dependency_unavailable -> unknown x1

Definitions: *False Diagnosis* = wrong label with confidence >= 0.8. *Premature Diagnosis* = a (non-unknown) diagnosis given before the case's key discriminating evidence was queried, regardless of correctness. *Unknown* = no diagnosis within the step budget.
