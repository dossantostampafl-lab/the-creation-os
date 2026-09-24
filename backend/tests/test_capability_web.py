from __future__ import annotations

import socket

import httpx
import pytest

from app.capabilities.contracts import CapabilityContext, CapabilityIntent, MissionAuthorization
from app.capabilities.web import WebCapabilityAdapter


def context_for(**scope) -> CapabilityContext:
    return CapabilityContext(
        mission_id="mission-a",
        authorization=MissionAuthorization(
            allowed_capabilities=["web"], scope=scope,
            authorized_by="creator", authorized_at="2026-01-01T00:00:00Z",
        ),
    )


def intent_for(url: str | None, action: str = "fetch") -> CapabilityIntent:
    return CapabilityIntent(capability="web", action=action, resource=url)


def adapter_for(handler, *, resolves_to: str = "93.184.216.34", **kwargs) -> WebCapabilityAdapter:
    """An adapter whose name resolution is deterministic, so no test touches real DNS."""
    async def resolve(host: str) -> list[str]:
        if host == "unresolvable.invalid":
            raise socket.gaierror("no such host")
        return [resolves_to]

    return WebCapabilityAdapter(transport=httpx.MockTransport(handler), resolve=resolve, **kwargs)


def page(_request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, text="<h1>Hello</h1>", headers={"content-type": "text/html"})


@pytest.mark.asyncio
async def test_a_public_page_is_fetched() -> None:
    adapter = adapter_for(page)

    result = await adapter.execute(intent_for("https://example.com/docs"), context_for())

    assert result.ok
    assert result.data["status"] == 200
    assert result.data["content"] == "<h1>Hello</h1>"
    assert result.data["truncated"] is False


@pytest.mark.asyncio
@pytest.mark.parametrize("address", [
    "127.0.0.1",        # this machine — the API, FreeLLMAPI, anything bound to loopback
    "10.0.0.5",         # private network
    "192.168.1.10",     # private network
    "172.17.0.2",       # the Docker network where Postgres and Redis live
    "169.254.169.254",  # cloud metadata, the classic credential theft target
])
async def test_an_address_off_the_public_internet_is_refused(address: str) -> None:
    reached = []

    def handler(request: httpx.Request) -> httpx.Response:
        reached.append(str(request.url))
        return httpx.Response(200, text="secret")

    adapter = adapter_for(handler, resolves_to=address)

    result = await adapter.execute(intent_for("http://anything.example/"), context_for())

    assert not result.ok and result.error["code"] == "WEB_REJECTED"
    assert reached == [], "the request must not be made at all"


@pytest.mark.asyncio
@pytest.mark.parametrize("url", [
    "file:///etc/passwd",
    "ftp://example.com/x",
    "gopher://example.com/",
    "",
    "https://",
])
async def test_only_http_and_https_with_a_host_are_accepted(url: str) -> None:
    adapter = adapter_for(page)

    result = await adapter.execute(intent_for(url), context_for())

    assert not result.ok and result.error["code"] == "WEB_REJECTED"


@pytest.mark.asyncio
async def test_a_redirect_into_a_private_address_is_refused() -> None:
    """An open redirect is the usual way past a check made only on the first URL."""
    reached: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        reached.append(str(request.url))
        if request.url.host == "example.com":
            return httpx.Response(302, headers={"location": "http://internal.example/admin"})
        return httpx.Response(200, text="secret")

    async def resolve(host: str) -> list[str]:
        return ["127.0.0.1" if host == "internal.example" else "93.184.216.34"]

    adapter = WebCapabilityAdapter(transport=httpx.MockTransport(handler), resolve=resolve)

    result = await adapter.execute(intent_for("https://example.com/go"), context_for())

    assert not result.ok and result.error["code"] == "WEB_REJECTED"
    assert reached == ["https://example.com/go"], "the redirect must not be followed"


@pytest.mark.asyncio
async def test_a_redirect_to_another_public_page_is_followed() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/go":
            return httpx.Response(301, headers={"location": "https://example.com/final"})
        return httpx.Response(200, text="arrived")

    adapter = adapter_for(handler)

    result = await adapter.execute(intent_for("https://example.com/go"), context_for())

    assert result.ok and result.data["content"] == "arrived"
    assert result.data["url"].endswith("/final")


@pytest.mark.asyncio
async def test_the_creator_can_narrow_a_mission_to_named_hosts() -> None:
    adapter = adapter_for(page)
    scoped = context_for(web_allowed_hosts=["docs.example.com"])

    allowed = await adapter.execute(intent_for("https://docs.example.com/a"), scoped)
    refused = await adapter.execute(intent_for("https://other.example.com/a"), scoped)

    assert allowed.ok
    assert not refused.ok and "not in the authorized list" in refused.error["detail"]


@pytest.mark.asyncio
async def test_a_large_page_is_truncated_rather_than_swallowing_memory() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="x" * 5000)

    adapter = adapter_for(handler, max_bytes=100)

    result = await adapter.execute(intent_for("https://example.com/big"), context_for())

    assert result.ok and result.data["truncated"] is True
    assert len(result.data["content"]) == 100


@pytest.mark.asyncio
async def test_an_unresolvable_host_fails_without_raising() -> None:
    adapter = adapter_for(page)

    result = await adapter.execute(intent_for("https://unresolvable.invalid/"), context_for())

    assert not result.ok and result.error["code"] == "WEB_REJECTED"


@pytest.mark.asyncio
async def test_another_action_is_refused() -> None:
    adapter = adapter_for(page)

    result = await adapter.execute(intent_for("https://example.com/", action="post"), context_for())

    assert not result.ok and result.error["code"] == "WEB_REJECTED"


@pytest.mark.asyncio
async def test_a_host_restriction_that_cannot_be_read_is_not_treated_as_no_restriction() -> None:
    """Fail closed: a scope written the wrong way must not widen the Mission."""
    adapter = adapter_for(page)
    context = CapabilityContext(
        mission_id="mission-a",
        authorization=MissionAuthorization(
            allowed_capabilities=["web"], scope={"web_allowed_hosts": {"docs.example.com": True}},
            authorized_by="creator", authorized_at="2026-01-01T00:00:00Z",
        ),
    )

    result = await adapter.execute(intent_for("https://docs.example.com/a"), context)

    assert not result.ok and result.error["code"] == "WEB_REJECTED"


@pytest.mark.asyncio
async def test_a_single_host_written_as_a_string_still_narrows_the_mission() -> None:
    adapter = adapter_for(page)
    scoped = context_for(web_allowed_hosts="docs.example.com")

    allowed = await adapter.execute(intent_for("https://docs.example.com/a"), scoped)
    refused = await adapter.execute(intent_for("https://other.example.com/a"), scoped)

    assert allowed.ok
    assert not refused.ok


@pytest.mark.asyncio
@pytest.mark.parametrize("url", ["http://[::1", "http://:80/", "http://[not-an-ip]/"])
async def test_a_malformed_url_is_refused_rather_than_failing_the_task(url: str) -> None:
    adapter = adapter_for(page)

    result = await adapter.execute(intent_for(url), context_for())

    assert not result.ok and result.error["code"] == "WEB_REJECTED"


@pytest.mark.asyncio
async def test_the_limit_counts_bytes_not_characters() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="á" * 200, headers={"content-type": "text/plain; charset=utf-8"})

    adapter = adapter_for(handler, max_bytes=100)

    result = await adapter.execute(intent_for("https://example.com/big"), context_for())

    assert result.ok and result.data["truncated"] is True
    assert len(result.data["content"].encode("utf-8")) <= 100


@pytest.mark.asyncio
async def test_the_address_the_connection_reached_is_checked_again() -> None:
    """A name that answers public and then private (DNS rebinding) must not get through."""
    class _Stream:
        @staticmethod
        def get_extra_info(name: str):
            return ("127.0.0.1", 443) if name == "server_addr" else None

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="secret", extensions={"network_stream": _Stream()})

    adapter = adapter_for(handler)

    result = await adapter.execute(intent_for("https://example.com/"), context_for())

    assert not result.ok and result.error["code"] == "WEB_REJECTED"


@pytest.mark.asyncio
@pytest.mark.parametrize("host", ["::1", "::ffff:127.0.0.1", "127.0.0.1", "fd00::1", "0.0.0.0"])
async def test_an_address_written_straight_into_the_url_is_refused(host: str) -> None:
    """An IPv6 literal or an IPv4-mapped address must not slip past the public-internet check."""
    async def resolve(name: str) -> list[str]:
        return [name]

    adapter = WebCapabilityAdapter(
        transport=httpx.MockTransport(page), resolve=resolve,
    )
    bracketed = f"[{host}]" if ":" in host else host

    result = await adapter.execute(intent_for(f"http://{bracketed}/"), context_for())

    assert not result.ok and result.error["code"] == "WEB_REJECTED"


@pytest.mark.asyncio
async def test_an_address_that_cannot_be_read_fails_closed() -> None:
    async def resolve(_name: str) -> list[str]:
        return ["not-an-address"]

    adapter = WebCapabilityAdapter(transport=httpx.MockTransport(page), resolve=resolve)

    result = await adapter.execute(intent_for("https://example.com/"), context_for())

    assert not result.ok and result.error["code"] == "WEB_REJECTED"
