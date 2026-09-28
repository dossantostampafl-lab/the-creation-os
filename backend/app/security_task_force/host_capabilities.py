from __future__ import annotations

import os
import platform
import shutil
from dataclasses import dataclass


@dataclass(frozen=True)
class HostCapabilities:
    """What this host can offer. Read-only facts: probing never changes host configuration."""

    kata: bool = False
    firecracker: bool = False
    docker: bool = False
    kvm: bool = False
    os_name: str = "linux"


def probe_host() -> HostCapabilities:
    system = platform.system().lower()
    kvm = system == "linux" and os.path.exists("/dev/kvm") and os.access("/dev/kvm", os.R_OK | os.W_OK)
    # Kata needs a registered runtime and hardware virtualization; Firecracker needs its binary,
    # the jailer that confines it, and KVM. Windows/Docker Desktop offers neither on its own.
    kata = kvm and shutil.which("kata-runtime") is not None
    firecracker = kvm and shutil.which("firecracker") is not None and shutil.which("jailer") is not None
    return HostCapabilities(
        kata=kata, firecracker=firecracker, docker=shutil.which("docker") is not None, kvm=kvm, os_name=system
    )
