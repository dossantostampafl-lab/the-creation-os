# Sandbox selection

Only Kata Containers or Firecracker may run privileged work (FD-020). `probe_host()` reads facts only: KVM access,
`kata-runtime`, and `firecracker` plus `jailer`. `select_sandbox()` ranks the candidates that exist; with none, privileged
execution is disabled and the reason is `no_strong_isolation`. Plain Docker is never a candidate.

The gateway takes its backend from `STF_SANDBOX_BACKEND` (`auto`, `kata`, `firecracker`) and the availability flags
`STF_KATA_AVAILABLE` / `STF_FIRECRACKER_AVAILABLE`. On Windows/Docker Desktop, expect privileged execution to stay off;
the control plane, policy plane and Range simulation still run.
