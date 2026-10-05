"""Free public-news search; bounded GETs through the existing public-web guard."""
from __future__ import annotations

import asyncio
from copy import deepcopy
from time import monotonic
from typing import Any
from urllib.parse import urlencode, urlsplit
from xml.etree import ElementTree

from app.capabilities.contracts import CapabilityContext, CapabilityIntent
from app.capabilities.web import WebCapabilityAdapter
from app.capabilities.web_providers import ProviderUnavailable, WebProviderMetadata


class PublicNewsProvider:
    name = 'public-news'
    actions = frozenset({'search'})
    metadata = WebProviderMetadata(
        origin='public:news.google.com/rss', license='linked-public-news-metadata',
        security_review='approved', supported_actions=actions, production_enabled=True,
    )

    def __init__(self, *, reader: WebCapabilityAdapter | None = None,
                 interval_seconds: float = 1.0) -> None:
        self.reader = reader or WebCapabilityAdapter(timeout_seconds=10, max_bytes=500000)
        self.interval_seconds = interval_seconds
        self._lock = asyncio.Lock()
        self._last_request = 0.0
        self._cache: dict[str, tuple[float, dict[str, Any] | None]] = {}

    async def execute(self, intent: CapabilityIntent, context: CapabilityContext) -> dict[str, Any]:
        query = intent.arguments.get('query')
        if intent.action != 'search' or not isinstance(query, str) or not 1 <= len(query.strip()) <= 256:
            raise ProviderUnavailable('public news requires a bounded search query')
        query = query.strip()
        # Always check source authority, including cache hits under another mission.
        allowed = WebCapabilityAdapter._allowed_hosts(context)
        if allowed is not None and 'news.google.com' not in allowed:
            raise ProviderUnavailable('public news source not authorized')
        url = 'https://news.google.com/rss/search?' + urlencode(
            {'q': query, 'hl': 'pt-BR', 'gl': 'BR', 'ceid': 'BR:pt-419'})
        async with self._lock:
            cached = self._cache.get(query)
            if cached and monotonic() < cached[0]:
                if cached[1] is None:
                    raise ProviderUnavailable('public news is cooling down after failure')
                return deepcopy(cached[1])
            await asyncio.sleep(max(0, self.interval_seconds - (monotonic() - self._last_request)))
            self._last_request = monotonic()
            if len(self._cache) >= 128:
                self._cache.pop(next(iter(self._cache)))
            # Negative cache avoids retry storms on 429, invalid RSS or outages.
            self._cache[query] = (monotonic() + 600, None)
            result = await self.reader.execute(
                CapabilityIntent(capability='web', action='fetch', resource=url), context)
            if not result.ok or result.data.get('status') != 200 or result.data.get('truncated'):
                raise ProviderUnavailable('public news fetch unavailable')
            content = result.data.get('content', '')
            # Refuse DTD/entity input before parsing public, untrusted XML.
            if not isinstance(content, str) or '<!DOCTYPE' in content.upper() or '<!ENTITY' in content.upper():
                raise ProviderUnavailable('public news XML refused')
            try:
                root = ElementTree.fromstring(content)
            except ElementTree.ParseError as exc:
                raise ProviderUnavailable('public news XML invalid') from exc
            items = []
            for item in root.findall('./channel/item'):
                title = (item.findtext('title') or '').strip()[:512]
                link = (item.findtext('link') or '').strip()
                parts = urlsplit(link)
                if not title or len(link) > 4096 or parts.scheme != 'https' or parts.hostname != 'news.google.com' or parts.username or parts.password:
                    continue
                items.append({'title': title, 'url': link,
                              'published': (item.findtext('pubDate') or '')[:128]})
                if len(items) == 3:
                    break
            if not items:
                raise ProviderUnavailable('public news has no usable evidence')
            data: dict[str, Any] = {'items': items, 'url': url, 'query': query,
                                    'source': 'public-news', 'content_kind': 'untrusted_news_metadata'}
            self._cache[query] = (monotonic() + 600, data)
            return deepcopy(data)
