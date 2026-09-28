from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel


class UniverseEconomicProjection(BaseModel):
    creator_id: str
    universe_id: str
    currency: str
    available: Decimal
    reserved: Decimal
    committed: Decimal
    settling: Decimal
    settled_pnl: Decimal
    nav: Decimal
    drawdown: Decimal
    economic_status: str
    reconciliation_backlog: int = 0
