from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import StrEnum
from typing import Any, cast

from app.config import settings
from app.core.domain import Actor, DomainError, require_creator
from app.models.perception import CreatorNotification, PerceptionRun, PerceptionSource
from app.repositories.automation import AutomationRepository
from app.repositories.capabilities import CapabilityRepository
from app.repositories.opportunities import OpportunityRepository
from app.repositories.perception import PerceptionRepository
from app.services.automation import AutomationService
from app.services.capability_governance import CapabilityGovernanceService
from app.services.opportunities import OBSERVATION_DUPLICATE, OBSERVATION_INVALID, OpportunityDiscoveryService


class PerceptionError(DomainError):
    pass


class PERCEPTION_SOURCE_NOT_FOUND(PerceptionError):
    pass


class PERCEPTION_SOURCE_DISABLED(PerceptionError):
    pass


class PERCEPTION_SOURCE_ALREADY_RUNNING(PerceptionError):
    pass


class PERCEPTION_SOURCE_RATE_LIMITED(PerceptionError):
    pass


class PERCEPTION_SOURCE_SUSPENDED(PerceptionError):
    pass


class PERCEPTION_PROVIDER_UNAVAILABLE(PerceptionError):
    pass


class PERCEPTION_RESPONSE_INVALID(PerceptionError):
    pass


class PERCEPTION_PERMISSION_DENIED(PerceptionError):
    pass


class PERCEPTION_COLLECTION_FAILED(PerceptionError):
    pass


class NOTIFICATION_NOT_FOUND(PerceptionError):
    pass


class NOTIFICATION_PERMISSION_DENIED(PerceptionError):
    pass


class NOTIFICATION_INVALID_TRANSITION(PerceptionError):
    pass


class NotificationStatus(StrEnum):
    UNREAD = "unread"
    READ = "read"
    ACKNOWLEDGED = "acknowledged"
    DISMISSED = "dismissed"


@dataclass(frozen=True)
class CollectionResult:
    source: PerceptionSource
    run: PerceptionRun
    observations_count: int
    opportunities_count: int
    notifications_count: int


class PerceptionService:
    def __init__(
        self,
        repository: PerceptionRepository,
        *,
        automation: AutomationService | None = None,
        discovery: OpportunityDiscoveryService | None = None,
        governance: CapabilityGovernanceService | None = None,
    ) -> None:
        self.repository = repository
        self.automation = automation or AutomationService(AutomationRepository(repository.session))
        self.discovery = discovery or OpportunityDiscoveryService(OpportunityRepository(repository.session))
        self.governance = governance or CapabilityGovernanceService(CapabilityRepository(repository.session))

    async def list_sources(self, actor: Actor, universe: str | None, correlation_id: str) -> list[PerceptionSource]:
        require_creator(actor, "list perception sources")
        await self._authorize(actor, "perception_source_list", correlation_id)
        await self._ensure_default_sources(actor, correlation_id)
        return await self.repository.sources(universe=universe)

    async def enable_source(self, actor: Actor, source_id: str, correlation_id: str) -> PerceptionSource:
        require_creator(actor, "enable perception source")
        await self._authorize(actor, "perception_source_enable", correlation_id)
        item = await self.repository.source(source_id, lock=True)
        if item is None:
            raise PERCEPTION_SOURCE_NOT_FOUND("Perception source not found")
        item.enabled = True
        item.next_run_at = datetime.now(timezone.utc)
        await self.repository.add_event("perception.source.enabled", "perception_source", item.id, actor.id, actor.role, correlation_id, {"source": item.name})
        await self.repository.commit()
        return item

    async def disable_source(self, actor: Actor, source_id: str, correlation_id: str) -> PerceptionSource:
        require_creator(actor, "disable perception source")
        await self._authorize(actor, "perception_source_disable", correlation_id)
        item = await self.repository.source(source_id, lock=True)
        if item is None:
            raise PERCEPTION_SOURCE_NOT_FOUND("Perception source not found")
        item.enabled = False
        await self.repository.add_event("perception.source.disabled", "perception_source", item.id, actor.id, actor.role, correlation_id, {"source": item.name})
        await self.repository.commit()
        return item

    async def source_runs(self, actor: Actor, source_id: str, limit: int) -> list[PerceptionRun]:
        require_creator(actor, "view perception runs")
        if await self.repository.source(source_id) is None:
            raise PERCEPTION_SOURCE_NOT_FOUND("Perception source not found")
        return await self.repository.runs(source_id, limit=limit)

    async def run_source(self, actor: Actor, source_id: str, correlation_id: str, *, force: bool = False) -> CollectionResult:
        require_creator(actor, "run perception source")
        await self._authorize(actor, "perception_source_collect", correlation_id)
        source = await self.repository.source(source_id, lock=True)
        if source is None:
            raise PERCEPTION_SOURCE_NOT_FOUND("Perception source not found")
        if not source.enabled:
            await self._audit_denied(actor, source, correlation_id, "PERCEPTION_SOURCE_DISABLED")
            raise PERCEPTION_SOURCE_DISABLED("Perception source is disabled")
        now = datetime.now(timezone.utc)
        if await self.repository.active_run(source.id):
            await self._audit_denied(actor, source, correlation_id, "PERCEPTION_SOURCE_ALREADY_RUNNING")
            raise PERCEPTION_SOURCE_ALREADY_RUNNING("Perception source is already running")
        if self._is_suspended(source, now):
            await self.repository.add_event("perception.collection.skipped", "perception_source", source.id, actor.id, actor.role, correlation_id, {"reason": "suspended"})
            await self.repository.commit()
            raise PERCEPTION_SOURCE_SUSPENDED("Perception source is suspended")
        if not force and source.last_started_at is not None and now - self._aware(source.last_started_at) < timedelta(seconds=source.minimum_interval_seconds):
            await self.repository.add_event("perception.collection.skipped", "perception_source", source.id, actor.id, actor.role, correlation_id, {"reason": "rate_limited"})
            await self.repository.commit()
            raise PERCEPTION_SOURCE_RATE_LIMITED("Perception source minimum interval has not elapsed")

        source.last_started_at = now
        run = await self.repository.add_run(PerceptionRun(source_id=source.id, status="running", started_at=now, metadata_json={"correlation_id": correlation_id}))
        await self.repository.add_event("perception.collection.started", "perception_source", source.id, actor.id, actor.role, correlation_id, {"source": source.name, "provider": source.provider})
        await self.repository.commit()

        try:
            observations, attempts = await self._collect_with_retry(actor, source, correlation_id)
            persisted = 0
            for payload in observations:
                try:
                    normalized = self._normalize_payload(source, payload)
                    await self.repository.add_event("observation.normalized", "perception_source", source.id, actor.id, actor.role, correlation_id, {"source": source.name, "subject": normalized["subject"], "event_type": normalized["event_type"]})
                    await self.discovery._ingest_without_commit(actor, normalized, correlation_id)
                    persisted += 1
                except OBSERVATION_DUPLICATE:
                    await self.repository.add_event("observation.duplicate_ignored", "perception_source", source.id, actor.id, actor.role, correlation_id, {"source": source.name})
                except OBSERVATION_INVALID as exc:
                    await self.repository.add_event("observation.rejected", "perception_source", source.id, actor.id, actor.role, correlation_id, {"source": source.name, "reason": exc.__class__.__name__})
            opportunities = []
            if persisted:
                await self._authorize(actor, "run_discovery", correlation_id)
                await self.repository.add_event("opportunity.discovery.triggered", "perception_source", source.id, actor.id, actor.role, correlation_id, {"observation_count": persisted})
                opportunities = await self.discovery.detect(actor, correlation_id)
                await self.repository.add_event("opportunity.ranking.updated", "perception_source", source.id, actor.id, actor.role, correlation_id, {"opportunity_count": len(opportunities)})
            notifications = await self._notify_creator(actor, correlation_id)
            await self._finish_success(source, run, attempts, persisted, len(opportunities), correlation_id, actor, notifications)
            return CollectionResult(source, run, persisted, len(opportunities), notifications)
        except PerceptionError as exc:
            await self._finish_failure(source, run, actor, correlation_id, exc.__class__.__name__, str(exc))
            raise

    async def run_due_sources(self, actor: Actor, correlation_id: str) -> list[CollectionResult]:
        require_creator(actor, "run due perception sources")
        await self._authorize(actor, "perception_scheduler_run", correlation_id)
        await self._ensure_default_sources(actor, correlation_id)
        results = []
        for source in await self.repository.due_sources(datetime.now(timezone.utc)):
            try:
                results.append(await self.run_source(actor, source.id, correlation_id, force=True))
            except PerceptionError:
                continue
        return results

    async def list_notifications(self, actor: Actor, status: str | None, limit: int, offset: int, correlation_id: str) -> list[CreatorNotification]:
        require_creator(actor, "list notifications")
        await self._authorize(actor, "perception_notification_list", correlation_id)
        return await self.repository.notifications(actor.id, status=status, limit=limit, offset=offset)

    async def mark_notification_read(self, actor: Actor, notification_id: str, correlation_id: str) -> CreatorNotification:
        return await self._transition_notification(actor, notification_id, NotificationStatus.READ, correlation_id)

    async def acknowledge_notification(self, actor: Actor, notification_id: str, correlation_id: str) -> CreatorNotification:
        return await self._transition_notification(actor, notification_id, NotificationStatus.ACKNOWLEDGED, correlation_id)

    async def _transition_notification(self, actor: Actor, notification_id: str, target: NotificationStatus, correlation_id: str) -> CreatorNotification:
        require_creator(actor, "update notification")
        await self._authorize(actor, "perception_notification_update", correlation_id)
        item = await self.repository.notification(notification_id, lock=True)
        if item is None:
            raise NOTIFICATION_NOT_FOUND("Notification not found")
        if item.recipient_actor_id != actor.id:
            raise NOTIFICATION_PERMISSION_DENIED("Notification belongs to another actor")
        if item.status == NotificationStatus.ACKNOWLEDGED.value:
            raise NOTIFICATION_INVALID_TRANSITION("Notification is already acknowledged")
        previous = item.status
        now = datetime.now(timezone.utc)
        if target is NotificationStatus.READ:
            item.status = NotificationStatus.READ.value
            item.read_at = item.read_at or now
            event_type = "creator.notification.read"
        else:
            item.status = NotificationStatus.ACKNOWLEDGED.value
            item.acknowledged_at = now
            item.read_at = item.read_at or now
            event_type = "creator.notification.acknowledged"
        await self.repository.add_event(event_type, "creator_notification", item.id, actor.id, actor.role, correlation_id, {"previous_status": previous, "new_status": item.status})
        await self.repository.commit()
        return item

    async def _collect_with_retry(self, actor: Actor, source: PerceptionSource, correlation_id: str) -> tuple[list[dict[str, Any]], int]:
        attempts = 0
        last_error: str | None = None
        for attempt in range(settings.perception_max_retries + 1):
            attempts = attempt + 1
            try:
                return await self._collect_once(actor, source, correlation_id, attempts), attempts
            except PERCEPTION_RESPONSE_INVALID as exc:
                raise exc
            except PerceptionError as exc:
                last_error = str(exc)
                if attempt >= settings.perception_max_retries:
                    break
        raise PERCEPTION_COLLECTION_FAILED(last_error or "Collection failed")

    async def _collect_once(self, actor: Actor, source: PerceptionSource, correlation_id: str, attempt: int) -> list[dict[str, Any]]:
        if source.provider.startswith("fixture_"):
            execution, _ = await self.automation.execute(
                actor,
                connector_id="opportunity",
                capability="collect_observations",
                payload={"source": source.name, "provider": source.provider},
                timeout_seconds=5,
                idempotency_key=f"perception-fixture:{source.id}:{correlation_id}:{attempt}",
                correlation_id=correlation_id,
            )
            return list((execution.result_payload or {}).get("observations", []))
        url = self._source_url(source)
        execution, _ = await self.automation.execute(
            actor,
            connector_id=source.connector_name,
            capability=source.capability_name,
            payload={"method": "GET", "url": url, "headers": {"accept": "application/json", "user-agent": "the-creation-os-perception"}},
            timeout_seconds=float(settings.perception_request_timeout_seconds),
            idempotency_key=f"perception:{source.id}:{correlation_id}:{attempt}",
            correlation_id=correlation_id,
        )
        if execution.status != "succeeded":
            raise PERCEPTION_PROVIDER_UNAVAILABLE(execution.error_code or "provider unavailable")
        payload = execution.result_payload or {}
        headers = cast(dict[str, str], payload.get("headers") if isinstance(payload.get("headers"), dict) else {})
        source.last_etag = headers.get("etag") or source.last_etag
        source.last_modified = headers.get("last-modified") or source.last_modified
        try:
            body = json.loads(str(payload.get("body_preview") or ""))
        except json.JSONDecodeError as exc:
            raise PERCEPTION_RESPONSE_INVALID("Provider returned invalid JSON") from exc
        if source.provider == "yahoo_finance_chart":
            return self._normalize_yahoo_response(source, body)
        if source.provider == "github_releases":
            return self._normalize_github_releases(source, body)
        raise PERCEPTION_PROVIDER_UNAVAILABLE("Unknown perception provider")

    def _source_url(self, source: PerceptionSource) -> str:
        config = source.config_json or {}
        if source.provider == "yahoo_finance_chart":
            symbol = str(config.get("symbols", ["AAPL"])[0]).strip().upper()
            return f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range=1d&interval=1m"
        if source.provider == "github_releases":
            repo = str(config.get("repositories", ["openai/openai-python"])[0]).strip()
            return f"https://api.github.com/repos/{repo}/releases?per_page=5"
        raise PERCEPTION_PROVIDER_UNAVAILABLE("Unknown perception provider")

    def _normalize_yahoo_response(self, source: PerceptionSource, body: dict[str, Any]) -> list[dict[str, Any]]:
        try:
            result = body["chart"]["result"][0]
            meta = result["meta"]
            timestamps = result.get("timestamp") or []
            quote = result["indicators"]["quote"][0]
            closes = [item for item in quote.get("close", []) if item is not None]
            volumes = [item for item in quote.get("volume", []) if item is not None]
        except (KeyError, IndexError, TypeError) as exc:
            raise PERCEPTION_RESPONSE_INVALID("Yahoo Finance response schema is invalid") from exc
        if not closes or not timestamps:
            raise PERCEPTION_RESPONSE_INVALID("Yahoo Finance response has no usable market data")
        symbol = str(meta.get("symbol") or source.config_json.get("symbols", ["unknown"])[0]).upper()
        latest = float(closes[-1])
        previous = float(meta.get("chartPreviousClose") or closes[0] or latest)
        percent_change = ((latest - previous) / previous) * 100 if previous else 0.0
        volume = int(volumes[-1]) if volumes else 0
        average_volume = (sum(volumes) / len(volumes)) if volumes else 0
        observed_at = datetime.fromtimestamp(int(timestamps[-1]), tz=timezone.utc).isoformat()
        events = [
            {
                "universe": "finance",
                "source": source.name,
                "subject": symbol,
                "event_type": "market_snapshot",
                "title": f"{symbol} market snapshot",
                "summary": f"{symbol} reported an informational market snapshot.",
                "observed_at": observed_at,
                "normalized_data": {"price": latest, "percent_change": percent_change, "volume": volume, "currency": meta.get("currency")},
                "evidence": {"provider": source.provider, "financial_execution": False},
                "source_reliability": 0.78,
                "correlation_key": f"{symbol.lower()}:market",
                "external_id": f"{symbol}:{timestamps[-1]}:market_snapshot",
            }
        ]
        if abs(percent_change) >= 2.0:
            events.append({**events[0], "event_type": "price_change", "title": f"{symbol} price change", "summary": f"{symbol} moved {percent_change:.2f}% in the configured informational window.", "external_id": f"{symbol}:{timestamps[-1]}:price_change"})
        if average_volume and volume >= average_volume * 2:
            events.append({**events[0], "event_type": "abnormal_volume", "title": f"{symbol} abnormal volume", "summary": f"{symbol} volume exceeded the deterministic abnormal-volume threshold.", "external_id": f"{symbol}:{timestamps[-1]}:abnormal_volume"})
        return events

    def _normalize_github_releases(self, source: PerceptionSource, body: Any) -> list[dict[str, Any]]:
        if not isinstance(body, list):
            raise PERCEPTION_RESPONSE_INVALID("GitHub releases response schema is invalid")
        events = []
        for item in body[:5]:
            if not isinstance(item, dict):
                continue
            tag = str(item.get("tag_name") or item.get("id") or "").strip()
            if not tag:
                continue
            repo = str((source.config_json or {}).get("repositories", ["unknown/repo"])[0])
            observed_at = item.get("published_at") or item.get("created_at") or datetime.now(timezone.utc).isoformat()
            events.append(
                {
                    "universe": "technology",
                    "source": source.name,
                    "subject": repo,
                    "event_type": "technology_release",
                    "title": str(item.get("name") or f"{repo} {tag}")[:256],
                    "summary": (str(item.get("body") or "Release activity detected from an authorized public source.")[:500]),
                    "observed_at": observed_at,
                    "normalized_data": {"tag": tag, "url": item.get("html_url"), "author": (item.get("author") or {}).get("login")},
                    "evidence": {"provider": source.provider, "url": item.get("html_url")},
                    "source_reliability": 0.76,
                    "correlation_key": f"{repo.lower()}:release",
                    "external_id": f"{repo}:{tag}",
                }
            )
        return events

    def _normalize_payload(self, source: PerceptionSource, payload: dict[str, Any]) -> dict[str, Any]:
        normalized = dict(payload)
        normalized["source"] = str(normalized.get("source") or source.name)
        normalized["universe"] = str(normalized.get("universe") or source.universe)
        return normalized

    async def _notify_creator(self, actor: Actor, correlation_id: str) -> int:
        now = datetime.now(timezone.utc)
        cooldown_since = now - timedelta(seconds=settings.opportunity_notification_cooldown_seconds)
        created = 0
        for opportunity in await self.repository.opportunities_for_notification():
            if opportunity.priority_score < settings.opportunity_notification_min_score:
                continue
            if opportunity.confidence < settings.opportunity_notification_min_confidence:
                continue
            if opportunity.risk > settings.opportunity_notification_max_risk:
                continue
            if opportunity.expires_at <= now:
                continue
            if await self.repository.recent_notification(actor.id, opportunity.id, cooldown_since):
                continue
            notification = await self.repository.add_notification(
                CreatorNotification(
                    recipient_actor_id=actor.id,
                    type="opportunity",
                    title=f"Oportunidade: {opportunity.title}",
                    message=f"{opportunity.universe} score {opportunity.priority_score:.2f}; aguarda decisao do Criador.",
                    opportunity_id=opportunity.id,
                    priority_score=opportunity.priority_score,
                    status=NotificationStatus.UNREAD.value,
                )
            )
            await self.repository.add_event("creator.notification.created", "creator_notification", notification.id, actor.id, actor.role, correlation_id, {"opportunity_id": opportunity.id, "priority_score": opportunity.priority_score})
            created += 1
        return created

    async def _finish_success(
        self,
        source: PerceptionSource,
        run: PerceptionRun,
        attempts: int,
        observations_count: int,
        opportunities_count: int,
        correlation_id: str,
        actor: Actor,
        notifications_count: int,
    ) -> None:
        completed = datetime.now(timezone.utc)
        previous_failures = source.failure_count
        source.failure_count = 0
        source.last_succeeded_at = completed
        source.last_cursor = completed.isoformat()
        source.next_run_at = completed + timedelta(seconds=source.schedule_interval_seconds)
        run.status = "succeeded"
        run.completed_at = completed
        run.duration_ms = int((completed - self._aware(run.started_at)).total_seconds() * 1000)
        run.attempts_count = attempts
        run.observations_count = observations_count
        run.opportunities_count = opportunities_count
        run.metadata_json = {"notifications_count": notifications_count}
        await self.repository.add_event("perception.checkpoint.updated", "perception_source", source.id, actor.id, actor.role, correlation_id, {"last_cursor": source.last_cursor})
        await self.repository.add_event("perception.collection.succeeded", "perception_source", source.id, actor.id, actor.role, correlation_id, {"observations": observations_count, "opportunities": opportunities_count, "duration_ms": run.duration_ms})
        if previous_failures >= source.max_consecutive_failures:
            await self.repository.add_event("source.collection.resumed", "perception_source", source.id, actor.id, actor.role, correlation_id, {"source": source.name})
        await self.repository.commit()

    async def _finish_failure(self, source: PerceptionSource, run: PerceptionRun, actor: Actor, correlation_id: str, code: str, message: str) -> None:
        completed = datetime.now(timezone.utc)
        source.failure_count += 1
        source.last_failed_at = completed
        if source.failure_count >= source.max_consecutive_failures:
            source.next_run_at = completed + timedelta(seconds=settings.perception_suspend_seconds)
            await self.repository.add_event("source.collection.suspended", "perception_source", source.id, actor.id, actor.role, correlation_id, {"failure_count": source.failure_count})
        run.status = "failed"
        run.completed_at = completed
        run.duration_ms = int((completed - self._aware(run.started_at)).total_seconds() * 1000)
        run.error_code = code
        run.error_message = message[:2048]
        await self.repository.add_event("perception.collection.failed", "perception_source", source.id, actor.id, actor.role, correlation_id, {"code": code, "error": message[:256]})
        await self.repository.commit()

    async def _ensure_default_sources(self, actor: Actor, correlation_id: str) -> None:
        defaults: list[dict[str, Any]] = [
            {
                "name": "financial-public-market",
                "universe": "finance",
                "provider": "yahoo_finance_chart",
                "config_json": {"symbols": [item.strip().upper() for item in settings.perception_financial_symbols.split(",") if item.strip()] or ["AAPL"]},
            },
            {
                "name": "technology-public-releases",
                "universe": "technology",
                "provider": "github_releases",
                "config_json": {"repositories": [item.strip() for item in settings.perception_technology_repositories.split(",") if item.strip()] or ["openai/openai-python"]},
            },
        ]
        changed = False
        for data in defaults:
            if await self.repository.source_by_name(data["name"]) is not None:
                continue
            source = await self.repository.add_source(
                PerceptionSource(
                    name=data["name"],
                    universe=data["universe"],
                    provider=data["provider"],
                    capability_name="http_request",
                    connector_name="restricted_rest",
                    enabled=False,
                    schedule_interval_seconds=settings.perception_default_interval_seconds,
                    minimum_interval_seconds=settings.perception_min_interval_seconds,
                    max_consecutive_failures=settings.perception_failure_threshold,
                    config_json=data["config_json"],
                )
            )
            await self.repository.add_event("perception.source.created", "perception_source", source.id, actor.id, actor.role, correlation_id, {"source": source.name, "provider": source.provider})
            changed = True
        if changed:
            await self.repository.commit()

    async def _authorize(self, actor: Actor, connector_capability: str, correlation_id: str) -> None:
        await self.governance.authorize_execution(actor, connector_id="opportunity", connector_capability=connector_capability, correlation_id=correlation_id)

    async def _audit_denied(self, actor: Actor, source: PerceptionSource, correlation_id: str, code: str) -> None:
        await self.repository.add_event("opportunity.execution.denied", "perception_source", source.id, actor.id, actor.role, correlation_id, {"code": code, "source": source.name})
        await self.repository.commit()

    def _is_suspended(self, source: PerceptionSource, now: datetime) -> bool:
        return source.failure_count >= source.max_consecutive_failures and source.next_run_at is not None and self._aware(source.next_run_at) > now

    def _aware(self, value: datetime) -> datetime:
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
