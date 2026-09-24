# STF kill switch

The runtime is fail-closed. Global or mission kill state prevents new dispatch. Revocation must be checked again at the privileged boundary before execution. Recovery requires a new authorization transition; never clear a kill switch by replaying stale workflow payloads.
