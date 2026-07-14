from __future__ import annotations

from sqlalchemy.exc import IntegrityError

from app.core.consolidation import ConsolidationError, ConsolidationIssue, build_consolidation
from app.models.consolidation import MissionConsolidation
from app.repositories.consolidation import ConsolidationRepository
from app.services.domain import NotFoundError


class ConsolidationService:
    def __init__(self, repository: ConsolidationRepository) -> None:
        self.repository = repository

    async def consolidate(self, mission_id: str) -> tuple[MissionConsolidation, bool]:
        mission = await self.repository.mission(mission_id, lock=True)
        if mission is None:
            await self.repository.rollback()
            raise NotFoundError("Mission not found")

        existing = await self.repository.consolidation(mission_id)
        if existing is not None:
            await self.repository.commit()
            return existing, False

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
