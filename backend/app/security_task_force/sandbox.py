from __future__ import annotations

from dataclasses import dataclass, field

from .host_capabilities import HostCapabilities

# SOPHIA's criteria (FD-020). Only Kata and Firecracker are ever candidates.
_SCORES: dict[str, dict[str, int]] = {
    "kata": {"isolation": 5, "compatibility": 5, "performance": 3, "simplicity": 4, "auditability": 4,
             "recovery": 4, "least_privilege": 4},
    "firecracker": {"isolation": 5, "compatibility": 3, "performance": 5, "simplicity": 2, "auditability": 4,
                    "recovery": 4, "least_privilege": 5},
}


@dataclass(frozen=True)
class SandboxSelection:
    engine: str | None
    privileged_execution_enabled: bool
    reason_codes: list[str] = field(default_factory=list)


def select_sandbox(*, host: HostCapabilities, preferred: str = "auto") -> SandboxSelection:
    """Choose an isolation boundary or disable privileged execution.

    There is no weaker fallback: plain Docker is not a candidate, and a host that cannot provide
    Kata or Firecracker leaves privileged execution off while the control plane keeps running.
    """
    if preferred not in {"auto", "kata", "firecracker"}:
        return SandboxSelection(None, False, ["unknown_backend"])
    candidates = [name for name, ok in (("kata", host.kata), ("firecracker", host.firecracker)) if ok]
    if preferred != "auto":
        if preferred not in candidates:
            return SandboxSelection(None, False, ["configured_backend_unavailable"])
        return SandboxSelection(preferred, True, ["configured_backend"])
    if not candidates:
        reasons = ["no_strong_isolation"] + ([] if host.kvm else ["kvm_unavailable"])
        return SandboxSelection(None, False, reasons)
    best = max(candidates, key=lambda name: (sum(_SCORES[name].values()), name == "kata"))
    return SandboxSelection(best, True, ["sophia_ranked"])
