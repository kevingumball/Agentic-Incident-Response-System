# Benchmark results (dev split)

Model `gpt-4.1-mini` | 1 run(s) per case | step budget 10 tool calls | started 20260925-102933

| Architecture | Accuracy | Cases correct in every run | False Diagnosis | Premature Diagnosis | Unknown | Avg Tool Calls | Avg Tokens | Cost / Case | Avg Time |
|---|---|---|---|---|---|---|---|---|---|
| ReAct baseline | 8/8 (100%) | 8/8 | 0% | 12% | 0% | 7.1 | 15,843 | $0.0068 | 30.6s |
| Planner + Hypothesis + Verifier | 5/8 (62%) | 5/8 | 38% | 50% | 0% | 4.2 | 16,965 | $0.0084 | 117.2s |

## Accuracy by root cause

| Root cause | ReAct baseline | Planner + Hypothesis + Verifier |
|---|---|---|
| bad_config_deploy | 1/1 | 0/1 |
| cpu_hot_loop | 1/1 | 0/1 |
| db_pool_exhaustion | 1/1 | 1/1 |
| dependency_unavailable | 1/1 | 1/1 |
| expired_credential | 1/1 | 0/1 |
| memory_leak | 1/1 | 1/1 |
| missing_env_var | 1/1 | 1/1 |
| slow_db_query | 1/1 | 1/1 |

## Misdiagnoses (truth -> predicted)

- **ReAct baseline:** none
- **Planner + Hypothesis + Verifier:** bad_config_deploy -> missing_env_var x1, expired_credential -> dependency_unavailable x1, cpu_hot_loop -> bad_config_deploy x1

Definitions: *False Diagnosis* = wrong label with confidence >= 0.8. *Premature Diagnosis* = a (non-unknown) diagnosis given before the case's key discriminating evidence was queried, regardless of correctness. *Unknown* = no diagnosis within the step budget.
