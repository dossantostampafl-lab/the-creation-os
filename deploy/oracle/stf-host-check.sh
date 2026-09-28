#!/usr/bin/env bash
# Can this server run privileged Security Task Force work? Read-only: nothing is installed or changed.
#
#   sudo ./deploy/oracle/stf-host-check.sh
#
# Prints the facts that decide it (architecture, virtualization, KVM, Kata, Firecracker) and then the
# verdict from deploy/stf/verify-host.sh. Exit 0 only when a strong isolation backend is present.
# Plain Docker never counts, so a "no" here means privileged execution stays disabled.
set -uo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
verifier="$here/../stf/verify-host.sh"

echo "== Host =="
echo "arch:        $(uname -m)"
echo "kernel:      $(uname -r)"
if command -v systemd-detect-virt >/dev/null 2>&1; then
  echo "virt:        $(systemd-detect-virt 2>/dev/null || true)"
fi

# The Oracle metadata service names the shape. A bare metal shape (BM.*) can expose KVM; a plain VM
# shape usually cannot, and that difference decides everything below.
shape="$(curl -fsS -m 3 -H 'Authorization: Bearer Oracle' http://169.254.169.254/opc/v2/instance/ 2>/dev/null \
  | python3 -c 'import json,sys; print(json.load(sys.stdin).get("shape",""))' 2>/dev/null || true)"
echo "oci shape:   ${shape:-unknown}"

echo
echo "== CPU virtualization =="
if [ -r /proc/cpuinfo ]; then
  flags="$(grep -m1 -oE '\b(vmx|svm)\b' /proc/cpuinfo 2>/dev/null || true)"
  echo "vmx/svm:     ${flags:-none visible}"
fi
if command -v lscpu >/dev/null 2>&1; then
  lscpu 2>/dev/null | grep -E '^(Hypervisor vendor|Virtualization type|Virtualization):' \
    | sed -E 's/[[:space:]]+/ /g; s/^/             /' || true
fi
if [ -e /dev/kvm ]; then
  ls -l /dev/kvm | sed 's/^/kvm device:  /'
else
  echo "kvm device:  absent"
fi

echo
echo "== Runtimes on PATH =="
for binary in kata-runtime containerd-shim-kata-v2 firecracker jailer; do
  if path="$(command -v "$binary" 2>/dev/null)"; then echo "$binary: $path"; else echo "$binary: not found"; fi
done
if command -v docker >/dev/null 2>&1; then
  if runtimes="$(docker info --format '{{json .Runtimes}}' 2>/dev/null)"; then
    echo "docker runtimes: $runtimes"
  else
    echo "docker runtimes: unreadable (no permission or no daemon)"
  fi
fi

echo
echo "== Verdict =="
if [ ! -f "$verifier" ]; then
  echo "deploy/stf/verify-host.sh is missing, so no verdict can be given; privileged execution stays disabled." >&2
  exit 1
fi
bash "$verifier"
