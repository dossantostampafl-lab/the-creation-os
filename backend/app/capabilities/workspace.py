"""A place where a Mission can keep what it produces.

Each Mission gets its own directory and can never reach outside it: the path an Agent asks
for is resolved and confirmed to stay inside, so one Mission cannot read another's work and
none can touch the rest of the filesystem. Nothing here leaves the machine, so this
capability declares no external effect.
"""

from __future__ import annotations

from pathlib import Path, PurePosixPath

from app.capabilities.contracts import (
    CapabilityContext,
    CapabilityIntent,
    CapabilityResult,
    IdempotencyClass,
)

CAPABILITY = "workspace"
ACTIONS = ("write", "read", "list", "append")


class WorkspaceError(RuntimeError):
    """The Agent asked for something this capability will not do."""


def _relative(resource: str | None) -> Path:
    """The path an Agent asked for, rejected unless it is a plain relative path.

    Parsed as POSIX so a Windows-style path is refused outright rather than quietly
    becoming a filename with backslashes in it.
    """
    raw = (resource or "").strip()
    if not raw:
        raise WorkspaceError("workspace requires a resource path")
    if "\0" in raw:
        raise WorkspaceError("workspace paths must not contain a NUL byte")
    if "\\" in raw:
        raise WorkspaceError("workspace paths must use '/' as the separator")
    candidate = PurePosixPath(raw)
    if candidate.is_absolute():
        raise WorkspaceError("workspace paths must be relative")
    if ".." in candidate.parts:
        raise WorkspaceError("workspace paths must not leave the Mission directory")
    parts = [part for part in candidate.parts if part != "."]
    if not parts:
        raise WorkspaceError("workspace requires a resource path")
    return Path(*parts)


class WorkspaceCapabilityAdapter:
    name = CAPABILITY
    # Nothing leaves the machine, and writing the same file twice ends in the same place.
    external_effect = False
    minimum_idempotency_class = IdempotencyClass.IDEMPOTENT

    def __init__(self, *, root: Path, max_bytes: int = 1_000_000) -> None:
        if max_bytes <= 0:
            raise ValueError("workspace max_bytes must be positive")
        self._root = root
        self._max_bytes = max_bytes

    def _mission_directory(self, context: CapabilityContext) -> Path:
        # The Mission's own id names its directory, so it is held to the same rule as any
        # other path: one plain segment, nothing that could relocate the sandbox.
        mission = context.mission_id.strip()
        if mission in {"", ".", ".."} or "/" in mission or "\\" in mission or "\0" in mission:
            raise WorkspaceError("workspace mission id is not a usable directory name")
        directory = self._root / mission
        directory.mkdir(parents=True, exist_ok=True)
        return directory.resolve()

    def _target(self, context: CapabilityContext, resource: str | None) -> Path:
        mission_root = self._mission_directory(context)
        target = (mission_root / _relative(resource)).resolve()
        # The decisive check: a symlink or any path trick must not land outside the Mission.
        if target != mission_root and mission_root not in target.parents:
            raise WorkspaceError("workspace paths must not leave the Mission directory")
        return target

    async def execute(self, intent: CapabilityIntent, context: CapabilityContext) -> CapabilityResult:
        try:
            data = self._run(intent, context)
        except WorkspaceError as exc:
            return CapabilityResult(
                capability=CAPABILITY, action=intent.action, ok=False,
                error={"code": "WORKSPACE_REJECTED", "detail": str(exc)},
            )
        # A path the operating system refuses outright (a NUL byte slipped past, a name too
        # long) arrives as ValueError from resolve(); that is a refusal, not a crash.
        except ValueError as exc:
            return CapabilityResult(
                capability=CAPABILITY, action=intent.action, ok=False,
                error={"code": "WORKSPACE_REJECTED", "detail": f"workspace path is not usable: {exc.__class__.__name__}"},
            )
        except OSError as exc:
            return CapabilityResult(
                capability=CAPABILITY, action=intent.action, ok=False,
                error={"code": "WORKSPACE_IO_ERROR", "detail": exc.__class__.__name__},
            )
        return CapabilityResult(capability=CAPABILITY, action=intent.action, ok=True, data=data)

    def _run(self, intent: CapabilityIntent, context: CapabilityContext) -> dict:
        if intent.action not in ACTIONS:
            raise WorkspaceError(f"workspace action must be one of: {', '.join(ACTIONS)}")

        if intent.action == "list":
            mission_root = self._mission_directory(context)
            base = self._target(context, intent.resource) if intent.resource else mission_root
            if not base.is_dir():
                raise WorkspaceError("workspace list requires a directory")
            entries = sorted(
                str(item.relative_to(mission_root)) + ("/" if item.is_dir() else "")
                for item in base.iterdir()
            )
            return {"entries": entries}

        target = self._target(context, intent.resource)

        if intent.action == "read":
            if not target.is_file():
                raise WorkspaceError("workspace read requires an existing file")
            if target.stat().st_size > self._max_bytes:
                raise WorkspaceError("workspace file is too large to read")
            return {"content": target.read_text(encoding="utf-8", errors="replace")}

        content = intent.arguments.get("content")
        if not isinstance(content, str):
            raise WorkspaceError("workspace write requires a string 'content' argument")
        encoded = content.encode("utf-8")
        existing = target.stat().st_size if intent.action == "append" and target.is_file() else 0
        if existing + len(encoded) > self._max_bytes:
            raise WorkspaceError("workspace write exceeds the size limit")

        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("a" if intent.action == "append" else "w", encoding="utf-8") as handle:
            handle.write(content)
        return {"path": intent.resource, "bytes": len(encoded)}
