from app.inference.contracts import (
    InferenceRequest,
    InferenceResponse,
    ModelRequirements,
    ProviderHealth,
    ProviderUnavailable,
)
from app.inference.openai_provider import OpenAIResponsesProvider
from app.inference.provider import InferenceProvider
from app.inference.registry import ProviderRegistry
from app.inference.router import ModelRouter

def build_model_router() -> ModelRouter:
    from app.inference.bootstrap import build_model_router as _build_model_router

    return _build_model_router()


__all__ = [
    "InferenceProvider",
    "InferenceRequest",
    "InferenceResponse",
    "ModelRequirements",
    "ModelRouter",
    "OpenAIResponsesProvider",
    "ProviderHealth",
    "ProviderRegistry",
    "ProviderUnavailable",
    "build_model_router",
]
