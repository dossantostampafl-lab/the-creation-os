from __future__ import annotations

from pydantic import BaseModel, Field


class VoiceSynthesisRequest(BaseModel):
    # Hard ceiling against oversized payloads; VOICE_SYNTHESIS_MAX_CHARS is enforced by the service.
    text: str = Field(..., min_length=1, max_length=20_000)
