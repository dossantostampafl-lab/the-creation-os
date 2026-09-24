from __future__ import annotations

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
COMPOSE = ROOT / "compose.yml"


def load_compose() -> dict:
    assert COMPOSE.exists(), "cyber_range/compose.yml must exist"
    return yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))


def published_host(port_spec: object) -> str | None:
    if isinstance(port_spec, str):
        parts = port_spec.split(":")
        if len(parts) >= 3:
            return parts[0]
        return None
    if isinstance(port_spec, dict):
        host_ip = port_spec.get("host_ip")
        return str(host_ip) if host_ip is not None else None
    return None


def test_vulnerable_targets_never_bind_to_lan() -> None:
    compose = load_compose()
    services = compose["services"]

    for service_name in ("juice-shop", "webgoat"):
        service = services[service_name]
        for port_spec in service.get("ports", []):
            assert published_host(port_spec) == "127.0.0.1", (
                f"{service_name} must publish only on 127.0.0.1: {port_spec!r}"
            )


def test_range_networks_are_internal() -> None:
    compose = load_compose()
    networks = compose.get("networks", {})
    assert networks, "Cyber Range must declare isolated Docker networks"
    assert all(network.get("internal") is True for network in networks.values())


def test_controller_is_loopback_only() -> None:
    compose = load_compose()
    controller = compose["services"]["controller"]
    ports = controller.get("ports", [])
    assert ports, "Range Controller must expose its documented local API"
    assert all(published_host(port) == "127.0.0.1" for port in ports)


def test_required_lifecycle_scripts_exist() -> None:
    for name in ("start.sh", "stop.sh", "reset.sh", "verify.sh"):
        assert (ROOT / "scripts" / name).is_file(), f"missing cyber_range/scripts/{name}"


def test_controller_and_scenarios_exist() -> None:
    assert (ROOT / "controller").is_dir(), "Range Controller source directory is required"
    assert (ROOT / "scenarios").is_dir(), "Range scenarios directory is required"
