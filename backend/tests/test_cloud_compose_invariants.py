"""What the cloud server's Compose overlay must not take away.

The overlay hardens the stack for a machine on the public internet, and it is easy to harden
one thing into breaking another: removing the API's published port looks like tightening, but
it is the port the installer waits on and creates the Creator through, so the deployment comes
up with no account and no way in. These tests hold both ends of that at once.
"""

from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "docker-compose.yml"
CLOUD = ROOT / "docker-compose.cloud.yml"
INSTALLER = ROOT / "deploy" / "oracle" / "install.sh"


class ComposeLoader(yaml.SafeLoader):
    """Compose's `!reset` tag is not YAML the safe loader knows; read it as "removed"."""


ComposeLoader.add_constructor("!reset", lambda loader, node: None)


def load(path: Path) -> dict:
    return yaml.load(path.read_text(encoding="utf-8"), Loader=ComposeLoader)


def published(service: dict) -> list[str]:
    return [str(port) for port in service.get("ports") or []]


def test_the_installer_can_still_reach_the_api_on_loopback() -> None:
    api = load(BASE)["services"]["api"]
    assert any(port.startswith("127.0.0.1:") for port in published(api)), (
        "the API must stay published on loopback: the installer waits on it and bootstraps "
        "the Creator through it"
    )
    assert "127.0.0.1:8000" in INSTALLER.read_text(encoding="utf-8"), (
        "the installer no longer uses the loopback API; this test is guarding the wrong address"
    )
    cloud_api = load(CLOUD)["services"]["api"]
    assert "ports" not in cloud_api, "the cloud overlay must not take the API's loopback port away"


def test_the_api_keeps_its_route_to_a_provider_on_this_machine() -> None:
    """install.sh opens the firewall for a FreeLLMAPI on port 3001 reached through the host."""
    assert "extra_hosts" not in load(CLOUD)["services"]["api"]
    assert "extra_hosts" not in load(CLOUD)["services"]["worker"]


def test_only_caddy_is_reachable_from_the_internet() -> None:
    cloud = load(CLOUD)["services"]
    assert cloud["frontend"]["ports"] is None, "only Caddy may publish the site"
    for name, service in cloud.items():
        if name == "caddy":
            continue
        for port in published(service):
            assert port.startswith("127.0.0.1:"), f"{name} publishes {port} beyond loopback"
    assert sorted(published(cloud["caddy"])) == ["443:443", "80:80"]
