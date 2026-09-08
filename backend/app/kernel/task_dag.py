from __future__ import annotations


def ready_step_keys(
    dependencies: dict[str, set[str]],
    *,
    succeeded: set[str],
    terminal: set[str],
) -> list[str]:
    ready: list[str] = []
    for step_key in sorted(dependencies):
        if step_key in terminal:
            continue
        required = dependencies[step_key]
        if required <= succeeded:
            ready.append(step_key)
    return ready
