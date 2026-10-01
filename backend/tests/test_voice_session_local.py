from __future__ import annotations

import asyncio
import importlib
import json

import pytest


def local_module():
    try:
        return importlib.import_module('app.voice_session.local')
    except ModuleNotFoundError:
        pytest.fail('Local speech adapters have not been implemented')


class Synthesizer:
    def __init__(self):
        self.calls = []

    async def synthesize(self, text):
        self.calls.append(text)
        return b'\x00\x01' * 240


@pytest.mark.asyncio
async def test_local_tts_buffers_token_fragments_into_complete_sentences():
    engine = Synthesizer()
    async with local_module().KokoroRealtimeTTS(engine) as tts:
        await tts.send_text('Estou ')
        await tts.send_text('aqui. ')
        await tts.send_text('Pode falar')
        await tts.finish()
        chunks = []
        while (chunk := await tts.receive_audio()) is not None:
            chunks.append(chunk)
    assert engine.calls == ['Estou aqui.', 'Pode falar']
    assert b''.join(chunks) == b'\x00\x01' * 480


@pytest.mark.asyncio
async def test_local_tts_propagates_synthesis_failure_instead_of_hanging():
    class Broken:
        async def synthesize(self, text):
            raise OSError('model unavailable')
    async with local_module().KokoroRealtimeTTS(Broken()) as tts:
        await tts.send_text('Olá.')
        await tts.finish()
        with pytest.raises(OSError, match='model unavailable'):
            await asyncio.wait_for(tts.receive_audio(), timeout=1)


class Recognizer:
    def __init__(self):
        self.finals = 0

    def AcceptWaveform(self, audio):
        return False

    def PartialResult(self):
        return json.dumps({'partial': 'deus quanto é dois mais dois'})

    def FinalResult(self):
        self.finals += 1
        return json.dumps({'text': 'deus quanto é dois mais dois'})


@pytest.mark.asyncio
async def test_local_stt_commits_after_short_silence_without_losing_wake_question():
    rec = Recognizer()
    async with local_module().VoskRealtimeSTT(recognizer=rec, silence_ms=400) as stt:
        await stt.send_audio(b'\x00\x20' * 1600)
        partial = await stt.receive_transcript()
        assert partial.text == 'deus quanto é dois mais dois'
        assert not partial.committed
        for _ in range(4):
            await stt.send_audio(b'\x00\x00' * 1600)
        final = await asyncio.wait_for(stt.receive_transcript(), timeout=1)
        assert final.committed
        assert final.text == partial.text
    assert rec.finals == 1


@pytest.mark.asyncio
async def test_explicit_commit_does_not_duplicate_final_when_silent():
    rec = Recognizer()
    async with local_module().VoskRealtimeSTT(recognizer=rec) as stt:
        await stt.send_audio(b'\x00\x20' * 1600, commit=True)
        assert (await stt.receive_transcript()).committed
        await stt.send_audio(b'', commit=True)
    assert rec.finals == 1


def test_local_voice_does_not_require_elevenlabs_credentials(monkeypatch):
    from app.config import settings
    api = importlib.import_module('app.api.voice_session')
    monkeypatch.setattr(settings, 'elevenlabs_enabled', False)
    monkeypatch.setattr(settings, 'elevenlabs_api_key', None)
    monkeypatch.setitem(settings.__dict__, 'deus_voice_engine', 'local')
    configured = getattr(api, '_voice_configured', lambda: False)
    assert configured()


@pytest.mark.asyncio
async def test_local_voice_never_calls_paid_fallback_when_primary_fails():
    from app.inference.contracts import InferenceRequest, InferenceTimeoutError
    from app.voice_session.inference import stream_with_fallback

    class Unavailable:
        name = 'freellmapi'
        async def stream(self, request):
            if False:
                yield ''

    with pytest.raises(InferenceTimeoutError):
        _ = [chunk async for chunk in stream_with_fallback(
            InferenceRequest(messages=[{'role': 'user', 'content': 'Olá'}]),
            primary=Unavailable(), fallback=None,
        )]


@pytest.mark.asyncio
async def test_local_tts_cancel_does_not_emit_audio_from_old_turn():
    started = asyncio.Event()
    release = asyncio.Event()
    class Delayed:
        async def synthesize(self, text):
            started.set()
            await release.wait()
            return b'old audio'

    tts = local_module().KokoroRealtimeTTS(Delayed())
    async with tts:
        await tts.send_text('Primeira resposta.')
        await started.wait()
    release.set()
    await asyncio.sleep(0)
    assert tts._audio.empty()


@pytest.mark.asyncio
async def test_local_stt_rejects_incomplete_pcm_sample():
    async with local_module().VoskRealtimeSTT(recognizer=Recognizer()) as stt:
        with pytest.raises(ValueError, match='PCM16'):
            await stt.send_audio(b'\x01')


@pytest.mark.asyncio
async def test_long_local_response_does_not_abort_on_phrase_queue_capacity():
    engine = Synthesizer()
    async with local_module().KokoroRealtimeTTS(engine) as tts:
        for _ in range(70):
            await tts.send_text('Uma frase completa. ')
        await tts.finish()
        chunks = []
        while (chunk := await asyncio.wait_for(tts.receive_audio(), timeout=1)) is not None:
            chunks.append(chunk)
    assert len(engine.calls) == 70
    assert b''.join(chunks) == b'\x00\x01' * 240 * 70


@pytest.mark.asyncio
async def test_cancelled_native_synthesis_waiter_is_discarded_before_inference():
    module = local_module()
    lock = getattr(module, '_TTS_LOCK', None)
    run = getattr(module, '_run_synthesis', None)
    assert lock is not None and run is not None, 'Separate cancellable TTS scheduling is required'
    calls = []
    lock.acquire()
    try:
        task = asyncio.create_task(run(lambda: calls.append('obsolete') or b'audio'))
        await asyncio.sleep(0.02)
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
    finally:
        lock.release()
    await run(lambda: b'current')
    assert calls == []


@pytest.mark.asyncio
async def test_recognition_does_not_wait_for_obsolete_synthesis():
    module = local_module()
    lock = getattr(module, '_TTS_LOCK', getattr(module, '_CPU_LOCK', None))
    lock.acquire()
    try:
        async with module.VoskRealtimeSTT(recognizer=Recognizer()) as stt:
            await asyncio.wait_for(stt.send_audio(b'\x00\x20' * 1600), timeout=0.5)
    finally:
        lock.release()


@pytest.mark.asyncio
async def test_local_stt_batches_browser_worklet_frames_before_native_recognition():
    rec = Recognizer()
    calls = []
    original = rec.AcceptWaveform
    def accept(audio):
        calls.append(len(audio))
        return original(audio)
    rec.AcceptWaveform = accept
    async with local_module().VoskRealtimeSTT(recognizer=rec) as stt:
        for _ in range(40):
            await stt.send_audio(b'\x00\x20' * 40)
        assert (await stt.receive_transcript()).text.startswith('deus')
    assert calls == [3200]


@pytest.mark.asyncio
async def test_long_idle_does_not_force_an_immediate_empty_commit_on_next_question():
    rec = Recognizer()
    async with local_module().VoskRealtimeSTT(recognizer=rec) as stt:
        for _ in range(310):
            await stt.send_audio(b'\x00\x00' * 1600)
        await stt.send_audio(b'\x00\x20' * 1600)
    assert rec.finals == 0
