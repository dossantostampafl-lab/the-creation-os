#!/usr/bin/env bash
set -euo pipefail

TABLE="tco_range"
TARGET_BRIDGE="tco_rng_tgt"
CONTROL_BRIDGE="tco_rng_ctl"
PUBLIC_BRIDGE="tco_rng_pub"

usage() {
  echo "Usage: $0 {apply|status|remove}" >&2
  exit 2
}

require_root() {
  if [ "$(id -u)" -ne 0 ]; then
    echo "containment firewall requires root" >&2
    exit 1
  fi
}

require_nft() {
  command -v nft >/dev/null 2>&1 || {
    echo "nftables is required for Cyber Range host containment" >&2
    exit 1
  }
}

apply_rules() {
  require_root
  require_nft

  # Replace only our dedicated table; do not flush or rewrite the host's existing firewall.
  nft delete table inet "$TABLE" 2>/dev/null || true
  nft -f - <<NFT
table inet tco_range {
  chain input {
    type filter hook input priority -50; policy accept;
    ct state established,related accept
    iifname "$TARGET_BRIDGE" drop
    iifname "$CONTROL_BRIDGE" drop
    iifname "$PUBLIC_BRIDGE" drop
  }

  chain forward {
    type filter hook forward priority -50; policy accept;
    ct state established,related accept
    iifname "$TARGET_BRIDGE" oifname != "$TARGET_BRIDGE" drop
    iifname "$CONTROL_BRIDGE" oifname != "$CONTROL_BRIDGE" drop
    iifname "$PUBLIC_BRIDGE" oifname != "$PUBLIC_BRIDGE" drop
  }
}
NFT
  nft list table inet "$TABLE" >/dev/null
  echo "Cyber Range containment firewall applied."
}

status_rules() {
  require_nft
  nft list table inet "$TABLE"
}

remove_rules() {
  require_root
  require_nft
  nft delete table inet "$TABLE"
  echo "Cyber Range containment firewall removed."
}

case "${1:-}" in
  apply) apply_rules ;;
  status) status_rules ;;
  remove) remove_rules ;;
  *) usage ;;
esac
