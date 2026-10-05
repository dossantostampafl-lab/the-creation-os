from __future__ import annotations

import httpx
import pytest

from app.capabilities.contracts import CapabilityContext, CapabilityIntent, MissionAuthorization
from app.capabilities.web import WebCapabilityAdapter


def context(hosts=None):
    return CapabilityContext(mission_id='public-research', authorization=MissionAuthorization(
        allowed_capabilities=['web'], scope={} if hosts is None else {'web_allowed_hosts': hosts},
        authorized_by='creator', authorized_at='2026-10-05T00:00:00Z'))


@pytest.mark.asyncio
async def test_public_search_reads_bounded_rss_and_caches_without_credentials():
    from app.capabilities.public_news import PublicNewsProvider
    calls = []
    async def resolve(host):
        return ['142.250.74.14']
    def serve(request):
        calls.append(request)
        items = ''.join(f'<item><title>Software {i}</title><link>https://news.google.com/articles/{i}</link><pubDate>Mon, 05 Oct 2026 00:00:00 GMT</pubDate></item>' for i in range(8))
        return httpx.Response(200, text=f'<rss><channel>{items}</channel></rss>')
    reader = WebCapabilityAdapter(transport=httpx.MockTransport(serve), resolve=resolve)
    provider = PublicNewsProvider(reader=reader, interval_seconds=0)
    gateway = WebCapabilityAdapter(providers=[provider], resolve=resolve)
    intent = CapabilityIntent(capability='web', action='search', arguments={'query': 'engenharia software'})
    first = await gateway.execute(intent, context())
    second = await gateway.execute(intent, context())
    assert first.ok and second.ok
    assert len(first.data['items']) == 3
    assert first.data == second.data
    assert len(calls) == 1
    assert calls[0].method == 'GET'
    assert calls[0].url.host == 'news.google.com'
    assert not calls[0].headers.get('authorization')
    assert first.data['items'][0]['title'] == 'Software 0'
    assert not (await gateway.execute(intent, context(['example.com']))).ok


@pytest.mark.asyncio
@pytest.mark.parametrize('response', [httpx.Response(429), httpx.Response(200, text='<rss>invalid'), httpx.Response(200, text='x' * 501000)])
async def test_unavailable_or_malformed_news_is_not_evidence(response):
    from app.capabilities.public_news import PublicNewsProvider
    async def resolve(host):
        return ['142.250.74.14']
    reader = WebCapabilityAdapter(transport=httpx.MockTransport(lambda request: response), resolve=resolve)
    gateway = WebCapabilityAdapter(providers=[PublicNewsProvider(reader=reader, interval_seconds=0)], resolve=resolve)
    result = await gateway.execute(CapabilityIntent(capability='web', action='search', arguments={'query': 'software'}), context())
    assert not result.ok


@pytest.mark.asyncio
async def test_public_news_cannot_follow_redirect_into_private_network():
    from app.capabilities.public_news import PublicNewsProvider
    async def resolve(host):
        return ['127.0.0.1'] if host == 'localhost' else ['142.250.74.14']
    reader = WebCapabilityAdapter(transport=httpx.MockTransport(lambda request: httpx.Response(302, headers={'location': 'http://localhost/secrets'})), resolve=resolve)
    gateway = WebCapabilityAdapter(providers=[PublicNewsProvider(reader=reader, interval_seconds=0)], resolve=resolve)
    result = await gateway.execute(CapabilityIntent(capability='web', action='search', arguments={'query': 'software'}), context())
    assert not result.ok


@pytest.mark.asyncio
async def test_public_discovery_denies_write_capabilities(monkeypatch):
    from app.autonomy.discovery import build_discovery_gateway
    from app.config import settings
    monkeypatch.setattr(settings, 'public_news_search_enabled', True)
    gateway = build_discovery_gateway()
    assert not gateway.declaration('web').external_effect
    from app.capabilities.policy import CapabilityDenied
    with pytest.raises(CapabilityDenied):
        await gateway.execute(CapabilityIntent(capability='workspace', action='write'), context())


def test_public_discovery_honors_web_disable(monkeypatch):
    from app.autonomy.discovery import build_discovery_gateway
    from app.config import settings
    monkeypatch.setattr(settings, 'public_news_search_enabled', True)
    monkeypatch.setattr(settings, 'web_capability_enabled', False)
    # An absent adapter has a fail-closed declaration (external + at-most-once).
    assert build_discovery_gateway().declaration('web').external_effect
