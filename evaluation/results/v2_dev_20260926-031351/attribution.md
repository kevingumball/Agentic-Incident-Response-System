# Failure attribution

| Category | A. ReAct baseline | B. Planner + Hypothesis (no verifier) | C. B + hard rules | D. C + LLM skeptic (phase-1 system) |
|---|---|---|---|---|
| blocked_correct_by_rules |  |  | 4 | 3 |
| budget_exhausted_wrong_top |  |  | 1 | 3 |
| hypothesis_drifted_away |  | 3 | 1 | 2 |
| hypothesis_never_ranked_truth |  | 9 |  |  |
| planner_missed_key_evidence |  |  | 15 | 5 |
| react_misread | 9 |  |  |  |
| verifier_accepted_wrong |  |  | 1 | 5 |
| **total wrong** | 9 | 12 | 22 | 18 |

## A. ReAct baseline

- `case_007` (medium) truth **missing_env_var** -> bad_config_deploy | react_misread: key evidence queried at step 6, still answered bad_config_deploy
- `case_007` (medium) truth **missing_env_var** -> bad_config_deploy | react_misread: key evidence queried at step 6, still answered bad_config_deploy
- `case_009` (hard) truth **missing_env_var** -> bad_config_deploy | react_misread: key evidence queried at step 7, still answered bad_config_deploy
- `case_009` (hard) truth **missing_env_var** -> bad_config_deploy | react_misread: key evidence queried at step 7, still answered bad_config_deploy
- `case_012` (hard) truth **unknown** -> dependency_unavailable | react_misread: key evidence queried at step 6, still answered dependency_unavailable
- `case_012` (hard) truth **unknown** -> bad_config_deploy | react_misread: key evidence queried at step 6, still answered bad_config_deploy
- `case_016` (medium) truth **unknown** -> dependency_unavailable | react_misread: key evidence queried at step 3, still answered dependency_unavailable
- `case_018` (medium) truth **memory_leak** -> cpu_hot_loop | react_misread: key evidence queried at step 1, still answered cpu_hot_loop
- `case_029` (hard) truth **slow_db_query** -> db_pool_exhaustion | react_misread: key evidence queried at step 6, still answered db_pool_exhaustion

## B. Planner + Hypothesis (no verifier)

- `case_007` (medium) truth **missing_env_var** -> bad_config_deploy | hypothesis_drifted_away: truth was top at steps [5], final top bad_config_deploy (key evidence at step 6)
- `case_007` (medium) truth **missing_env_var** -> bad_config_deploy | hypothesis_drifted_away: truth was top at steps [3], final top bad_config_deploy (key evidence at step 4)
- `case_019` (medium) truth **expired_credential** -> dependency_unavailable | hypothesis_drifted_away: truth was top at steps [5, 6], final top dependency_unavailable (key evidence at step 6)
- `case_006` (hard) truth **expired_credential** -> dependency_unavailable | hypothesis_never_ranked_truth: key evidence at step 7; truth never top; final dependency_unavailable
- `case_006` (hard) truth **expired_credential** -> dependency_unavailable | hypothesis_never_ranked_truth: key evidence at step 6; truth never top; final dependency_unavailable
- `case_009` (hard) truth **missing_env_var** -> bad_config_deploy | hypothesis_never_ranked_truth: key evidence at step 6; truth never top; final bad_config_deploy
- `case_009` (hard) truth **missing_env_var** -> bad_config_deploy | hypothesis_never_ranked_truth: key evidence at step 7; truth never top; final bad_config_deploy
- `case_012` (hard) truth **unknown** -> dependency_unavailable | hypothesis_never_ranked_truth: key evidence at step 6; truth never top; final dependency_unavailable
- `case_012` (hard) truth **unknown** -> bad_config_deploy | hypothesis_never_ranked_truth: key evidence at step 8; truth never top; final bad_config_deploy
- `case_016` (medium) truth **unknown** -> dependency_unavailable | hypothesis_never_ranked_truth: key evidence at step 3; truth never top; final dependency_unavailable
- `case_016` (medium) truth **unknown** -> dependency_unavailable | hypothesis_never_ranked_truth: key evidence at step 3; truth never top; final dependency_unavailable
- `case_033` (hard) truth **bad_config_deploy** -> dependency_unavailable | hypothesis_never_ranked_truth: key evidence at step 8; truth never top; final dependency_unavailable

## C. B + hard rules

- `case_009` (hard) truth **missing_env_var** -> unknown | blocked_correct_by_rules: truth on top at the end; rules: Competing hypothesis bad_config_deploy is still at 0.80 (>= 0.5); find evidence that discriminates it from missing_env_var.
- `case_018` (medium) truth **memory_leak** -> unknown | blocked_correct_by_rules: truth on top at the end; rules: Competing hypothesis cpu_hot_loop is still at 0.85 (>= 0.5); find evidence that discriminates it from memory_leak.
- `case_032` (medium) truth **db_pool_exhaustion** -> unknown | blocked_correct_by_rules: truth on top at the end; rules: Competing hypothesis dependency_unavailable is still at 0.50 (>= 0.5); find evidence that discriminates it from db_pool_exhaustion.
- `case_032` (medium) truth **db_pool_exhaustion** -> unknown | blocked_correct_by_rules: truth on top at the end; rules: Competing hypothesis dependency_unavailable is still at 0.60 (>= 0.5); find evidence that discriminates it from db_pool_exhaustion.
- `case_006` (hard) truth **expired_credential** -> unknown | budget_exhausted_wrong_top: budget exhausted with top=dependency_unavailable
- `case_007` (medium) truth **missing_env_var** -> bad_config_deploy | hypothesis_drifted_away: truth was top at steps [1], final top bad_config_deploy (key evidence at step 6)
- `case_006` (hard) truth **expired_credential** -> dependency_unavailable | planner_missed_key_evidence: concluded dependency_unavailable without key evidence
- `case_007` (medium) truth **missing_env_var** -> dependency_unavailable | planner_missed_key_evidence: concluded dependency_unavailable without key evidence
- `case_009` (hard) truth **missing_env_var** -> bad_config_deploy | planner_missed_key_evidence: concluded bad_config_deploy without key evidence
- `case_010` (hard) truth **db_pool_exhaustion** -> dependency_unavailable | planner_missed_key_evidence: concluded dependency_unavailable without key evidence
- `case_010` (hard) truth **db_pool_exhaustion** -> cpu_hot_loop | planner_missed_key_evidence: concluded cpu_hot_loop without key evidence
- `case_012` (hard) truth **unknown** -> dependency_unavailable | planner_missed_key_evidence: concluded dependency_unavailable without key evidence
- `case_012` (hard) truth **unknown** -> dependency_unavailable | planner_missed_key_evidence: concluded dependency_unavailable without key evidence
- `case_016` (medium) truth **unknown** -> dependency_unavailable | planner_missed_key_evidence: concluded dependency_unavailable without key evidence
- `case_019` (medium) truth **expired_credential** -> dependency_unavailable | planner_missed_key_evidence: concluded dependency_unavailable without key evidence
- `case_028` (hard) truth **memory_leak** -> dependency_unavailable | planner_missed_key_evidence: concluded dependency_unavailable without key evidence
- `case_028` (hard) truth **memory_leak** -> bad_config_deploy | planner_missed_key_evidence: concluded bad_config_deploy without key evidence
- `case_029` (hard) truth **slow_db_query** -> dependency_unavailable | planner_missed_key_evidence: concluded dependency_unavailable without key evidence
- `case_033` (hard) truth **bad_config_deploy** -> dependency_unavailable | planner_missed_key_evidence: concluded dependency_unavailable without key evidence
- `case_040` (medium) truth **bad_config_deploy** -> dependency_unavailable | planner_missed_key_evidence: concluded dependency_unavailable without key evidence
- `case_040` (medium) truth **bad_config_deploy** -> dependency_unavailable | planner_missed_key_evidence: concluded dependency_unavailable without key evidence
- `case_016` (medium) truth **unknown** -> dependency_unavailable | verifier_accepted_wrong: key evidence at step 4; truth never top; verifier accepted dependency_unavailable

## D. C + LLM skeptic (phase-1 system)

- `case_018` (medium) truth **memory_leak** -> unknown | blocked_correct_by_rules: truth on top at the end; rules: Top hypothesis memory_leak has confidence 0.30 < 0.8.
- `case_029` (hard) truth **slow_db_query** -> unknown | blocked_correct_by_rules: truth on top at the end; rules: Competing hypothesis bad_config_deploy is still at 0.75 (>= 0.5); find evidence that discriminates it from slow_db_query.
- `case_041` (medium) truth **dependency_unavailable** -> unknown | blocked_correct_by_rules: truth on top at the end; rules: Competing hypothesis unknown is still at 0.50 (>= 0.5); find evidence that discriminates it from dependency_unavailable.
- `case_007` (medium) truth **missing_env_var** -> unknown | budget_exhausted_wrong_top: budget exhausted with top=bad_config_deploy
- `case_028` (hard) truth **memory_leak** -> unknown | budget_exhausted_wrong_top: budget exhausted with top=dependency_unavailable
- `case_033` (hard) truth **bad_config_deploy** -> unknown | budget_exhausted_wrong_top: budget exhausted with top=dependency_unavailable
- `case_009` (hard) truth **missing_env_var** -> bad_config_deploy | hypothesis_drifted_away: truth was top at steps [2], final top bad_config_deploy (key evidence at step 8)
- `case_010` (hard) truth **db_pool_exhaustion** -> cpu_hot_loop | hypothesis_drifted_away: truth was top at steps [5, 6], final top cpu_hot_loop (key evidence at step 7)
- `case_006` (hard) truth **expired_credential** -> dependency_unavailable | planner_missed_key_evidence: concluded dependency_unavailable without key evidence
- `case_006` (hard) truth **expired_credential** -> dependency_unavailable | planner_missed_key_evidence: concluded dependency_unavailable without key evidence
- `case_012` (hard) truth **unknown** -> dependency_unavailable | planner_missed_key_evidence: concluded dependency_unavailable without key evidence
- `case_012` (hard) truth **unknown** -> dependency_unavailable | planner_missed_key_evidence: concluded dependency_unavailable without key evidence
- `case_028` (hard) truth **memory_leak** -> dependency_unavailable | planner_missed_key_evidence: concluded dependency_unavailable without key evidence
- `case_007` (medium) truth **missing_env_var** -> dependency_unavailable | verifier_accepted_wrong: key evidence at step 7; truth never top; verifier accepted dependency_unavailable
- `case_009` (hard) truth **missing_env_var** -> bad_config_deploy | verifier_accepted_wrong: key evidence at step 7; truth never top; verifier accepted bad_config_deploy
- `case_010` (hard) truth **db_pool_exhaustion** -> dependency_unavailable | verifier_accepted_wrong: key evidence at step 7; truth never top; verifier accepted dependency_unavailable
- `case_016` (medium) truth **unknown** -> dependency_unavailable | verifier_accepted_wrong: key evidence at step 3; truth never top; verifier accepted dependency_unavailable
- `case_016` (medium) truth **unknown** -> slow_db_query | verifier_accepted_wrong: key evidence at step 3; truth never top; verifier accepted slow_db_query
