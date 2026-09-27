# Failure attribution

| Category | E. B + checklist & margin rules | F. E + LLM skeptic |
|---|---|---|
| blocked_correct_by_rules | 1 | 2 |
| budget_exhausted_wrong_top | 2 |  |
| hypothesis_drifted_away | 3 | 2 |
| hypothesis_never_ranked_truth |  | 2 |
| planner_missed_key_evidence | 7 | 7 |
| **total wrong** | 13 | 13 |

## E. B + checklist & margin rules

- `case_010` (hard) truth **db_pool_exhaustion** -> unknown | blocked_correct_by_rules: truth on top at the end; rules: Supporting evidence for db_pool_exhaustion comes from 1 source type(s); need at least 2.
- `case_028` (hard) truth **memory_leak** -> unknown | budget_exhausted_wrong_top: budget exhausted with top=cpu_hot_loop
- `case_033` (hard) truth **bad_config_deploy** -> unknown | budget_exhausted_wrong_top: budget exhausted with top=dependency_unavailable
- `case_007` (medium) truth **missing_env_var** -> bad_config_deploy | hypothesis_drifted_away: truth was top at steps [1, 2], final top bad_config_deploy (key evidence at step 5)
- `case_007` (medium) truth **missing_env_var** -> bad_config_deploy | hypothesis_drifted_away: truth was top at steps [1, 2], final top bad_config_deploy (key evidence at step 5)
- `case_009` (hard) truth **missing_env_var** -> bad_config_deploy | hypothesis_drifted_away: truth was top at steps [1, 2, 3], final top bad_config_deploy (key evidence at step 8)
- `case_006` (hard) truth **expired_credential** -> dependency_unavailable | planner_missed_key_evidence: concluded dependency_unavailable without key evidence
- `case_006` (hard) truth **expired_credential** -> dependency_unavailable | planner_missed_key_evidence: concluded dependency_unavailable without key evidence
- `case_009` (hard) truth **missing_env_var** -> dependency_unavailable | planner_missed_key_evidence: concluded dependency_unavailable without key evidence
- `case_012` (hard) truth **unknown** -> dependency_unavailable | planner_missed_key_evidence: concluded dependency_unavailable without key evidence
- `case_012` (hard) truth **unknown** -> dependency_unavailable | planner_missed_key_evidence: concluded dependency_unavailable without key evidence
- `case_029` (hard) truth **slow_db_query** -> db_pool_exhaustion | planner_missed_key_evidence: concluded db_pool_exhaustion without key evidence
- `case_040` (medium) truth **bad_config_deploy** -> dependency_unavailable | planner_missed_key_evidence: concluded dependency_unavailable without key evidence

## F. E + LLM skeptic

- `case_018` (medium) truth **memory_leak** -> unknown | blocked_correct_by_rules: truth on top at the end; rules: memory_leak (0.85) does not lead cpu_hot_loop (0.75) by 0.3; find discriminating evidence.
- `case_028` (hard) truth **memory_leak** -> unknown | blocked_correct_by_rules: truth on top at the end; rules: memory_leak (0.95) does not lead cpu_hot_loop (0.85) by 0.3; find discriminating evidence.
- `case_007` (medium) truth **missing_env_var** -> bad_config_deploy | hypothesis_drifted_away: truth was top at steps [1, 2], final top bad_config_deploy (key evidence at step 5)
- `case_007` (medium) truth **missing_env_var** -> dependency_unavailable | hypothesis_drifted_away: truth was top at steps [1], final top dependency_unavailable (key evidence at step 5)
- `case_016` (medium) truth **unknown** -> dependency_unavailable | hypothesis_never_ranked_truth: key evidence at step 5; truth never top; final dependency_unavailable
- `case_018` (medium) truth **memory_leak** -> cpu_hot_loop | hypothesis_never_ranked_truth: key evidence at step 1; truth never top; final cpu_hot_loop
- `case_006` (hard) truth **expired_credential** -> dependency_unavailable | planner_missed_key_evidence: concluded dependency_unavailable without key evidence
- `case_009` (hard) truth **missing_env_var** -> dependency_unavailable | planner_missed_key_evidence: concluded dependency_unavailable without key evidence
- `case_009` (hard) truth **missing_env_var** -> dependency_unavailable | planner_missed_key_evidence: concluded dependency_unavailable without key evidence
- `case_010` (hard) truth **db_pool_exhaustion** -> bad_config_deploy | planner_missed_key_evidence: concluded bad_config_deploy without key evidence
- `case_012` (hard) truth **unknown** -> dependency_unavailable | planner_missed_key_evidence: concluded dependency_unavailable without key evidence
- `case_016` (medium) truth **unknown** -> dependency_unavailable | planner_missed_key_evidence: concluded dependency_unavailable without key evidence
- `case_029` (hard) truth **slow_db_query** -> db_pool_exhaustion | planner_missed_key_evidence: concluded db_pool_exhaustion without key evidence
