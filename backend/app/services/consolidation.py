from __future__ import annotations

import uuid

from sqlalchemy.exc import IntegrityError

from app.core.consolidation import ConsolidationError, ConsolidationIssue, build_consolidation
from app.core.domain import require_malkuth_authorized
from app.models.consolidation import MissionConsolidation
from app.repositories.consolidation import ConsolidationRepository
from app.services.domain import NotFoundError


class ConsolidationService:
    def __init__(self, repository: ConsolidationRepository) -> None:
        self.repository = repository

    async def consolidate(
        self,
        mission_id: str,
        *,
        correlation_id: str | None = None,
        actor_id: str = "system",
        actor_role: str = "system",
        causation_id: str | None = None,
    ) -> tuple[MissionConsolidation, bool]:
        correlation_id = correlation_id or str(uuid.uuid4())
        mission = await self.repository.mission(mission_id, lock=True)
        if mission is None:
            await self.repository.rollback()
            raise NotFoundError("Mission not found")

        existing = await self.repository.consolidation(mission_id)
        if existing is not None:
            await self.repository.commit()
            return existing, False

        # Only gates *new* consolidation attempts. An idempotent repeat for a mission that
        # already consolidated (and has since moved on to DISTRIBUTED/EXECUTING/MANIFESTED
        # via the tail chain) is handled by the existing-record return above; this guard
        # only needs to stop FAILED/CANCELLED missions from starting fresh work.
        require_malkuth_authorized(mission.status)

        try:
            tasks = await self.repository.tasks(mission_id)
            task_ids = {item.id for item in tasks}
            dependencies = await self.repository.dependencies(task_ids)
            dispatch_items = await self.repository.dispatch_items(mission_id, task_ids)
            dispatch_ids = {item.id for item in dispatch_items}
            executions = await self.repository.executions(mission_id, task_ids, dispatch_ids)
            document = build_consolidation(mission, tasks, dependencies, dispatch_items, executions)
            item = MissionConsolidation(
                mission_id=mission.id,
                status=document.status,
                payload_json=document.payload,
                inconsistencies_json=document.inconsistencies,
                completeness_json=document.completeness,
                fingerprint=document.fingerprint,
            )
            await self.repository.add(item)
            await self.repository.add_event(
                "mission_consolidated", mission.id, actor_id, actor_role, correlation_id,
                {"consolidation_id": item.id, "fingerprint": item.fingerprint}, causation_id=causation_id,
            )
            await self.repository.commit()
            return item, True
        except ConsolidationError:
            await self.repository.rollback()
            raise
        except IntegrityError as exc:
            await self.repository.rollback()
            existing = await self.repository.consolidation(mission_id)
            if existing is not None:
                return existing, False
            raise ConsolidationError(
                [
                    ConsolidationIssue(
                        "consolidation_persistence_conflict",
                        "mission",
                        mission_id,
                        "Consolidation could not be persisted atomically",
                    )
                ]
            ) from exc
        except Exception:
            await self.repository.rollback()
            raise

    async def get(self, mission_id: str) -> MissionConsolidation:
        item = await self.repository.consolidation(mission_id)
        if item is None:
            raise NotFoundError("Mission consolidation not found")
        return item
