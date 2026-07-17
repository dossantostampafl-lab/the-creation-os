from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class TrinityOrchestrationResponse(BaseModel):
    god_interaction_id: str
    conversation_id: str
    interaction_type: str
    sophia_understanding_id: str
    rockmam_assessment_id: str
    assessment_result: str
    understanding_created: bool
    assessment_created: bool
    god_consolidated_result: dict[str, Any]
