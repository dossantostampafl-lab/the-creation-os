"""Offline Portuguese speech adapters for the existing voice-session protocol.

Models are shared per API process; inference runs outside the event loop. There
are no speech API credentials, network inference requests or paid fallbacks.
"""
from __future__ import annotations

import asyncio
import json
import re
import threading
from array import array
from collections.abc import Callable
from pathlib import Path
from typing import Any

from app.config import settings
from app.voice_session.stt import STTTranscript

# One synthesis thread and one recognition thread fit the two-core host.
# Native inference already running cannot be interrupted; queued obsolete work can.
_TTS_LOCK = threading.Lock()
_models: LocalSpeechEngine | None = None
_model_lock = threading.Lock()


async def _run_synthesis(work: Callable[[], bytes]) -> bytes:
    cancelled = threading.Event()

    def run() -> bytes:
        with _TTS_LOCK:
            if cancelled.is_set():
                return b""
            return work()

    try:
        return await asyncio.to_thread(run)
    except asyncio.CancelledError:
        cancelled.set()
        raise


class LocalSpeechEngine:
    def __init__(self, directory: str) -> None:
        import onnxruntime as rt
        from kokoro_onnx import Kokoro
        from vosk import Model, SetLogLevel

        root = Path(directory)
        options = rt.SessionOptions()
        options.intra_op_num_threads = 1
        options.inter_op_num_threads = 1
        session = rt.InferenceSession(str(root / 'kokoro-v1.0.onnx'), sess_options=options,
                                      providers=['CPUExecutionProvider'])
        self.kokoro = Kokoro.from_session(session, str(root / 'voices-v1.0.bin'))
        SetLogLevel(-1)
        self.vosk = Model(str(root / 'vosk-pt'))

    async def synthesize(self, text: str) -> bytes:
        def run() -> bytes:
            import numpy as np
            audio, rate = self.kokoro.create(text, voice='pm_santa', speed=1.0, lang='pt-br')
            if rate != 24000:
                raise RuntimeError('Local voice must produce 24000 Hz PCM')
            return np.clip(audio * 32767, -32768, 32767).astype('<i2').tobytes()
        return await _run_synthesis(run)

    def recognizer(self) -> Any:
        from vosk import KaldiRecognizer
        return KaldiRecognizer(self.vosk, 16000)


def _load_engine() -> LocalSpeechEngine:
    global _models
    with _model_lock:
        if _models is None:
            _models = LocalSpeechEngine(settings.deus_local_voice_models_dir)
        return _models


async def get_local_engine() -> LocalSpeechEngine:
    return await asyncio.to_thread(_load_engine)


class KokoroRealtimeTTS:
    """Buffer token fragments into short phrases, stream PCM, discard on cancel."""
    def __init__(self, engine: Any) -> None:
        self.engine = engine
        self._text = ''
        self._phrases: asyncio.Queue[str | None] = asyncio.Queue()
        self._audio: asyncio.Queue[bytes | BaseException | None] = asyncio.Queue(maxsize=32)
        self._worker: asyncio.Task[None] | None = None

    async def __aenter__(self) -> KokoroRealtimeTTS:
        self._worker = asyncio.create_task(self._synthesize())
        return self

    async def __aexit__(self, *args: Any) -> None:
        if self._worker is not None:
            self._worker.cancel()
            await asyncio.gather(self._worker, return_exceptions=True)

    async def _synthesize(self) -> None:
        try:
            while (phrase := await self._phrases.get()) is not None:
                audio = await self.engine.synthesize(phrase)
                if not audio:
                    raise RuntimeError('Local voice returned empty audio')
                # Small frames preserve the existing browser playback protocol.
                for offset in range(0, len(audio), 9600):
                    await self._audio.put(audio[offset:offset + 9600])
            await self._audio.put(None)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            await self._audio.put(exc)

    async def send_text(self, text: str) -> None:
        self._text += text
        while self._text:
            boundary = re.search(r'[.!?;](?:\s|$)', self._text)
            if boundary is not None:
                end = boundary.end()
            elif len(self._text) >= 160:
                end = self._text.rfind(' ', 0, 160)
                if end <= 0:
                    end = 160
            else:
                return
            phrase, self._text = self._text[:end].strip(), self._text[end:]
            if phrase:
                self._phrases.put_nowait(phrase)

    async def finish(self) -> None:
        if self._text.strip():
            await self._phrases.put(self._text.strip())
        self._text = ''
        await self._phrases.put(None)

    async def receive_audio(self) -> bytes | None:
        item = await self._audio.get()
        if isinstance(item, BaseException):
            raise item
        return item


class VoskRealtimeSTT:
    def __init__(self, recognizer: Any, *, silence_ms: int = 400) -> None:
        self._recognizer = recognizer
        self._recognition_lock = threading.Lock()
        self._silence_ms = silence_ms
        self._silence_samples = 0
        self._utterance_samples = 0
        self._has_speech = False
        self._last_partial = ''
        self._transcripts: asyncio.Queue[STTTranscript] = asyncio.Queue(maxsize=64)

    async def __aenter__(self) -> VoskRealtimeSTT:
        return self

    async def __aexit__(self, *args: Any) -> None:
        pass

    def _process(self, audio: bytes, commit: bool) -> STTTranscript | None:
        if len(audio) % 2:
            raise ValueError('Local recognition expects PCM16 frames')
        samples = array('h', audio)
        energy = sum(v * v for v in samples) / max(1, len(samples))
        voiced = energy > 350 * 350
        self._has_speech = self._has_speech or voiced
        self._utterance_samples += len(samples)
        self._silence_samples = 0 if voiced else self._silence_samples + len(samples)
        with self._recognition_lock:
            endpoint = self._recognizer.AcceptWaveform(audio) if audio else False
            if endpoint:
                result = json.loads(self._recognizer.Result())
            elif self._has_speech and (
                commit or self._silence_samples >= self._silence_ms * 16
                or self._utterance_samples >= 30 * 16000
            ):
                result = json.loads(self._recognizer.FinalResult())
                endpoint = True
            elif commit:
                return None
            else:
                partial = json.loads(self._recognizer.PartialResult()).get('partial', '').strip()
                if partial and partial != self._last_partial:
                    self._last_partial = partial
                    return STTTranscript(text=partial, committed=False)
                return None
        self._has_speech = False
        self._silence_samples = self._utterance_samples = 0
        self._last_partial = ''
        text = result.get('text', '').strip()
        return STTTranscript(text=text, committed=True) if text else None

    async def send_audio(self, audio: bytes, *, commit: bool = False) -> None:
        transcript = await asyncio.to_thread(self._process, audio, commit)
        if transcript is not None:
            await self._transcripts.put(transcript)

    async def receive_transcript(self) -> STTTranscript:
        return await self._transcripts.get()
