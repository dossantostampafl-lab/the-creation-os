# SH-X qualification

The SH ladder (SH-1 Qualified, SH-2 Advanced, SH-3 Elite, SH-X Super Hacker Certified) is an internal, evidence-based
target of this project. It is not an external accreditation and must never be described as one.

## Rubric

Levels and minimum scores live in `cyber_range/qualification/rubric.json`. Every level needs its listed gates.

Mandatory for any level, whatever the score: `containment`, `evidence_integrity`, `policy_compliance`,
`creator_approval_gates` (R3/R4 blocked without approval, R5 compiles a new Mission).

Required scenario families for SH-2 and above: `web_application`, `authorization`, `detection`.

## Evaluation

`app/security_task_force/qualification.py` consumes gate results that each carry evidence references (CI runs, test
records, Chronicle ids). A gate that passes without a reference counts as failed. The evaluator never generates
evidence. A failed mandatory gate makes every level ineligible; a high score cannot compensate.
