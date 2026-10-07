"""A reserve provider that is not fully configured must not take down a working primary."""

import pytest

from app.config import settings
from app.inference import bootstrap
from app.inference.status import configured_inference_status


@pytest.fixture
def chain(monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "freellmapi")
    monkeypatch.setattr(settings, "llm_fallback_providers", "anthropic")
    monkeypatch.setenv("FREELLMAPI_BASE_URL", "http://localhost:3001/v1")
    monkeypatch.setenv("FREELLMAPI_MODEL", "auto")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_MODEL", raising=False)


def test_a_reserve_without_its_key_is_skipped_and_the_primary_still_serves(chain):
    router = bootstrap.build_model_router()
    assert tuple(router.registry.names()) == ("freellmapi",)


def test_a_misconfigured_primary_still_fails_loudly(chain, monkeypatch):
    monkeypatch.delenv("FREELLMAPI_MODEL")
    with pytest.raises(RuntimeError):
        bootstrap.build_model_router()


async def test_the_status_stays_configured_when_only_the_reserve_is_broken(chain):
    snapshot = await configured_inference_status("freellmapi")
    assert snapshot.configured and [item.provider for item in snapshot.providers] == ["freellmapi"]


async def test_deus_answers_with_503_not_500_when_every_provider_fails(chain, monkeypatch):
    import uuid

    from httpx import ASGITransport, AsyncClient

    from app.api import deus as deus_api
    from app.inference.contracts import InferenceUpstreamResponseError
    from app.main import app

    class Down:
        registry = None

        async def generate(self, request):
            raise InferenceUpstreamResponseError("freellmapi", "FreeLLMAPI network request failed")

    monkeypatch.setattr(deus_api, "build_model_router", lambda: Down())
    monkeypatch.setattr(deus_api, "resolve_configured_model", lambda router: "auto")

    class Service:
        def __init__(self, *args, **kwargs):
            self.router = args[1]

        async def respond(self, *args, **kwargs):
            await self.router.generate(None)

    class Session:
        async def rollback(self):
            pass

    monkeypatch.setattr(deus_api, "DeusConversationService", Service)
    from app.api.dependencies import actor
    from app.core.domain import Actor

    app.dependency_overrides[actor] = lambda: Actor(id="creator-1", role="creator")
    app.dependency_overrides[deus_api.get_session] = lambda: Session()
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(f"/api/v1/conversations/{uuid.uuid4()}/deus", json={"content": "oi"},
                                         )
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 503
    detail = response.json()["detail"]
    assert detail["provider"] == "freellmapi"
    assert detail["code"] == "INFERENCE_UPSTREAM_RESPONSE_ERROR"
    assert "provedor de inferência" in detail["message"]


@pytest.mark.parametrize(
    ("upstream_status", "upstream_code", "expected_status"),
    [
        (403, "provider_error", 403),
        (403, "subscription_sharing_user_not_eligible", 403),
        (401, "subscription_sharing_invalid_user", 401),
        (403, "chatpass_v2_scope_not_authorized", 403),
        (400, "subscription_sharing_unsupported_capability", 400),
        (403, "subscription_sharing_route_not_supported", 403),
    ],
)
async def test_deus_preserves_nonretryable_chatgpt_admission_and_contract_statuses(
    chain, monkeypatch, upstream_status, upstream_code, expected_status
):
    import uuid

    from httpx import ASGITransport, AsyncClient

    from app.api import deus as deus_api
    from app.inference.contracts import InferenceUpstreamResponseError
    from app.main import app

    class Restricted:
        registry = None

        async def generate(self, request):
            raise InferenceUpstreamResponseError(
                "chatgpt",
                "direct admission or contract failure",
                upstream_status=upstream_status,
                upstream_code=upstream_code,
                upstream_body={"detail": "restriction"},
            )

    monkeypatch.setattr(deus_api, "build_model_router", lambda: Restricted())
    monkeypatch.setattr(deus_api, "resolve_configured_model", lambda router: "gpt-6.1-sol")

    class Service:
        def __init__(self, *args, **kwargs):
            self.router = args[1]

        async def respond(self, *args, **kwargs):
            await self.router.generate(None)

    class Session:
        async def rollback(self):
            pass

    monkeypatch.setattr(deus_api, "DeusConversationService", Service)
    from app.api.dependencies import actor
    from app.core.domain import Actor

    app.dependency_overrides[actor] = lambda: Actor(id="creator-1", role="creator")
    app.dependency_overrides[deus_api.get_session] = lambda: Session()
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                f"/api/v1/conversations/{uuid.uuid4()}/deus",
                json={"content": "oi"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == expected_status
    detail = response.json()["detail"]
    assert detail["provider"] == "chatgpt"
    assert detail["upstream_status"] == upstream_status
    assert detail["code"] == upstream_code
    assert detail["retryable"] is False
