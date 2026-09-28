from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.economy import EconomicLedgerEntry
from app.models.entities import Creator, Mission, Universe
from app.models.opportunity import Opportunity
from app.repositories.domain import DomainRepository
from app.schemas.economy import UniverseEconomicProjection

SIMULATED_MODES = frozenset({"simulation", "simulated", "paper", "shadow"})
ACTIVE_ECONOMIC_STATUS = "ACTIVE"
SUSPENDED_ECONOMIC_STATUS = "ECONOMIC_SUSPENDED"
RECONCILIATION_REQUIRED = "RECONCILIATION_REQUIRED"


class EconomicPolicyError(RuntimeError):
    """A requested material economic action is outside the configured policy."""


def _money(value: Decimal | int | float | str) -> Decimal:
    return Decimal(str(value))


def _event_type(entry_type: str, status: str) -> str:
    kind = entry_type.upper()
    state = status.upper()
    if kind == "RESERVE" or state == "RESERVED":
        return "economic_reserved"
    if kind == "COMMIT" or state == "COMMITTED":
        return "economic_committed"
    if kind == "SETTLING" or state == "SETTLING":
        return "economic_settling"
    if kind == "UNKNOWN" or state == "UNKNOWN":
        return "economic_unknown"
    if kind == "RECONCILED" or state == "RECONCILED":
        return "economic_reconciled"
    return "economic_settled"


async def _validate_scope(
    repository: DomainRepository,
    *,
    creator_id: str,
    universe_id: str,
    mission_id: str | None,
    opportunity_id: str | None,
) -> None:
    # Lazy import avoids services.domain -> kernel -> capabilities.runtime -> services.economy
    # initialization cycle while preserving the domain-level not-found contract.
    from app.services.domain import NotFoundError

    creator = await repository.get(Creator, creator_id)
    if creator is None:
        raise NotFoundError("Creator not found")
    universe = await repository.get(Universe, universe_id)
    if universe is None:
        raise NotFoundError("Universe not found")

    if mission_id is not None:
        mission = await repository.get(Mission, mission_id)
        if mission is None or mission.creator_id != creator_id:
            raise NotFoundError("Mission not found")
        if opportunity_id is not None and mission.opportunity_id not in {None, opportunity_id}:
            raise NotFoundError("Opportunity not found for Mission")

    if opportunity_id is not None:
        opportunity = await repository.get(Opportunity, opportunity_id)
        if opportunity is None or opportunity.creator_id != creator_id:
            raise NotFoundError("Opportunity not found")


async def append_ledger_entry(
    repository: DomainRepository,
    *,
    creator_id: str,
    universe_id: str,
    mission_id: str | None,
    opportunity_id: str | None,
    entry_type: str,
    amount: Decimal,
    currency: str,
    status: str,
    external_reference: str | None,
    metadata: dict,
    correlation_id: str,
) -> EconomicLedgerEntry:
    await _validate_scope(
        repository,
        creator_id=creator_id,
        universe_id=universe_id,
        mission_id=mission_id,
        opportunity_id=opportunity_id,
    )
    normalized_type = entry_type.strip().upper()
    normalized_status = status.strip().upper()
    normalized_currency = currency.strip().upper()
    if not normalized_type or not normalized_status or not normalized_currency:
        raise ValueError("entry_type, status, and currency are required")

    if external_reference:
        existing = await repository.session.scalar(
            select(EconomicLedgerEntry).where(
                EconomicLedgerEntry.creator_id == creator_id,
                EconomicLedgerEntry.universe_id == universe_id,
                EconomicLedgerEntry.entry_type == normalized_type,
                EconomicLedgerEntry.external_reference == external_reference,
            )
        )
        if existing is not None:
            return existing

    settled_at = (
        datetime.now(timezone.utc)
        if normalized_status in {"SETTLED", "PROFIT", "LOSS", "RECONCILED"}
        or normalized_type in {"PROFIT", "LOSS", "RECONCILED"}
        else None
    )
    entry = EconomicLedgerEntry(
        creator_id=creator_id,
        universe_id=universe_id,
        mission_id=mission_id,
        opportunity_id=opportunity_id,
        entry_type=normalized_type,
        amount=_money(amount),
        currency=normalized_currency,
        status=normalized_status,
        external_reference=external_reference,
        metadata_json=dict(metadata),
        settled_at=settled_at,
    )
    try:
        entry = await repository.add(entry)
    except IntegrityError as exc:
        await repository.rollback()
        if external_reference and "uq_economic_ledger_external_transition" in str(exc):
            existing = await repository.session.scalar(
                select(EconomicLedgerEntry).where(
                    EconomicLedgerEntry.creator_id == creator_id,
                    EconomicLedgerEntry.universe_id == universe_id,
                    EconomicLedgerEntry.entry_type == normalized_type,
                    EconomicLedgerEntry.external_reference == external_reference,
                )
            )
            if existing is not None:
                return existing
        raise

    await repository.add_event(
        _event_type(normalized_type, normalized_status),
        "economic_ledger",
        entry.id,
        universe_id,
        "universe",
        correlation_id,
        {
            "entry_type": normalized_type,
            "status": normalized_status,
            "amount": str(entry.amount),
            "currency": normalized_currency,
            "mission_id": mission_id,
            "opportunity_id": opportunity_id,
            "external_reference": external_reference,
        },
    )
    await repository.commit()
    if normalized_type == "LOSS":
        await _ensure_suspension_if_required(
            repository,
            creator_id=creator_id,
            universe_id=universe_id,
            currency=normalized_currency,
            correlation_id=correlation_id,
        )
    return entry


async def project_universe_economy(
    session: AsyncSession,
    *,
    creator_id: str,
    universe_id: str,
    currency: str,
) -> UniverseEconomicProjection:
    normalized_currency = currency.strip().upper()
    rows = list(
        (
            await session.scalars(
                select(EconomicLedgerEntry)
                .where(
                    EconomicLedgerEntry.creator_id == creator_id,
                    EconomicLedgerEntry.universe_id == universe_id,
                    EconomicLedgerEntry.currency == normalized_currency,
                )
                .order_by(EconomicLedgerEntry.created_at, EconomicLedgerEntry.id)
            )
        ).all()
    )

    nav = Decimal("0")
    peak_nav = Decimal("0")
    reserved = Decimal("0")
    committed = Decimal("0")
    settling = Decimal("0")
    settled_pnl = Decimal("0")
    unresolved: set[str] = set()
    today_loss = Decimal("0")
    sticky_suspended = False
    today = datetime.now(timezone.utc).date()

    for row in rows:
        metadata = row.metadata_json or {}
        mode = str(metadata.get("mode", "real")).strip().lower()
        if mode in SIMULATED_MODES or metadata.get("real") is False:
            continue

        amount = abs(_money(row.amount))
        kind = row.entry_type.upper()
        if kind == "GENESIS":
            nav += amount
        elif kind == "RESERVE":
            reserved += amount
        elif kind in {"RELEASE", "RESERVATION_RELEASED"}:
            reserved = max(Decimal("0"), reserved - amount)
        elif kind == "COMMIT":
            reserved = max(Decimal("0"), reserved - amount)
            committed += amount
        elif kind == "SETTLING":
            committed = max(Decimal("0"), committed - amount)
            settling += amount
        elif kind in {"SETTLE", "SETTLED"}:
            settling = max(Decimal("0"), settling - amount)
        elif kind == "PROFIT":
            nav += amount
            settled_pnl += amount
        elif kind == "LOSS":
            nav -= amount
            settled_pnl -= amount
            if row.created_at.astimezone(timezone.utc).date() == today:
                today_loss += amount
        elif kind == "UNKNOWN":
            unresolved.add(row.external_reference or row.id)
        elif kind == "SUSPENSION":
            sticky_suspended = True
        elif kind == "RECONCILED":
            key = str(metadata.get("unknown_reference") or row.external_reference or "")
            if key:
                unresolved.discard(key)
            if bool(metadata.get("release_settling", True)):
                settling = max(Decimal("0"), settling - amount)

        if nav > peak_nav:
            peak_nav = nav

    available = nav - reserved - committed - settling
    drawdown = Decimal("0")
    if peak_nav > 0 and nav < peak_nav:
        drawdown = (peak_nav - nav) / peak_nav

    daily_loss_ratio = Decimal("0")
    if peak_nav > 0:
        daily_loss_ratio = today_loss / peak_nav

    if unresolved:
        economic_status = RECONCILIATION_REQUIRED
    elif sticky_suspended or (
        nav <= 0 and peak_nav > 0
        or drawdown >= _money(settings.economic_drawdown_stop_ratio)
        or daily_loss_ratio >= _money(settings.economic_daily_stop_ratio)
    ):
        economic_status = SUSPENDED_ECONOMIC_STATUS
    else:
        economic_status = ACTIVE_ECONOMIC_STATUS

    return UniverseEconomicProjection(
        creator_id=creator_id,
        universe_id=universe_id,
        currency=normalized_currency,
        available=available,
        reserved=reserved,
        committed=committed,
        settling=settling,
        settled_pnl=settled_pnl,
        nav=nav,
        drawdown=drawdown,
        economic_status=economic_status,
        reconciliation_backlog=len(unresolved),
    )


async def _ensure_suspension_if_required(
    repository: DomainRepository,
    *,
    creator_id: str,
    universe_id: str,
    currency: str,
    correlation_id: str,
) -> None:
    projection = await project_universe_economy(
        repository.session,
        creator_id=creator_id,
        universe_id=universe_id,
        currency=currency,
    )
    if projection.economic_status != SUSPENDED_ECONOMIC_STATUS:
        return

    reference = f"suspension:{creator_id}:{universe_id}:{currency}"
    existing = await repository.session.scalar(
        select(EconomicLedgerEntry).where(
            EconomicLedgerEntry.creator_id == creator_id,
            EconomicLedgerEntry.universe_id == universe_id,
            EconomicLedgerEntry.entry_type == "SUSPENSION",
            EconomicLedgerEntry.external_reference == reference,
        )
    )
    if existing is not None:
        return

    item = EconomicLedgerEntry(
        creator_id=creator_id,
        universe_id=universe_id,
        mission_id=None,
        opportunity_id=None,
        entry_type="SUSPENSION",
        amount=Decimal("0"),
        currency=currency,
        status=SUSPENDED_ECONOMIC_STATUS,
        external_reference=reference,
        metadata_json={
            "mode": "real",
            "nav": str(projection.nav),
            "drawdown": str(projection.drawdown),
            "automatic_recapitalization": False,
        },
    )
    try:
        item = await repository.add(item)
    except IntegrityError as exc:
        await repository.rollback()
        if "uq_economic_ledger_external_transition" in str(exc):
            return
        raise
    await repository.add_event(
        "universe_economic_suspended",
        "economic_ledger",
        item.id,
        universe_id,
        "universe",
        correlation_id,
        {
            "currency": currency,
            "nav": str(projection.nav),
            "drawdown": str(projection.drawdown),
        },
    )
    await repository.commit()


async def _economic_lock(repository: DomainRepository, *, creator_id: str, universe_id: str) -> None:
    if repository.session.bind is not None and repository.session.bind.dialect.name == "postgresql":
        await repository.session.execute(
            text("SELECT pg_advisory_xact_lock(hashtext(:economic_scope))"),
            {"economic_scope": f"{creator_id}:{universe_id}"},
        )


async def ensure_genesis_allocation(
    repository: DomainRepository,
    *,
    creator_id: str,
    universe_id: str,
    correlation_id: str,
    amount: Decimal | None = None,
    currency: str | None = None,
) -> EconomicLedgerEntry:
    if not settings.real_economic_mode_enabled:
        raise EconomicPolicyError("real economic mode is not enabled")
    await _economic_lock(repository, creator_id=creator_id, universe_id=universe_id)
    return await append_ledger_entry(
        repository,
        creator_id=creator_id,
        universe_id=universe_id,
        mission_id=None,
        opportunity_id=None,
        entry_type="GENESIS",
        amount=amount if amount is not None else _money(settings.economic_genesis_amount),
        currency=currency or settings.economic_currency,
        status="SETTLED",
        external_reference=f"genesis:{creator_id}:{universe_id}:{(currency or settings.economic_currency).upper()}",
        metadata={"mode": "real", "source": "GENESIS_FUND"},
        correlation_id=correlation_id,
    )


async def reserve_for_capability(
    repository: DomainRepository,
    *,
    creator_id: str,
    universe_id: str,
    mission_id: str,
    opportunity_id: str | None,
    amount: Decimal,
    currency: str,
    external_reference: str,
    metadata: dict[str, Any],
    correlation_id: str,
) -> EconomicLedgerEntry:
    if not settings.real_economic_mode_enabled:
        raise EconomicPolicyError("real economic mode is not enabled")
    requested = abs(_money(amount))
    if requested <= 0:
        raise EconomicPolicyError("economic reservation amount must be positive")

    await _economic_lock(repository, creator_id=creator_id, universe_id=universe_id)
    projection = await project_universe_economy(
        repository.session,
        creator_id=creator_id,
        universe_id=universe_id,
        currency=currency,
    )
    if projection.economic_status != ACTIVE_ECONOMIC_STATUS:
        raise EconomicPolicyError(f"Universe economic state is {projection.economic_status}")

    max_action = projection.nav * _money(settings.economic_max_risk_per_action_ratio)
    max_exposure = projection.nav * _money(settings.economic_max_exposure_ratio)
    max_operational = projection.nav * _money(settings.economic_max_operational_ratio)
    current_exposure = projection.reserved + projection.committed + projection.settling
    structural_floor = projection.nav * _money(settings.economic_structural_reserve_ratio)

    if requested > max_action:
        raise EconomicPolicyError("requested risk exceeds max risk per action")
    if current_exposure + requested > max_exposure:
        raise EconomicPolicyError("requested reservation exceeds max simultaneous exposure")
    if current_exposure + requested > max_operational:
        raise EconomicPolicyError("requested reservation exceeds max operational capital")
    if projection.available - requested < structural_floor:
        raise EconomicPolicyError("requested reservation would consume structural reserve")
    if requested > projection.available:
        raise EconomicPolicyError("insufficient available capital")

    return await append_ledger_entry(
        repository,
        creator_id=creator_id,
        universe_id=universe_id,
        mission_id=mission_id,
        opportunity_id=opportunity_id,
        entry_type="RESERVE",
        amount=requested,
        currency=currency,
        status="RESERVED",
        external_reference=external_reference,
        metadata={**metadata, "mode": "real"},
        correlation_id=correlation_id,
    )


async def mark_capability_committed(
    repository: DomainRepository,
    *,
    creator_id: str,
    universe_id: str,
    mission_id: str,
    opportunity_id: str | None,
    amount: Decimal,
    currency: str,
    external_reference: str,
    correlation_id: str,
) -> EconomicLedgerEntry:
    return await append_ledger_entry(
        repository,
        creator_id=creator_id,
        universe_id=universe_id,
        mission_id=mission_id,
        opportunity_id=opportunity_id,
        entry_type="COMMIT",
        amount=amount,
        currency=currency,
        status="COMMITTED",
        external_reference=external_reference,
        metadata={"mode": "real"},
        correlation_id=correlation_id,
    )


async def mark_capability_settling(
    repository: DomainRepository,
    *,
    creator_id: str,
    universe_id: str,
    mission_id: str,
    opportunity_id: str | None,
    amount: Decimal,
    currency: str,
    external_reference: str,
    correlation_id: str,
) -> EconomicLedgerEntry:
    return await append_ledger_entry(
        repository,
        creator_id=creator_id,
        universe_id=universe_id,
        mission_id=mission_id,
        opportunity_id=opportunity_id,
        entry_type="SETTLING",
        amount=amount,
        currency=currency,
        status="SETTLING",
        external_reference=external_reference,
        metadata={"mode": "real"},
        correlation_id=correlation_id,
    )


async def settle_capability_result(
    repository: DomainRepository,
    *,
    creator_id: str,
    universe_id: str,
    mission_id: str,
    opportunity_id: str | None,
    amount: Decimal,
    currency: str,
    external_reference: str,
    pnl: Decimal = Decimal("0"),
    correlation_id: str,
) -> list[EconomicLedgerEntry]:
    entries = [
        await append_ledger_entry(
            repository,
            creator_id=creator_id,
            universe_id=universe_id,
            mission_id=mission_id,
            opportunity_id=opportunity_id,
            entry_type="SETTLE",
            amount=amount,
            currency=currency,
            status="SETTLED",
            external_reference=external_reference,
            metadata={"mode": "real"},
            correlation_id=correlation_id,
        )
    ]
    realized = _money(pnl)
    if realized != 0:
        entries.append(
            await append_ledger_entry(
                repository,
                creator_id=creator_id,
                universe_id=universe_id,
                mission_id=mission_id,
                opportunity_id=opportunity_id,
                entry_type="PROFIT" if realized > 0 else "LOSS",
                amount=abs(realized),
                currency=currency,
                status="SETTLED",
                external_reference=external_reference,
                metadata={"mode": "real"},
                correlation_id=correlation_id,
            )
        )
    return entries


async def mark_capability_uncertain(
    repository: DomainRepository,
    *,
    creator_id: str,
    universe_id: str,
    mission_id: str,
    opportunity_id: str | None,
    amount: Decimal,
    currency: str,
    external_reference: str,
    correlation_id: str,
) -> EconomicLedgerEntry:
    return await append_ledger_entry(
        repository,
        creator_id=creator_id,
        universe_id=universe_id,
        mission_id=mission_id,
        opportunity_id=opportunity_id,
        entry_type="UNKNOWN",
        amount=amount,
        currency=currency,
        status="UNKNOWN",
        external_reference=external_reference,
        metadata={"mode": "real", "reconciliation_required": True},
        correlation_id=correlation_id,
    )


async def reconcile_capability(
    repository: DomainRepository,
    *,
    creator_id: str,
    universe_id: str,
    mission_id: str,
    opportunity_id: str | None,
    amount: Decimal,
    currency: str,
    external_reference: str,
    correlation_id: str,
) -> EconomicLedgerEntry:
    return await append_ledger_entry(
        repository,
        creator_id=creator_id,
        universe_id=universe_id,
        mission_id=mission_id,
        opportunity_id=opportunity_id,
        entry_type="RECONCILED",
        amount=amount,
        currency=currency,
        status="RECONCILED",
        external_reference=external_reference,
        metadata={"mode": "real", "unknown_reference": external_reference, "release_settling": True},
        correlation_id=correlation_id,
    )
