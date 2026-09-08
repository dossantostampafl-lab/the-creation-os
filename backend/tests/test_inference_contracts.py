from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.inference.contracts import InferenceRequest, ModelRequirements


def test_inference_request_requires_messages() -> None:
    with pytest.raises(ValidationError):
        InferenceRequest(messages=[])


def test_model_requirements_reject_invalid_token_limit() -> None:
    with pytest.raises(ValidationError):
        ModelRequirements(max_output_tokens=0)
