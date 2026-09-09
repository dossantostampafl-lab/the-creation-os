# Intelligence Fabric Phase 2 — Capability and Model Evidence Plan

**Goal:** Extend the existing Creation-owned inference runtime with explicit provider/model capability evidence so routing can reject incompatible candidates before network execution, while preserving explicit preferred/fallback governance.

**Base:** Stacked on `feat/freellmapi-phase1`; Phase 1 PR #11 remains independently reviewable.

## Constraints

- `ModelRouter` and `ProviderRegistry` remain canonical.
- No automatic provider discovery or implicit fallback in this phase.
- Capability metadata is evidence/admission data, not an authorization bypass.
- Unknown capability evidence fails closed when the request explicitly requires that capability.
- Existing requests without required capabilities preserve current behavior.
- No provider-advertised capability is treated as benchmark proof; metadata is Creation-owned configuration/evidence.
- No fake telemetry or live external keys in tests.

## Task 1 — Capability contracts and registry metadata

**Files:**
- Modify: `backend/app/inference/contracts.py`
- Modify: `backend/app/inference/registry.py`
- Test: `backend/tests/test_inference_capabilities.py`

Add:
- `ModelRequirements.required_capabilities: set[str]`
- immutable `ProviderModelProfile` containing provider, model and capabilities
- registry methods to register and query profiles
- duplicate profile rejection

## Task 2 — Capability admission in router

**Files:**
- Modify: `backend/app/inference/router.py`
- Test: `backend/tests/test_inference_capabilities.py`

Behavior:
- preserve explicit candidate order
- if no capabilities are requested, preserve current routing
- when capabilities are required, candidate must have Creation-owned evidence for the selected/requested model
- incompatible or missing evidence is treated as unavailable for that request and can advance only to an explicitly listed fallback
- no provider outside the explicit candidate list may be selected

## Task 3 — Provider profile bootstrap

**Files:**
- Modify: `backend/app/inference/bootstrap.py`
- Test: `backend/tests/test_inference_capabilities.py`

Register conservative Phase 2 profiles for configured providers. Initial profiles cover only capabilities actually implemented by the adapter in Creation (`text`, `streaming` where supported); tool execution is not admitted by FreeLLMAPI Phase 1.

## Task 4 — Verification

- TDD RED -> GREEN for each behavior.
- Ruff, mypy, migrations, full pytest.
- Frontend build/unit/Playwright regression gate.
- Diff audit: no implicit fallback, no invented model capabilities, no provider leakage into cognitive layers, no secrets.
