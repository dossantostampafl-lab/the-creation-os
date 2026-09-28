#!/usr/bin/env bash
# Read-only check of whether this host can provide the isolation the Security Task Force requires
# (Kata Containers or Firecracker). It changes nothing. Exit 0 only if a strong backend is available.
#
# Run it on the machine that would host privileged execution, before setting STF_KATA_AVAILABLE or
# STF_FIRECRACKER_AVAILABLE for the gateway. Plain Docker is never accepted as a substitute.
set -u

kvm=no
kata=no
firecracker=no
[ -e /dev/kvm ] && [ -r /dev/kvm ] && [ -w /dev/kvm ] && kvm=yes
[ "$kvm" = yes ] && command -v kata-runtime >/dev/null 2>&1 && kata=yes
[ "$kvm" = yes ] && command -v firecracker >/dev/null 2>&1 && command -v jailer >/dev/null 2>&1 && firecracker=yes

echo "kvm:         $kvm"
echo "kata:        $kata"
echo "firecracker: $firecracker"
if command -v docker >/dev/null 2>&1; then
  echo "docker:      present (not an accepted sandbox on its own)"
else
  echo "docker:      absent"
fi

if [ "$kata" = yes ] || [ "$firecracker" = yes ]; then
  echo "result: a strong isolation backend is available; STF_SANDBOX_BACKEND=auto may select it"
  exit 0
fi

reason="no_strong_isolation"
[ "$kvm" = no ] && reason="$reason kvm_unavailable"
echo "result: privileged execution must stay disabled ($reason)"
exit 1
