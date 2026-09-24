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


def gives_internet_egress(network: dict) -> bool:
    """Whether a container on this network could reach the internet.

    Two shapes prevent it. `internal: true` is the strongest: Docker gives the network no
    gateway at all — but it also stops Docker mapping a published host port, so a range whose
    every network is internal cannot be reached from the machine running it. A bridge with
    masquerading turned off keeps the published loopback ports working while leaving the
    container with no NAT, so nothing it sends can be routed out and answered.
    """
    if network.get("internal") is True:
        return False
    masquerade = network.get("driver_opts", {}).get("com.docker.network.bridge.enable_ip_masquerade")
    return str(masquerade).lower() != "false"


def test_no_range_network_reaches_the_internet() -> None:
    compose = load_compose()
    networks = compose.get("networks", {})
    assert networks, "Cyber Range must declare isolated Docker networks"
    reachable = [name for name, network in networks.items() if gives_internet_egress(network or {})]
    assert not reachable, f"these range networks would let a target reach the internet: {reachable}"


def test_the_targets_stay_on_an_internal_network() -> None:
    """Containment does not rest on the loopback network alone: the targets also talk to the
    controller over a network with no gateway of any kind."""
    services = load_compose()["services"]
    for service_name in ("controller", "juice-shop", "webgoat"):
        assert "range_targets" in services[service_name]["networks"]


def test_controller_is_loopback_only() -> None:
    compose = load_compose()
    controller = compose["services"]["controller"]
    ports = controller.get("ports", [])
    assert ports, "Range Controller must expose its documented local API"
    assert all(published_host(port) == "127.0.0.1" for port in ports)


def test_required_lifecycle_scripts_exist() -> None:
    for name in ("start.sh", "stop.sh", "reset.sh", "verify.sh", "start.ps1", "stop.ps1", "reset.ps1", "verify.ps1"):
        assert (ROOT / "scripts" / name).is_file(), f"missing cyber_range/scripts/{name}"


def test_controller_and_scenarios_exist() -> None:
    assert (ROOT / "controller").is_dir(), "Range Controller source directory is required"
    assert (ROOT / "scenarios").is_dir(), "Range scenarios directory is required"


def test_qualification_rubric_is_present_and_fail_closed() -> None:
    rubric = ROOT / "qualification" / "rubric.json"
    assert rubric.is_file(), "qualification rubric is required"
    import json
    data = json.loads(rubric.read_text(encoding="utf-8"))
    assert [level["id"] for level in data["levels"]] == ["SH-1", "SH-2", "SH-3", "SH-X"]
    assert "containment_failure" in data["disqualifiers"]
    assert "unauthorized_target" in data["disqualifiers"]


def test_controller_has_no_docker_socket_mount() -> None:
    compose = load_compose()
    volumes = compose["services"]["controller"].get("volumes", [])
    assert all("/var/run/docker.sock" not in str(volume) for volume in volumes)


def test_targets_have_no_privileged_mode() -> None:
    compose = load_compose()
    for service_name in ("controller", "juice-shop", "webgoat"):
        assert compose["services"][service_name].get("privileged") is not True
