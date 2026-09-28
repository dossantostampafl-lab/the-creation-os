# Cyber Range

Lives in `cyber_range/` (controller, targets, scenario catalog, scripts) under the `cyber-range` profile. Targets are
published on `127.0.0.1` only and sit on internal networks. The Task Force talks to it through `RangeController`, which
accepts only `cyber_range:*` environments and validated scenario ids. Start with `cyber_range/scripts/start.sh`, check
with `verify.sh`, clear state with `reset.sh`.
