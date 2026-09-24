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
