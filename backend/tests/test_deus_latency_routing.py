from __future__ import annotations

import pytest

from app.services.deus import needs_trinity


@pytest.mark.parametrize(
    "content",
    [
        "continue",
        "prossiga",
        "mostre",
        "verifique",
        "repita",
        "abra",
        "feche",
        "corrija esse erro",
        "continue o projeto",
        "melhore isso",
        "corrija o fluxo da conversa",
        "resuma o que falamos",
    ],
)
def test_bounded_contextual_actions_skip_trinity(content: str) -> None:
    assert needs_trinity(content) is False


@pytest.mark.parametrize(
    "content",
    [
        "implemente um novo sistema",
        "crie um universo",
        "publique em produção",
        "deploy agora",
        "altere a governança",
        "configure segurança",
        "automatize pagamentos",
        "autoriza",
        "cancela a missão",
        "continue o deploy",
        "melhore o backend",
        "corrija o código",
    ],
)
def test_sensitive_or_substantial_actions_keep_trinity(content: str) -> None:
    assert needs_trinity(content) is True
