# Failure attribution

| Category | A. ReAct baseline | B. Planner + Hypothesis (no verifier) | D. C + LLM skeptic (phase-1 system) | E. B + checklist & margin rules | F. E + LLM skeptic |
|---|---|---|---|---|---|
| blocked_correct_by_rules |  |  | 5 | 2 | 3 |
| blocked_correct_by_skeptic |  |  | 2 |  |  |
| budget_exhausted_wrong_top |  |  | 3 | 1 | 3 |
| hypothesis_drifted_away |  | 8 | 4 | 4 | 4 |
| hypothesis_never_ranked_truth |  | 6 |  | 5 | 7 |
| planner_missed_key_evidence | 5 | 2 | 5 | 15 | 9 |
| react_misread | 8 |  |  |  |  |
| verifier_accepted_wrong |  |  | 5 |  |  |
| **total wrong** | 13 | 16 | 24 | 27 | 26 |

## A. ReAct baseline

- `case_020` (medium) truth **bad_config_deploy** -> dependency_unavailable | planner_missed_key_evidence: never queried key evidence; answered dependency_unavailable
- `case_020` (medium) truth **bad_config_deploy** -> dependency_unavailable | planner_missed_key_evidence: never queried key evidence; answered dependency_unavailable
- `case_022` (hard) truth **bad_config_deploy** -> dependency_unavailable | planner_missed_key_evidence: never queried key evidence; answered dependency_unavailable
- `case_022` (hard) truth **bad_config_deploy** -> dependency_unavailable | planner_missed_key_evidence: never queried key evidence; answered dependency_unavailable
- `case_025` (easy) truth **bad_config_deploy** -> unknown | planner_missed_key_evidence: never queried key evidence; answered unknown
- `case_001` (medium) truth **missing_env_var** -> bad_config_deploy | react_misread: key evidence queried at step 5, still answered bad_config_deploy
- `case_003` (hard) truth **unknown** -> dependency_unavailable | react_misread: key evidence queried at step 4, still answered dependency_unavailable
- `case_011` (medium) truth **unknown** -> dependency_unavailable | react_misread: key evidence queried at step 4, still answered dependency_unavailable
- `case_011` (medium) truth **unknown** -> dependency_unavailable | react_misread: key evidence queried at step 4, still answered dependency_unavailable
- `case_037` (hard) truth **missing_env_var** -> bad_config_deploy | react_misread: key evidence queried at step 9, still answered bad_config_deploy
- `case_038` (hard) truth **cpu_hot_loop** -> bad_config_deploy | react_misread: key evidence queried at step 1, still answered bad_config_deploy
- `case_042` (easy) truth **unknown** -> dependency_unavailable | react_misread: key evidence queried at step 3, still answered dependency_unavailable
- `case_042` (easy) truth **unknown** -> bad_config_deploy | react_misread: key evidence queried at step 3, still answered bad_config_deploy

## B. Planner + Hypothesis (no verifier)

- `case_001` (medium) truth **missing_env_var** -> bad_config_deploy | hypothesis_drifted_away: truth was top at steps [1], final top bad_config_deploy (key evidence at step 5)
- `case_001` (medium) truth **missing_env_var** -> bad_config_deploy | hypothesis_drifted_away: truth was top at steps [1, 4], final top bad_config_deploy (key evidence at step 5)
- `case_004` (easy) truth **missing_env_var** -> bad_config_deploy | hypothesis_drifted_away: truth was top at steps [4], final top bad_config_deploy (key evidence at step 4)
- `case_022` (hard) truth **bad_config_deploy** -> dependency_unavailable | hypothesis_drifted_away: truth was top at steps [5, 6, 7], final top dependency_unavailable (key evidence at step 5)
- `case_042` (easy) truth **unknown** -> bad_config_deploy | hypothesis_drifted_away: truth was top at steps [1, 2, 3, 4, 5, 7], final top bad_config_deploy (key evidence at step 5)
- `case_042` (easy) truth **unknown** -> bad_config_deploy | hypothesis_drifted_away: truth was top at steps [6], final top bad_config_deploy (key evidence at step 4)
- `case_044` (hard) truth **db_pool_exhaustion** -> dependency_unavailable | hypothesis_drifted_away: truth was top at steps [6, 7], final top dependency_unavailable (key evidence at step 7)
- `case_044` (hard) truth **db_pool_exhaustion** -> cpu_hot_loop | hypothesis_drifted_away: truth was top at steps [6, 7, 8], final top cpu_hot_loop (key evidence at step 7)
- `case_003` (hard) truth **unknown** -> dependency_unavailable | hypothesis_never_ranked_truth: key evidence at step 5; truth never top; final dependency_unavailable
- `case_003` (hard) truth **unknown** -> dependency_unavailable | hypothesis_never_ranked_truth: key evidence at step 5; truth never top; final dependency_unavailable
- `case_011` (medium) truth **unknown** -> dependency_unavailable | hypothesis_never_ranked_truth: key evidence at step 4; truth never top; final dependency_unavailable
- `case_011` (medium) truth **unknown** -> dependency_unavailable | hypothesis_never_ranked_truth: key evidence at step 4; truth never top; final dependency_unavailable
- `case_020` (medium) truth **bad_config_deploy** -> dependency_unavailable | hypothesis_never_ranked_truth: key evidence at step 4; truth never top; final dependency_unavailable
- `case_037` (hard) truth **missing_env_var** -> bad_config_deploy | hypothesis_never_ranked_truth: key evidence at step 4; truth never top; final bad_config_deploy
- `case_020` (medium) truth **bad_config_deploy** -> dependency_unavailable | planner_missed_key_evidence: concluded dependency_unavailable without key evidence
- `case_025` (easy) truth **bad_config_deploy** -> dependency_unavailable | planner_missed_key_evidence: concluded dependency_unavailable without key evidence

## D. C + LLM skeptic (phase-1 system)

- `case_002` (hard) truth **slow_db_query** -> unknown | blocked_correct_by_rules: truth on top at the end; rules: Competing hypothesis db_pool_exhaustion is still at 0.60 (>= 0.5); find evidence that discriminates it from slow_db_query.
- `case_022` (hard) truth **bad_config_deploy** -> unknown | blocked_correct_by_rules: truth on top at the end; rules: Supporting evidence for bad_config_deploy comes from 1 source type(s) (config); need at least 2 different types (metrics / logs / traces / config).
- `case_036` (medium) truth **expired_credential** -> unknown | blocked_correct_by_rules: truth on top at the end; rules: Competing hypothesis dependency_unavailable is still at 0.85 (>= 0.5); find evidence that discriminates it from expired_credential.
- `case_037` (hard) truth **missing_env_var** -> unknown | blocked_correct_by_rules: truth on top at the end; rules: Competing hypothesis bad_config_deploy is still at 0.75 (>= 0.5); find evidence that discriminates it from missing_env_var.
- `case_043` (hard) truth **memory_leak** -> unknown | blocked_correct_by_rules: truth on top at the end; rules: Competing hypothesis cpu_hot_loop is still at 0.70 (>= 0.5); find evidence that discriminates it from memory_leak.
- `case_002` (hard) truth **slow_db_query** -> unknown | blocked_correct_by_skeptic: truth on top at the end; skeptic: Reviewer rejected slow_db_query: rule out db_pool_exhaustion with get_trace(service="checkout"): A trace on checkout could show if requests are waiting on DB co
- `case_005` (hard) truth **dependency_unavailable** -> unknown | blocked_correct_by_skeptic: truth on top at the end; skeptic: Reviewer rejected dependency_unavailable: rule out bad_config_deploy with get_service_config(service="api-gateway"): Check if a recent config change in api-gate
- `case_025` (easy) truth **bad_config_deploy** -> unknown | budget_exhausted_wrong_top: budget exhausted with top=dependency_unavailable
- `case_027` (easy) truth **expired_credential** -> unknown | budget_exhausted_wrong_top: budget exhausted with top=dependency_unavailable
- `case_038` (hard) truth **cpu_hot_loop** -> unknown | budget_exhausted_wrong_top: budget exhausted with top=unknown
- `case_001` (medium) truth **missing_env_var** -> dependency_unavailable | hypothesis_drifted_away: truth was top at steps [1], final top dependency_unavailable (key evidence at step 5)
- `case_011` (medium) truth **unknown** -> dependency_unavailable | hypothesis_drifted_away: truth was top at steps [1], final top dependency_unavailable (key evidence at step 4)
- `case_042` (easy) truth **unknown** -> dependency_unavailable | hypothesis_drifted_away: truth was top at steps [1], final top dependency_unavailable (key evidence at step 3)
- `case_042` (easy) truth **unknown** -> db_pool_exhaustion | hypothesis_drifted_away: truth was top at steps [1], final top db_pool_exhaustion (key evidence at step 4)
- `case_004` (easy) truth **missing_env_var** -> dependency_unavailable | planner_missed_key_evidence: concluded dependency_unavailable without key evidence
- `case_011` (medium) truth **unknown** -> dependency_unavailable | planner_missed_key_evidence: concluded dependency_unavailable without key evidence
- `case_036` (medium) truth **expired_credential** -> dependency_unavailable | planner_missed_key_evidence: concluded dependency_unavailable without key evidence
- `case_037` (hard) truth **missing_env_var** -> bad_config_deploy | planner_missed_key_evidence: concluded bad_config_deploy without key evidence
- `case_044` (hard) truth **db_pool_exhaustion** -> dependency_unavailable | planner_missed_key_evidence: concluded dependency_unavailable without key evidence
- `case_001` (medium) truth **missing_env_var** -> bad_config_deploy | verifier_accepted_wrong: key evidence at step 4; truth never top; verifier accepted bad_config_deploy
- `case_003` (hard) truth **unknown** -> dependency_unavailable | verifier_accepted_wrong: key evidence at step 4; truth never top; verifier accepted dependency_unavailable
- `case_003` (hard) truth **unknown** -> dependency_unavailable | verifier_accepted_wrong: key evidence at step 6; truth never top; verifier accepted dependency_unavailable
- `case_004` (easy) truth **missing_env_var** -> dependency_unavailable | verifier_accepted_wrong: key evidence at step 4; truth never top; verifier accepted dependency_unavailable
- `case_020` (medium) truth **bad_config_deploy** -> dependency_unavailable | verifier_accepted_wrong: key evidence at step 3; truth never top; verifier accepted dependency_unavailable

## E. B + checklist & margin rules

- `case_004` (easy) truth **missing_env_var** -> unknown | blocked_correct_by_rules: truth on top at the end; rules: Supporting evidence for missing_env_var comes from 1 source type(s); need at least 2.
- `case_037` (hard) truth **missing_env_var** -> unknown | blocked_correct_by_rules: truth on top at the end; rules: missing_env_var (0.97) does not lead bad_config_deploy (0.80) by 0.3; find discriminating evidence.
- `case_001` (medium) truth **missing_env_var** -> unknown | budget_exhausted_wrong_top: budget exhausted with top=bad_config_deploy
- `case_001` (medium) truth **missing_env_var** -> bad_config_deploy | hypothesis_drifted_away: truth was top at steps [1], final top bad_config_deploy (key evidence at step 5)
- `case_003` (hard) truth **unknown** -> slow_db_query | hypothesis_drifted_away: truth was top at steps [1, 3], final top slow_db_query (key evidence at step 5)
- `case_020` (medium) truth **bad_config_deploy** -> dependency_unavailable | hypothesis_drifted_away: truth was top at steps [2, 3], final top dependency_unavailable (key evidence at step 3)
- `case_042` (easy) truth **unknown** -> bad_config_deploy | hypothesis_drifted_away: truth was top at steps [1, 2, 3, 5], final top bad_config_deploy (key evidence at step 4)
- `case_003` (hard) truth **unknown** -> bad_config_deploy | hypothesis_never_ranked_truth: key evidence at step 7; truth never top; final bad_config_deploy
- `case_035` (medium) truth **memory_leak** -> cpu_hot_loop | hypothesis_never_ranked_truth: key evidence at step 3; truth never top; final cpu_hot_loop
- `case_035` (medium) truth **memory_leak** -> cpu_hot_loop | hypothesis_never_ranked_truth: key evidence at step 3; truth never top; final cpu_hot_loop
- `case_042` (easy) truth **unknown** -> dependency_unavailable | hypothesis_never_ranked_truth: key evidence at step 5; truth never top; final dependency_unavailable
- `case_043` (hard) truth **memory_leak** -> cpu_hot_loop | hypothesis_never_ranked_truth: key evidence at step 3; truth never top; final cpu_hot_loop
- `case_002` (hard) truth **slow_db_query** -> db_pool_exhaustion | planner_missed_key_evidence: concluded db_pool_exhaustion without key evidence
- `case_002` (hard) truth **slow_db_query** -> db_pool_exhaustion | planner_missed_key_evidence: concluded db_pool_exhaustion without key evidence
- `case_004` (easy) truth **missing_env_var** -> dependency_unavailable | planner_missed_key_evidence: concluded dependency_unavailable without key evidence
- `case_011` (medium) truth **unknown** -> dependency_unavailable | planner_missed_key_evidence: concluded dependency_unavailable without key evidence
- `case_011` (medium) truth **unknown** -> dependency_unavailable | planner_missed_key_evidence: concluded dependency_unavailable without key evidence
- `case_020` (medium) truth **bad_config_deploy** -> dependency_unavailable | planner_missed_key_evidence: concluded dependency_unavailable without key evidence
- `case_027` (easy) truth **expired_credential** -> dependency_unavailable | planner_missed_key_evidence: concluded dependency_unavailable without key evidence
- `case_027` (easy) truth **expired_credential** -> dependency_unavailable | planner_missed_key_evidence: concluded dependency_unavailable without key evidence
- `case_036` (medium) truth **expired_credential** -> dependency_unavailable | planner_missed_key_evidence: concluded dependency_unavailable without key evidence
- `case_036` (medium) truth **expired_credential** -> dependency_unavailable | planner_missed_key_evidence: concluded dependency_unavailable without key evidence
- `case_037` (hard) truth **missing_env_var** -> dependency_unavailable | planner_missed_key_evidence: concluded dependency_unavailable without key evidence
- `case_039` (hard) truth **expired_credential** -> dependency_unavailable | planner_missed_key_evidence: concluded dependency_unavailable without key evidence
- `case_039` (hard) truth **expired_credential** -> dependency_unavailable | planner_missed_key_evidence: concluded dependency_unavailable without key evidence
- `case_044` (hard) truth **db_pool_exhaustion** -> dependency_unavailable | planner_missed_key_evidence: concluded dependency_unavailable without key evidence
- `case_044` (hard) truth **db_pool_exhaustion** -> dependency_unavailable | planner_missed_key_evidence: concluded dependency_unavailable without key evidence

## F. E + LLM skeptic

- `case_001` (medium) truth **missing_env_var** -> unknown | blocked_correct_by_rules: truth on top at the end; rules: missing_env_var (0.95) does not lead bad_config_deploy (0.75) by 0.3; find discriminating evidence.
- `case_037` (hard) truth **missing_env_var** -> unknown | blocked_correct_by_rules: truth on top at the end; rules: missing_env_var (0.98) does not lead bad_config_deploy (0.85) by 0.3; find discriminating evidence.
- `case_039` (hard) truth **expired_credential** -> unknown | blocked_correct_by_rules: truth on top at the end; rules: expired_credential (0.90) does not lead dependency_unavailable (0.80) by 0.3; find discriminating evidence.
- `case_020` (medium) truth **bad_config_deploy** -> unknown | budget_exhausted_wrong_top: budget exhausted with top=dependency_unavailable
- `case_022` (hard) truth **bad_config_deploy** -> unknown | budget_exhausted_wrong_top: budget exhausted with top=dependency_unavailable
- `case_036` (medium) truth **expired_credential** -> unknown | budget_exhausted_wrong_top: budget exhausted with top=dependency_unavailable
- `case_011` (medium) truth **unknown** -> dependency_unavailable | hypothesis_drifted_away: truth was top at steps [1], final top dependency_unavailable (key evidence at step 4)
- `case_014` (easy) truth **memory_leak** -> cpu_hot_loop | hypothesis_drifted_away: truth was top at steps [4, 5, 6, 7], final top cpu_hot_loop (key evidence at step 3)
- `case_037` (hard) truth **missing_env_var** -> bad_config_deploy | hypothesis_drifted_away: truth was top at steps [1, 2], final top bad_config_deploy (key evidence at step 6)
- `case_042` (easy) truth **unknown** -> dependency_unavailable | hypothesis_drifted_away: truth was top at steps [1], final top dependency_unavailable (key evidence at step 4)
- `case_001` (medium) truth **missing_env_var** -> bad_config_deploy | hypothesis_never_ranked_truth: key evidence at step 5; truth never top; final bad_config_deploy
- `case_003` (hard) truth **unknown** -> dependency_unavailable | hypothesis_never_ranked_truth: key evidence at step 4; truth never top; final dependency_unavailable
- `case_003` (hard) truth **unknown** -> dependency_unavailable | hypothesis_never_ranked_truth: key evidence at step 5; truth never top; final dependency_unavailable
- `case_004` (easy) truth **missing_env_var** -> dependency_unavailable | hypothesis_never_ranked_truth: key evidence at step 5; truth never top; final dependency_unavailable
- `case_014` (easy) truth **memory_leak** -> cpu_hot_loop | hypothesis_never_ranked_truth: key evidence at step 3; truth never top; final cpu_hot_loop
- `case_020` (medium) truth **bad_config_deploy** -> dependency_unavailable | hypothesis_never_ranked_truth: key evidence at step 4; truth never top; final dependency_unavailable
- `case_036` (medium) truth **expired_credential** -> dependency_unavailable | hypothesis_never_ranked_truth: key evidence at step 5; truth never top; final dependency_unavailable
- `case_002` (hard) truth **slow_db_query** -> db_pool_exhaustion | planner_missed_key_evidence: concluded db_pool_exhaustion without key evidence
- `case_005` (hard) truth **dependency_unavailable** -> bad_config_deploy | planner_missed_key_evidence: concluded bad_config_deploy without key evidence
- `case_011` (medium) truth **unknown** -> dependency_unavailable | planner_missed_key_evidence: concluded dependency_unavailable without key evidence
- `case_013` (medium) truth **slow_db_query** -> dependency_unavailable | planner_missed_key_evidence: concluded dependency_unavailable without key evidence
- `case_023` (easy) truth **slow_db_query** -> bad_config_deploy | planner_missed_key_evidence: concluded bad_config_deploy without key evidence
- `case_027` (easy) truth **expired_credential** -> dependency_unavailable | planner_missed_key_evidence: concluded dependency_unavailable without key evidence
- `case_027` (easy) truth **expired_credential** -> dependency_unavailable | planner_missed_key_evidence: concluded dependency_unavailable without key evidence
- `case_044` (hard) truth **db_pool_exhaustion** -> dependency_unavailable | planner_missed_key_evidence: concluded dependency_unavailable without key evidence
- `case_044` (hard) truth **db_pool_exhaustion** -> dependency_unavailable | planner_missed_key_evidence: concluded dependency_unavailable without key evidence
