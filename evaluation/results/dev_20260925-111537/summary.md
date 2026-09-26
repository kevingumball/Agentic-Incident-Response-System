# Benchmark results (dev split)

Model `gpt-4.1-mini` | 1 run(s) per case | step budget 10 tool calls | started 20260925-111537

| Architecture | Accuracy | Cases correct in every run | False Diagnosis | Premature Diagnosis | Unknown | Avg Tool Calls | Avg Tokens | Cost / Case | Avg Time |
|---|---|---|---|---|---|---|---|---|---|
| Planner + Hypothesis + Verifier | 8/8 (100%) | 8/8 | 0% | 0% | 0% | 5.6 | 32,830 | $0.0153 | 293.7s |

## Accuracy by root cause

| Root cause | Planner + Hypothesis + Verifier |
|---|---|
| bad_config_deploy | 1/1 |
| cpu_hot_loop | 1/1 |
| db_pool_exhaustion | 1/1 |
| dependency_unavailable | 1/1 |
| expired_credential | 1/1 |
| memory_leak | 1/1 |
| missing_env_var | 1/1 |
| slow_db_query | 1/1 |

## Misdiagnoses (truth -> predicted)

- **Planner + Hypothesis + Verifier:** none

Definitions: *False Diagnosis* = wrong label with confidence >= 0.8. *Premature Diagnosis* = a (non-unknown) diagnosis given before the case's key discriminating evidence was queried, regardless of correctness. *Unknown* = no diagnosis within the step budget.
