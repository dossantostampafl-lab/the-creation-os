from __future__ import annotations

from pathlib import Path

import pytest

from app.capabilities.contracts import CapabilityContext, CapabilityIntent, MissionAuthorization
from app.capabilities.workspace import WorkspaceCapabilityAdapter


def context_for(mission: str) -> CapabilityContext:
    return CapabilityContext(
        mission_id=mission,
        authorization=MissionAuthorization(
            allowed_capabilities=["workspace"], authorized_by="creator", authorized_at="2026-01-01T00:00:00Z",
        ),
    )


def intent_for(action: str, resource: str | None = None, **arguments) -> CapabilityIntent:
    return CapabilityIntent(capability="workspace", action=action, resource=resource, arguments=arguments)


@pytest.fixture
def adapter(tmp_path: Path) -> WorkspaceCapabilityAdapter:
    return WorkspaceCapabilityAdapter(root=tmp_path, max_bytes=200)


@pytest.mark.asyncio
async def test_what_a_mission_writes_it_can_read_back(adapter: WorkspaceCapabilityAdapter) -> None:
    mission = context_for("mission-a")

    written = await adapter.execute(intent_for("write", "notes/plan.md", content="first draft"), mission)
    read = await adapter.execute(intent_for("read", "notes/plan.md"), mission)
    listed = await adapter.execute(intent_for("list"), mission)

    assert written.ok and written.data["bytes"] == len("first draft")
    assert read.ok and read.data["content"] == "first draft"
    assert listed.ok and listed.data["entries"] == ["notes/"]


@pytest.mark.asyncio
async def test_append_adds_to_the_file(adapter: WorkspaceCapabilityAdapter) -> None:
    mission = context_for("mission-a")
    await adapter.execute(intent_for("write", "log.txt", content="one\n"), mission)

    await adapter.execute(intent_for("append", "log.txt", content="two\n"), mission)
    read = await adapter.execute(intent_for("read", "log.txt"), mission)

    assert read.data["content"] == "one\ntwo\n"


@pytest.mark.asyncio
async def test_a_mission_cannot_reach_another_missions_work(adapter: WorkspaceCapabilityAdapter) -> None:
    await adapter.execute(intent_for("write", "secret.txt", content="mine"), context_for("mission-a"))
    other = context_for("mission-b")

    read = await adapter.execute(intent_for("read", "secret.txt"), other)
    listed = await adapter.execute(intent_for("list"), other)

    assert not read.ok and read.error["code"] == "WORKSPACE_REJECTED"
    assert listed.data["entries"] == []


@pytest.mark.asyncio
@pytest.mark.parametrize("resource", [
    "../escape.txt",
    "notes/../../escape.txt",
    "/etc/passwd",
    "..",
    "C:\\Windows\\system.ini",
    "\\\\host\\share\\file",
    "",
    "   ",
])
async def test_a_path_that_leaves_the_mission_directory_is_refused(
    adapter: WorkspaceCapabilityAdapter, tmp_path: Path, resource: str,
) -> None:
    result = await adapter.execute(intent_for("write", resource, content="x"), context_for("mission-a"))

    assert not result.ok and result.error["code"] == "WORKSPACE_REJECTED"
    assert not (tmp_path / "escape.txt").exists()


@pytest.mark.asyncio
async def test_a_symlink_out_of_the_mission_is_refused(
    adapter: WorkspaceCapabilityAdapter, tmp_path: Path,
) -> None:
    outside = tmp_path / "outside.txt"
    outside.write_text("not yours")
    mission_root = tmp_path / "mission-a"
    mission_root.mkdir()
    (mission_root / "link.txt").symlink_to(outside)

    result = await adapter.execute(intent_for("read", "link.txt"), context_for("mission-a"))

    assert not result.ok and result.error["code"] == "WORKSPACE_REJECTED"


@pytest.mark.asyncio
async def test_writes_stay_within_the_size_limit(adapter: WorkspaceCapabilityAdapter) -> None:
    mission = context_for("mission-a")

    too_big = await adapter.execute(intent_for("write", "big.txt", content="x" * 201), mission)
    await adapter.execute(intent_for("write", "grow.txt", content="x" * 150), mission)
    overflows = await adapter.execute(intent_for("append", "grow.txt", content="x" * 100), mission)

    assert not too_big.ok and not overflows.ok
    assert overflows.error["code"] == "WORKSPACE_REJECTED"


@pytest.mark.asyncio
@pytest.mark.parametrize(("action", "arguments"), [
    ("delete", {"content": "x"}),
    ("write", {}),
    ("write", {"content": 42}),
])
async def test_an_unsupported_request_is_refused(
    adapter: WorkspaceCapabilityAdapter, action: str, arguments: dict,
) -> None:
    intent = CapabilityIntent(capability="workspace", action=action, resource="f.txt", arguments=arguments)

    result = await adapter.execute(intent, context_for("mission-a"))

    assert not result.ok and result.error["code"] == "WORKSPACE_REJECTED"


@pytest.mark.asyncio
async def test_reading_a_missing_file_fails_without_raising(adapter: WorkspaceCapabilityAdapter) -> None:
    result = await adapter.execute(intent_for("read", "nope.txt"), context_for("mission-a"))

    assert not result.ok and result.error["code"] == "WORKSPACE_REJECTED"


@pytest.mark.asyncio
@pytest.mark.parametrize("mission", ["../..", "/srv", "", ".", "a/b"])
async def test_a_mission_id_that_could_relocate_the_sandbox_is_refused(
    adapter: WorkspaceCapabilityAdapter, mission: str,
) -> None:
    # model_copy so an id the contract itself would reject still reaches the adapter.
    context = context_for("mission-a").model_copy(update={"mission_id": mission})

    result = await adapter.execute(intent_for("write", "f.txt", content="x"), context)

    assert not result.ok and result.error["code"] == "WORKSPACE_REJECTED"


@pytest.mark.asyncio
async def test_a_nul_byte_in_the_path_is_refused(adapter: WorkspaceCapabilityAdapter) -> None:
    result = await adapter.execute(intent_for("write", "no\x00pe.txt", content="x"), context_for("mission-a"))

    assert not result.ok and result.error["code"] == "WORKSPACE_REJECTED"
