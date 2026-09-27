from __future__ import annotations

from app.admin import seed

EXPECTED = (
    ("knowledge", "Conhecimento", "10000000-0000-0000-0000-000000000001"),
    ("engineering", "Engenharia", "10000000-0000-0000-0000-000000000002"),
    ("security", "Segurança", "10000000-0000-0000-0000-000000000003"),
    ("vision", "Visão", "10000000-0000-0000-0000-000000000004"),
    ("design", "Design", "10000000-0000-0000-0000-000000000005"),
    ("business", "Negócios", "10000000-0000-0000-0000-000000000006"),
    ("marketing", "Marketing", "10000000-0000-0000-0000-000000000007"),
    ("legal", "Jurídico", "10000000-0000-0000-0000-000000000008"),
    ("finance", "Finanças", "10000000-0000-0000-0000-000000000009"),
    ("automation", "Automação", "10000000-0000-0000-0000-000000000010"),
    ("communication", "Comunicação", "10000000-0000-0000-0000-000000000011"),
    ("evolution", "Evolução", "10000000-0000-0000-0000-000000000012"),
)


def test_seed_exposes_exact_canonical_universe_catalog() -> None:
    actual = tuple((item.code, item.name, item.id) for item in seed.CANONICAL_UNIVERSES)
    assert actual == EXPECTED


def test_every_canonical_universe_has_minimal_active_agent_defaults() -> None:
    assert len(seed.CANONICAL_UNIVERSES) == 12
    assert len({item.code for item in seed.CANONICAL_UNIVERSES}) == 12
    assert len({item.id for item in seed.CANONICAL_UNIVERSES}) == 12

    for item in seed.CANONICAL_UNIVERSES:
        assert item.active is True
        assert item.agent_code == f"{item.code}-agent"
        assert item.agent_name
        assert item.description
        assert item.capabilities["inference_provider"]


def test_seed_identity_is_deterministic_across_repeated_catalog_reads() -> None:
    first = tuple((item.id, item.code, item.agent_code) for item in seed.CANONICAL_UNIVERSES)
    second = tuple((item.id, item.code, item.agent_code) for item in seed.CANONICAL_UNIVERSES)
    assert first == second
