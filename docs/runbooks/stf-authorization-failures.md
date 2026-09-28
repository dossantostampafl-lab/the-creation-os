# STF authorization failures

Every denial carries reason codes in the decision and in the Chronicle (`stf_action_decided`).

| Reason | Meaning | Action |
|---|---|---|
| `environment_not_authorized` | action environment is not in the contract | fix the request or compile a new contract; never widen silently |
| `target_not_authorized` | target absent or excluded | new Mission if scope must grow |
| `outside_time_window` | contract window closed or not open | compile a new contract |
| `mission_version_mismatch` | stale action | re-read the contract hash and resubmit |
| `creator_approval_required` | R3/R4 without approval | Creator approves through `/approval` |
| `new_mission_required` | R5 | compile a new Mission |
| `policy_unavailable` | OPA unreachable | restore OPA; nothing runs meanwhile |
| `kill_switch` | Mission or global kill active | see stf-kill-switch |
| `grant_invalid` | grant expired, revoked, spent or for another target | issue a new decision |
| `gateway_unavailable` / `SandboxUnavailable` | privileged path is off | see sandbox-selection |
