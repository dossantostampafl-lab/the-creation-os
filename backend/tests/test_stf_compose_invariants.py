from pathlib import Path
import yaml

ROOT=Path(__file__).resolve().parents[2]
COMPOSE=ROOT/"docker-compose.yml"

def compose():
    return yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))

def test_stf_control_plane_is_profile_gated():
    services=compose()["services"]
    for name in ("stf-nats","stf-opa","stf-temporal","stf-worker","stf-gateway"):
        assert "security-task-force" in services[name].get("profiles",[])

def test_gateway_has_no_host_port_or_docker_socket():
    gateway=compose()["services"]["stf-gateway"]
    assert not gateway.get("ports")
    assert all("/var/run/docker.sock" not in str(v) for v in gateway.get("volumes",[]))

def test_control_and_execution_networks_exist():
    networks=compose()["networks"]
    assert networks["stf-control"]["internal"] is True
    assert networks["stf-execution"]["internal"] is True
