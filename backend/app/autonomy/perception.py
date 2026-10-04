from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from app.capabilities.contracts import (
    CapabilityContext,
    CapabilityIntent,
    IdempotencyClass,
    MissionAuthorization,
)
from app.capabilities.gateway import CapabilityGateway


class PerceptionPolicyError(RuntimeError):
    """A pre-Mission sensor would cross the read-only perception boundary."""


@dataclass(frozen=True)
class SensorBinding:
    capability: str
    action: str


@dataclass(frozen=True)
class PerceptionObservation:
    sensor: str
    capability: str
    action: str
    data: dict[str, Any]


class PerceptionFabric:
    """Run centrally governed read-only sensors for Universe perception cells.

    Universe profiles only determine ordering. Authority comes from the explicit
    allowed_sensors envelope supplied to this fabric.
    """

    def __init__(
        self,
        gateway: CapabilityGateway,
        *,
        bindings: dict[str, SensorBinding],
        allowed_sensors: set[str],
        max_sensors_per_cycle: int = 4,
    ) -> None:
        if max_sensors_per_cycle <= 0:
            raise ValueError("max_sensors_per_cycle must be positive")
        self.gateway = gateway
        self.bindings = dict(bindings)
        self.allowed_sensors = set(allowed_sensors)
        self.max_sensors_per_cycle = max_sensors_per_cycle

    def _ordered_sensors(self, preferred_sensors: list[str], *, explore: bool) -> list[str]:
        preferred = [
            sensor
            for sensor in preferred_sensors
            if sensor in self.allowed_sensors and sensor in self.bindings
        ]
        if not explore:
            return preferred[: self.max_sensors_per_cycle]

        extras = sorted(
            sensor
            for sensor in self.allowed_sensors
            if sensor in self.bindings and sensor not in preferred
        )
        return (preferred + extras)[: self.max_sensors_per_cycle]

    async def observe(
        self,
        *,
        creator_id: str,
        universe_code: str,
        preferred_sensors: list[str],
        query: str,
        explore: bool,
    ) -> list[PerceptionObservation]:
        observations: list[PerceptionObservation] = []
        for sensor in self._ordered_sensors(preferred_sensors, explore=explore):
            binding = self.bindings[sensor]
            declaration = self.gateway.declaration(binding.capability)
            if declaration.external_effect:
                raise PerceptionPolicyError(
                    f"pre-Mission sensor has external effect: {sensor}"
                )
            if declaration.minimum_idempotency_class is IdempotencyClass.AT_MOST_ONCE:
                raise PerceptionPolicyError(
                    f"pre-Mission sensor requires AT_MOST_ONCE semantics: {sensor}"
                )

            authorization = MissionAuthorization(
                allowed_capabilities=[binding.capability],
                denied_capabilities=[],
                scope={"actions": {binding.capability: [binding.action]}},
                external_effects_allowed=False,
                risk_level="read_only",
                budget={},
                expires_at=None,
                version=1,
                authorized_by="system:perception",
                authorized_at=datetime.now(timezone.utc).isoformat(),
            )
            context = CapabilityContext(
                mission_id=f"perception:{creator_id}:{universe_code}",
                task_id=None,
                authorization=authorization,
            )
            result = await self.gateway.execute(
                CapabilityIntent(
                    capability=binding.capability,
                    action=binding.action,
                    arguments={"query": query},
                    external_effect=False,
                    idempotency_class=IdempotencyClass.SAFE,
                ),
                context,
            )
            if result.ok and result.data:
                observations.append(
                    PerceptionObservation(
                        sensor=sensor,
                        capability=binding.capability,
                        action=binding.action,
                        data=dict(result.data),
                    )
                )
        return observations
