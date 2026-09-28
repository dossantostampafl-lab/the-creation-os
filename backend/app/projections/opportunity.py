from __future__ import annotations

from collections import Counter

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.entities import Universe
from app.models.opportunity import Opportunity, OpportunityLease, OpportunityThesis
from app.services.economy import project_universe_economy


async def build_creator_opportunity_projection(
    session: AsyncSession,
    *,
    creator_id: str,
    currency: str,
) -> dict:
    opportunities = list(
        (
            await session.scalars(
                select(Opportunity).where(Opportunity.creator_id == creator_id)
            )
        ).all()
    )
    opportunity_ids = [item.id for item in opportunities]

    theses: list[OpportunityThesis] = []
    leases: list[OpportunityLease] = []
    if opportunity_ids:
        theses = list(
            (
                await session.scalars(
                    select(OpportunityThesis).where(
                        OpportunityThesis.opportunity_id.in_(opportunity_ids)
                    )
                )
            ).all()
        )
        leases = list(
            (
                await session.scalars(
                    select(OpportunityLease).where(
                        OpportunityLease.opportunity_id.in_(opportunity_ids),
                        OpportunityLease.lease_type == "EXECUTIVE",
                        OpportunityLease.status == "ACTIVE",
                    )
                )
            ).all()
        )

    universes = list(
        (
            await session.scalars(
                select(Universe).where(Universe.active.is_(True)).order_by(Universe.code)
            )
        ).all()
    )
    economic = [
        (
            await project_universe_economy(
                session,
                creator_id=creator_id,
                universe_id=universe.id,
                currency=currency,
            )
        ).model_dump(mode="json")
        for universe in universes
    ]

    return {
        "creator_id": creator_id,
        "opportunities": {
            "total": len(opportunities),
            "by_status": dict(Counter(item.status for item in opportunities)),
        },
        "theses": {
            "total": len(theses),
            "by_status": dict(Counter(item.status for item in theses)),
        },
        "active_executive_leases": len(leases),
        "universe_economy": economic,
        "reconciliation_backlog": sum(int(item["reconciliation_backlog"]) for item in economic),
    }
