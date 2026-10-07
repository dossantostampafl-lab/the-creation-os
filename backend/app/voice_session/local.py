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
from contextlib import nullcontext
from pathlib import Path
from typing import Any

from loguru import logger

from app.config import settings
from app.observability.telemetry import operation, traced
from app.voice_session.stt import STTTranscript
from app.voice_session.tts import VoiceSynthesisError

# Synthesis uses at most two CPU threads; recognition schedules independently.
# Native inference already running cannot be interrupted; queued obsolete work can.
_TTS_LOCK = threading.Lock()
_models: LocalSpeechEngine | None = None
_model_lock = threading.Lock()

# The large model often hears "Deus" as "seis", "adeus" or nothing on real microphones.
# A small model restricted to this grammar only decides whether "Deus" was said.
WAKE_GRAMMAR = json.dumps(["deus", "[unk]"])
WAKE_MIN_CONFIDENCE = 0.8
# A confident transcription of a look-alike word over the same audio vetoes the wake.
WAKE_LOOKALIKES = frozenset({"adeus", "museus", "dois", "seus", "meus", "teus", "zeus", "céus", "deu"})
WAKE_LOOKALIKE_MIN_CONFIDENCE = 0.8


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
        options.intra_op_num_threads = settings.deus_local_voice_cpu_threads
        options.inter_op_num_threads = 1
        session = rt.InferenceSession(str(root / 'kokoro-v1.0.onnx'), sess_options=options,
                                      providers=['CPUExecutionProvider'])
        self.kokoro = Kokoro.from_session(session, str(root / 'voices-v1.0.bin'))
        SetLogLevel(-1)
        self.vosk = Model(str(root / 'vosk-pt'))
        self.wake_vosk = None
        wake = root / 'vosk-wake-pt'
        if wake.is_dir():
            # The spotter is optional: a broken install must not stop the API from starting.
            try:
                self.wake_vosk = Model(str(wake))
            except Exception:
                logger.warning("Wake-word model at {} failed to load; using the main model only", wake)

    @traced("voice.tts")
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
        recognizer = KaldiRecognizer(self.vosk, 16000)
        recognizer.SetWords(True)
        return recognizer

    def wake_recognizer(self) -> Any | None:
        from vosk import KaldiRecognizer
        if self.wake_vosk is None:
            return None
        recognizer = KaldiRecognizer(self.wake_vosk, 16000, WAKE_GRAMMAR)
        recognizer.SetWords(True)
        return recognizer


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
            error = VoiceSynthesisError()
            error.__cause__ = exc
            await self._audio.put(error)

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


def _wake_hits(result: dict[str, Any]) -> list[tuple[float, float]]:
    return [
        (float(word['start']), float(word['end']))
        for word in result.get('result', [])
        if word.get('word') == 'deus' and float(word.get('conf', 0)) >= WAKE_MIN_CONFIDENCE
    ]


def _apply_wake(result: dict[str, Any], hits: list[tuple[float, float]]) -> str:
    """Return the transcript with "deus" restored where the wake spotter heard it."""
    text = str(result.get('text', '')).strip()
    if not hits or re.search(r'\bdeus\b', text):
        return text
    words = [w for w in result.get('result', []) if isinstance(w, dict) and 'word' in w]
    for start, end in hits:
        overlapping = [
            w for w in words
            if float(w.get('start', 0)) < end and float(w.get('end', 0)) > start
        ]
        if any(
            w['word'] in WAKE_LOOKALIKES and float(w.get('conf', 0)) >= WAKE_LOOKALIKE_MIN_CONFIDENCE
            for w in overlapping
        ):
            continue
        before = [w['word'] for w in words if float(w.get('end', 0)) <= start and w not in overlapping]
        after = [w['word'] for w in words if float(w.get('start', 0)) >= end and w not in overlapping]
        return ' '.join([*before, 'deus', *after])
    return text


class VoskRealtimeSTT:
    def __init__(
        self,
        recognizer: Any,
        *,
        silence_ms: int = 400,
        wake_recognizer: Any | None = None,
        debug_transcripts: bool = False,
    ) -> None:
        self._recognizer = recognizer
        self._wake_recognizer = wake_recognizer
        self._wake_hits: list[tuple[float, float]] = []
        self._debug_transcripts = debug_transcripts
        self._recognition_lock = threading.Lock()
        self._silence_ms = silence_ms
        self._silence_samples = 0
        self._utterance_samples = 0
        self._has_speech = False
        self._last_partial = ''
        self._pending_audio = bytearray()
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
        self._utterance_samples = self._utterance_samples + len(samples) if self._has_speech else 0
        self._silence_samples = 0 if voiced else self._silence_samples + len(samples)
        with (operation("voice.stt") if self._has_speech else nullcontext()), self._recognition_lock:
            endpoint = self._recognizer.AcceptWaveform(audio) if audio else False
            wake = self._wake_recognizer
            if wake is not None and audio and wake.AcceptWaveform(audio):
                self._wake_hits.extend(_wake_hits(json.loads(wake.Result())))
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
            if wake is not None:
                self._wake_hits.extend(_wake_hits(json.loads(wake.FinalResult())))
            hits, self._wake_hits = self._wake_hits, []
        self._has_speech = False
        self._silence_samples = self._utterance_samples = 0
        self._last_partial = ''
        text = _apply_wake(result, hits)
        if self._debug_transcripts:
            logger.bind(
                event="voice_transcript_debug",
                recognized=result.get('text', ''),
                wake_hits=len(hits),
                committed_text=text,
            ).info("voice transcript debug")
        return STTTranscript(text=text, committed=True) if text else None

    async def send_audio(self, audio: bytes, *, commit: bool = False) -> None:
        if len(audio) % 2:
            raise ValueError("Local recognition expects PCM16 frames")
        self._pending_audio.extend(audio)
        # Browser worklets send roughly 2.7 ms frames. Batch 100 ms to avoid
        # scheduling hundreds of native thread jobs per second.
        committed = False
        while len(self._pending_audio) >= 3200:
            chunk = bytes(self._pending_audio[:3200])
            del self._pending_audio[:3200]
            committed = commit and not self._pending_audio
            transcript = await asyncio.to_thread(self._process, chunk, committed)
            if transcript is not None:
                await self._transcripts.put(transcript)
        if commit and not committed:
            chunk = bytes(self._pending_audio)
            self._pending_audio.clear()
            transcript = await asyncio.to_thread(self._process, chunk, True)
            if transcript is not None:
                await self._transcripts.put(transcript)

    async def receive_transcript(self) -> STTTranscript:
        return await self._transcripts.get()
