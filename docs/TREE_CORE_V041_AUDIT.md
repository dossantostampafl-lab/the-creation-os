# Tree Core v0.4.1 Stabilization Audit

## Files

Created:

- `C:\Users\dossa\OneDrive\Área de Trabalho\THE CREATION OS\ARCHITECTURE.md`
- `C:\Users\dossa\OneDrive\Área de Trabalho\THE CREATION OS\backend\alembic\versions\0004_tree_core_foundation.py`
- `C:\Users\dossa\OneDrive\Área de Trabalho\THE CREATION OS\backend\app\api\tree_core.py`
- `C:\Users\dossa\OneDrive\Área de Trabalho\THE CREATION OS\backend\app\repositories\tree_core.py`
- `C:\Users\dossa\OneDrive\Área de Trabalho\THE CREATION OS\backend\app\schemas\tree_core.py`
- `C:\Users\dossa\OneDrive\Área de Trabalho\THE CREATION OS\backend\app\services\tree_core.py`
- `C:\Users\dossa\OneDrive\Área de Trabalho\THE CREATION OS\backend\tests\test_tree_core.py`
- `C:\Users\dossa\OneDrive\Área de Trabalho\THE CREATION OS\backend\tests\test_tree_core_http.py`
- `C:\Users\dossa\OneDrive\Área de Trabalho\THE CREATION OS\backend\tests\test_tree_core_postgres.py`

Modified:

- `C:\Users\dossa\OneDrive\Área de Trabalho\THE CREATION OS\README.md`
- `C:\Users\dossa\OneDrive\Área de Trabalho\THE CREATION OS\backend\README.md`
- `C:\Users\dossa\OneDrive\Área de Trabalho\THE CREATION OS\backend\MIGRATIONS.md`
- `C:\Users\dossa\OneDrive\Área de Trabalho\THE CREATION OS\backend\app\api\__init__.py`
- `C:\Users\dossa\OneDrive\Área de Trabalho\THE CREATION OS\backend\app\models\entities.py`

## Agent state machine

Allowed persisted states are `idle`, `busy`, `offline`, and `disabled`, enforced
by `ck_agent_status`. Registration and enable produce `offline`; an authorized
heartbeat produces `idle`; disable produces `disabled`. No v0.4.1 endpoint sets
`busy`, because dispatch and execution are outside this version.

## Eligibility rules

Heartbeat validity is five minutes, inclusive at the cutoff. Match accepts only
an `authorized` Mission and requires every requested normalized capability.
Eligible agents must have `enabled=true`, status `idle`, and a non-expired
heartbeat. Results are ordered by priority descending, then name ascending, then
UUID ascending. Name and UUID therefore provide a deterministic priority tie-break.

Match performs SELECT statements only. It does not flush, commit, create a
Mission, approve a Mission, update Mission status, or update Agent status.

## Constraints and normalization

- Primary keys are UUID strings.
- Capability names are trimmed and lowercased by the service.
- Capability name uniqueness is enforced both by the column unique constraint
  and by `uq_capabilities_name_normalized` on `lower(name)`.
- `agent_capabilities` has a composite primary key `(agent_id, capability_id)`.
- Both association foreign keys use `ON DELETE CASCADE`.
- Agent status is constrained to the four allowed values.

## HTTP authorization and inputs

All 12 Tree Core routes depend on `get_sovereign_creator`. Missing authentication
returns 401; a valid non-sovereign subject returns 403. This includes heartbeat.

Accepted request fields:

- Agent create: `name`, `description`, `universe`, `priority`.
- Agent patch: `name`, `description`, `universe`, `priority`.
- Capability create: `name`, `description`.
- Capability assignment: `capability_id` (UUID).
- Match: `mission_id` (UUID), `required_capabilities`.

Input schemas forbid extra fields. Client-supplied `role`, `status`, `enabled`,
`heartbeat_at`, `created_at`, and `updated_at` are rejected with 422. Invalid path
or body UUIDs return 422; missing resources return 404; domain and uniqueness
conflicts return 409.

## Scope boundary

Tree Core v0.4.1 only registers agents and selects eligible agents. It contains no
Dispatch Queue, Execution Monitor, Result Aggregator, complete Universes, Pulse,
or Malkuth implementation. No Mission execution occurs.
