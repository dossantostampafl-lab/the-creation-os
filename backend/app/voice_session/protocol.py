from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ClientEvent(BaseModel):
    type: Literal["wake", "barge_in", "audio", "commit", "stop"]
    session_id: str = Field(..., min_length=1)
    turn_id: int = Field(..., ge=0)
    audio_base64: str | None = None
    commit: bool = False
    utterance_id: str | None = Field(None, min_length=1, max_length=128)


def parse_client_event(raw: str) -> ClientEvent:
    return ClientEvent.model_validate_json(raw)
