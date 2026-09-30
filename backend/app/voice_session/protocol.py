from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ClientEvent(BaseModel):
    type: Literal["wake", "barge_in", "audio", "commit", "stop"]
    session_id: str = Field(..., min_length=1)
    turn_id: int = Field(..., ge=0)


def parse_client_event(raw: str) -> ClientEvent:
    return ClientEvent.model_validate_json(raw)
