# Failure attribution

| Category | A. ReAct baseline |
|---|---|
| react_misread | 5 |
| **total wrong** | 5 |

## A. ReAct baseline

- `case_007` (medium) truth **missing_env_var** -> bad_config_deploy | react_misread: key evidence queried at step 6, still answered bad_config_deploy
- `case_009` (hard) truth **missing_env_var** -> bad_config_deploy | react_misread: key evidence queried at step 7, still answered bad_config_deploy
- `case_012` (hard) truth **unknown** -> dependency_unavailable | react_misread: key evidence queried at step 6, still answered dependency_unavailable
- `case_016` (medium) truth **unknown** -> dependency_unavailable | react_misread: key evidence queried at step 3, still answered dependency_unavailable
- `case_018` (medium) truth **memory_leak** -> cpu_hot_loop | react_misread: key evidence queried at step 1, still answered cpu_hot_loop
