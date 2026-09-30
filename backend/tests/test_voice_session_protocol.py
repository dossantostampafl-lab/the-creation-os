from __future__ import annotations

from contextlib import asynccontextmanager

import pytest

from app.voice_session.protocol import parse_client_event
from app.voice_session.tickets import consume_voice_ticket, issue_voice_ticket


class FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, bytes] = {}

    async def set(self, key: str, value: str, *, ex: int) -> None:
        assert ex > 0
        self.values[key] = value.encode()

    async def getdel(self, key: str):
        return self.values.pop(key, None)

    async def aclose(self) -> None:
        return None


@pytest.mark.asyncio
async def test_voice_ticket_is_single_use(monkeypatch):
    fake = FakeRedis()

    @asynccontextmanager
    async def fake_client():
        yield fake

    monkeypatch.setattr("app.voice_session.tickets._client", fake_client)

    ticket = await issue_voice_ticket("creator-1")
    assert ticket
    assert await consume_voice_ticket(ticket) == "creator-1"
    assert await consume_voice_ticket(ticket) is None


@pytest.mark.asyncio
async def test_voice_ticket_does_not_embed_creator_identity(monkeypatch):
    fake = FakeRedis()

    @asynccontextmanager
    async def fake_client():
        yield fake

    monkeypatch.setattr("app.voice_session.tickets._client", fake_client)

    ticket = await issue_voice_ticket("creator-sensitive-id")
    assert "creator-sensitive-id" not in ticket


def test_protocol_requires_turn_id_for_barge_in():
    with pytest.raises(ValueError, match="turn_id"):
        parse_client_event('{"type":"barge_in","session_id":"s1"}')


def test_protocol_accepts_wake_control_event():
    event = parse_client_event('{"type":"wake","session_id":"s1","turn_id":0}')
    assert event.type == "wake"
    assert event.session_id == "s1"
    assert event.turn_id == 0


def test_protocol_accepts_pcm_audio_commit_metadata():
    event = parse_client_event(
        '{"type":"audio","session_id":"s1","turn_id":0,'
        '"audio_base64":"AQI=","commit":true,"utterance_id":"u-1"}'
    )

    assert event.audio_base64 == "AQI="
    assert event.commit is True
    assert event.utterance_id == "u-1"
