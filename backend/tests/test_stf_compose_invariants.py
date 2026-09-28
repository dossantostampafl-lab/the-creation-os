from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
COMPOSE = ROOT / "docker-compose.yml"


def compose():
    return yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))


def test_stf_control_plane_is_profile_gated():
    services = compose()["services"]
    names = ("stf-nats", "stf-opa", "stf-temporal", "stf-worker", "stf-gateway")
    for name in names:
        assert "security-task-force" in services[name].get("profiles", [])


def test_gateway_has_no_host_port_or_docker_socket():
    gateway = compose()["services"]["stf-gateway"]
    assert not gateway.get("ports")
    volumes = gateway.get("volumes", [])
    assert all("/var/run/docker.sock" not in str(volume) for volume in volumes)


def test_control_and_execution_networks_exist():
    networks = compose()["networks"]
    assert networks["stf-control"]["internal"] is True
    assert networks["stf-execution"]["internal"] is True


def test_core_stack_starts_without_any_task_force_service():
    services = compose()["services"]
    core = [name for name in services if not name.startswith("stf-")]
    for name in core:
        depends = services[name].get("depends_on", {})
        names = depends if isinstance(depends, list) else list(depends)
        assert not any(dep.startswith("stf-") for dep in names), name
        assert "security-task-force" not in services[name].get("profiles", [])


def test_control_plane_services_publish_no_host_ports():
    services = compose()["services"]
    for name in ("stf-nats", "stf-opa", "stf-temporal", "stf-worker", "stf-gateway"):
        assert not services[name].get("ports"), name


def test_gateway_is_locked_down_and_has_no_way_to_start_without_a_key():
    gateway = compose()["services"]["stf-gateway"]
    assert gateway["read_only"] is True and "no-new-privileges:true" in gateway["security_opt"]
    assert "STF_GATEWAY_SIGNING_KEY" in gateway["environment"]
    assert gateway["environment"]["STF_ALLOWED_ENVIRONMENTS"].endswith("cyber_range:}")  # real environments off by default
    assert "stf-execution" in gateway["networks"] and "tco_net" not in gateway["networks"]


def test_worker_reaches_only_the_control_network_and_shares_state_with_the_api():
    services = compose()["services"]
    assert list(services["stf-worker"]["networks"]) == ["stf-control"]
    assert any("stf_state" in str(volume) for volume in services["stf-worker"]["volumes"])
    assert any("stf_state" in str(volume) for volume in services["api"]["volumes"])


def test_range_targets_are_loopback_only_and_never_lan_bound():
    range_compose = yaml.safe_load((ROOT / "cyber_range" / "compose.yml").read_text(encoding="utf-8"))
    for name, service in range_compose["services"].items():
        assert "cyber-range" in service.get("profiles", []), name
        for port in service.get("ports", []):
            assert str(port).startswith("127.0.0.1:"), (name, port)
    assert "cyber-range" not in str(compose()["services"].keys())
