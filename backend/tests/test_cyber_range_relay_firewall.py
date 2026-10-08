"""The relay's firewall opening must survive a VM reboot."""

from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "deploy" / "oracle" / "enable-cyber-range-training.sh"


def test_the_relay_port_rule_is_saved_after_it_is_added() -> None:
    body = SCRIPT.read_text(encoding="utf-8")
    rule = body.index("--dport 7071 -j ACCEPT")
    saved = body.index("netfilter-persistent save", rule)
    assert saved > rule
