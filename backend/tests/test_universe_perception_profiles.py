from __future__ import annotations

from app.admin.seed import CANONICAL_UNIVERSES, canonical_perception_profile


def test_every_canonical_universe_has_perception_priors_not_acl() -> None:
    assert len(CANONICAL_UNIVERSES) == 12
    for universe in CANONICAL_UNIVERSES:
        profile = canonical_perception_profile(universe.code)
        assert profile["preferred_sensors"]
        assert profile["detector_weights"]
        assert profile["exploration_strategy"]["mode"] == "cross_sector"
        assert profile["exploration_strategy"]["priors_are_permissions"] is False
        assert "allowed_capabilities" not in profile
        assert "denied_capabilities" not in profile
        capabilities = universe.capabilities
        assert capabilities["preferred_sensors"] == profile["preferred_sensors"]
        assert capabilities["detector_weights"] == profile["detector_weights"]


def test_profiles_bias_attention_without_binding_universe_to_sector() -> None:
    engineering = canonical_perception_profile("engineering")
    business = canonical_perception_profile("business")
    legal = canonical_perception_profile("legal")
    evolution = canonical_perception_profile("evolution")

    assert "web.search" in engineering["preferred_sensors"]
    assert "web.search" in business["preferred_sensors"]
    assert "web.search" in legal["preferred_sensors"]
    assert evolution["exploration_strategy"]["mode"] == "cross_sector"

    # There is deliberately no deny-list: Mission authorization, not the prior, decides
    # whether Engineering may inspect commerce or Business may inspect code/GitHub.
    for profile in (engineering, business, legal, evolution):
        assert not any(key.startswith("deny") for key in profile)
