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


def test_vulnerable_targets_are_not_published_at_all() -> None:
    services = load_compose()["services"]
    for service_name in ("juice-shop", "webgoat"):
        assert services[service_name].get("ports", []) == []
        assert services[service_name]["networks"] == ["range_targets"]


def test_fixed_target_proxies_are_loopback_only_and_unprivileged() -> None:
    services = load_compose()["services"]
    expected = {
        "controller-proxy": ("controller", "7070"),
        "juice-shop-proxy": ("juice-shop", "3000"),
        "webgoat-proxy": ("webgoat", "8080"),
        "webwolf-proxy": ("webgoat", "9090"),
    }
    for service_name, (target, port) in expected.items():
        service = services[service_name]
        assert service["environment"]["TARGET_HOST"] == target
        assert str(service["environment"]["TARGET_PORT"]) == port
        expected_internal = "range_control" if service_name == "controller-proxy" else "range_targets"
        assert set(service["networks"]) == {expected_internal, "range_loopback"}
        assert service.get("read_only") is True
        assert "ALL" in service.get("cap_drop", [])
        assert service.get("privileged") is not True
        assert service.get("volumes", []) == []
        assert all(published_host(spec) == "127.0.0.1" for spec in service.get("ports", []))


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


def test_the_targets_have_only_the_internal_target_network() -> None:
    services = load_compose()["services"]
    for service_name in ("juice-shop", "webgoat"):
        assert services[service_name]["networks"] == ["range_targets"]
    assert services["controller"]["networks"] == ["range_control"]


def test_controller_is_reachable_only_through_its_loopback_proxy() -> None:
    services = load_compose()["services"]
    assert services["controller"].get("ports", []) == []
    proxy = services["controller-proxy"]
    assert proxy["environment"]["TARGET_HOST"] == "controller"
    assert str(proxy["environment"]["TARGET_PORT"]) == "7070"
    assert proxy.get("ports")
    assert all(published_host(port) == "127.0.0.1" for port in proxy["ports"])


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


def test_range_services_have_no_privileged_mode() -> None:
    compose = load_compose()
    for service_name in (
        "controller", "juice-shop", "webgoat",
        "controller-proxy", "juice-shop-proxy", "webgoat-proxy", "webwolf-proxy",
    ):
        assert compose["services"][service_name].get("privileged") is not True


def test_reset_preserves_evidence_volumes() -> None:
    """A reset clears scenario state; the evidence journal and the snapshots are proof and stay."""
    for name in ("reset.sh", "reset.ps1"):
        script = (ROOT / "scripts" / name).read_text(encoding="utf-8")
        code = "\n".join(line for line in script.splitlines() if not line.lstrip().startswith(("#",)))
        assert "down -v" not in code and "--volumes" not in code, f"{name} deletes every volume"
        assert "range_evidence" not in code and "range_snapshots" not in code, f"{name} touches the proof volumes"


def test_vulnerable_targets_and_controller_cannot_join_the_host_publication_network() -> None:
    services = load_compose()["services"]
    for service_name in ("juice-shop", "webgoat", "controller"):
        assert "range_loopback" not in services[service_name].get("networks", [])
    for service_name in ("juice-shop", "webgoat"):
        assert "range_control" not in services[service_name].get("networks", [])
    assert "range_targets" not in services["controller"].get("networks", [])


def test_proxies_have_no_docker_socket_or_host_network_mode() -> None:
    services = load_compose()["services"]
    for service_name in ("controller-proxy", "juice-shop-proxy", "webgoat-proxy", "webwolf-proxy"):
        service = services[service_name]
        assert service.get("network_mode") != "host"
        assert all("/var/run/docker.sock" not in str(volume) for volume in service.get("volumes", []))


def test_range_bridges_have_stable_names_for_host_firewall_enforcement() -> None:
    networks = load_compose()["networks"]
    assert networks["range_targets"]["driver_opts"]["com.docker.network.bridge.name"] == "tco_rng_tgt"
    assert networks["range_control"]["driver_opts"]["com.docker.network.bridge.name"] == "tco_rng_ctl"
    assert networks["range_loopback"]["driver_opts"]["com.docker.network.bridge.name"] == "tco_rng_pub"


def test_linux_containment_script_blocks_new_host_and_routed_connections() -> None:
    script = ROOT / "scripts" / "containment-linux.sh"
    assert script.is_file()
    code = script.read_text(encoding="utf-8")
    assert "table inet tco_range" in code
    assert "ct state established,related accept" in code
    for bridge in ("tco_rng_tgt", "tco_rng_ctl", "tco_rng_pub"):
        assert bridge in code
    assert "hook input" in code and "hook forward" in code
    assert "drop" in code
    assert "CYBER_RANGE_ENFORCE_HOST_FIREWALL" not in code, "the enforcement script itself must not silently no-op"


def test_runtime_smoke_applies_host_firewall_and_probes_host_reachability() -> None:
    workflow = ROOT.parent / ".github" / "workflows" / "cyber-range.yml"
    text = workflow.read_text(encoding="utf-8")
    assert "containment-linux.sh apply" in text
    assert "containment-linux.sh status" in text
    assert "HOST_GATEWAY" in text
    assert "host containment failed" in text
    assert "containment-linux.sh remove" in text
