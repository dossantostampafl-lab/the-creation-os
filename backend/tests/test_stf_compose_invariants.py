from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
COMPOSE = ROOT / "docker-compose.yml"


def compose():
    return yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))


def test_stf_control_plane_is_profile_gated():
    services = compose()["services"]
    names = ("stf-nats", "stf-opa", "stf-temporal", "stf-worker", "stf-training-worker", "stf-gateway")
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
    for name in ("stf-nats", "stf-opa", "stf-temporal", "stf-worker", "stf-training-worker", "stf-gateway"):
        assert not services[name].get("ports"), name


def test_gateway_is_locked_down_and_has_no_way_to_start_without_a_key():
    gateway = compose()["services"]["stf-gateway"]
    assert gateway["read_only"] is True and "no-new-privileges:true" in gateway["security_opt"]
    assert "STF_GATEWAY_SIGNING_KEY" in gateway["environment"]
    assert gateway["environment"]["STF_ALLOWED_ENVIRONMENTS"].endswith("cyber_range:}")  # real environments off by default
    assert "stf-execution" in gateway["networks"] and "tco_net" not in gateway["networks"]


def test_workers_reach_postgres_and_private_control_without_execution_network():
    services = compose()["services"]
    assert set(services["stf-worker"]["networks"]) == {"tco_net", "stf-control"}
    assert set(services["stf-training-worker"]["networks"]) == {"tco_net", "stf-control"}
    assert "stf-execution" not in services["stf-worker"]["networks"]
    assert "stf-execution" not in services["stf-training-worker"]["networks"]
    assert any("stf_state" in str(volume) for volume in services["stf-worker"]["volumes"])
    assert any("stf_state" in str(volume) for volume in services["api"]["volumes"])
    assert services["stf-training-worker"]["command"][-1] == "app.security_task_force.training_worker"


def test_temporal_accepts_clients_on_both_private_network_interfaces():
    temporal = compose()["services"]["stf-temporal"]
    assert set(temporal["networks"]) == {"tco_net", "stf-control"}
    # auto-setup otherwise chooses one hostname address; Docker DNS can return
    # the other interface, producing ConnectionRefused despite a running server.
    assert temporal["environment"].get("BIND_ON_IP") == "0.0.0.0"
    assert not temporal.get("ports")


def test_range_targets_are_loopback_only_and_never_lan_bound():
    range_compose = yaml.safe_load((ROOT / "cyber_range" / "compose.yml").read_text(encoding="utf-8"))
    for name, service in range_compose["services"].items():
        assert "cyber-range" in service.get("profiles", []), name
        for port in service.get("ports", []):
            assert str(port).startswith("127.0.0.1:"), (name, port)
    assert "cyber-range" not in str(compose()["services"].keys())


def test_observability_is_optional_read_only_and_loopback_only():
    services = compose()["services"]
    names = ("stf-loki", "stf-promtail", "stf-grafana")
    for name in names:
        assert services[name]["profiles"] == ["observability"], name
        assert not any("docker.sock" in str(volume) for volume in services[name].get("volumes", [])), name
    assert not services["stf-loki"].get("ports") and not services["stf-promtail"].get("ports")
    assert services["stf-grafana"]["ports"] == ['127.0.0.1:${STF_GRAFANA_PORT:-3001}:3000']
    logs = [v for v in services["stf-promtail"]["volumes"] if "/var/lib/docker/containers" in str(v)]
    assert logs and all(str(v).endswith(":ro") for v in logs)
    assert compose()["networks"]["obs-backend"]["internal"] is True
    assert services["stf-grafana"]["environment"]["GF_AUTH_ANONYMOUS_ENABLED"] == "false"
    for name in ("stf-worker", "stf-gateway", "api", "worker"):
        assert "obs-backend" not in services[name].get("networks", []), name


def test_core_stack_does_not_depend_on_observability():
    services = compose()["services"]
    for name, service in services.items():
        depends = service.get("depends_on", {})
        deps = depends if isinstance(depends, list) else list(depends)
        if name not in ("stf-promtail", "stf-grafana"):
            assert not any(dep in ("stf-loki", "stf-promtail", "stf-grafana") for dep in deps), name
