from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.living_core import actor
from app.config import settings
from app.core.domain import Actor
from app.inference.status import InferenceStatusSnapshot, configured_inference_status

router = APIRouter(tags=["inference-status"])


@router.get("/system/inference", response_model=InferenceStatusSnapshot)
async def get_inference_status(_: Actor = Depends(actor)) -> InferenceStatusSnapshot:
    return await configured_inference_status(settings.llm_provider)
