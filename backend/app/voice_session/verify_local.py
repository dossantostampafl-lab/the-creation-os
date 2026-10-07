"""Exercise actual cached models before activating local production speech."""
from __future__ import annotations

import asyncio
import json
import math
import time

from app.config import settings
from app.voice_session.local import VoskRealtimeSTT, get_local_engine


async def main() -> None:
    import numpy as np

    started = time.monotonic()
    engine = await get_local_engine()
    loaded_ms = round((time.monotonic() - started) * 1000)
    text = 'Deus, quanto é dois mais dois?'
    started = time.monotonic()
    audio = await engine.synthesize(text)
    synthesis_ms = round((time.monotonic() - started) * 1000)
    pcm = np.frombuffer(audio, dtype='<i2')
    converted = np.interp(np.arange(round(len(pcm) * 2 / 3)) * 1.5,
                          np.arange(len(pcm)), pcm).astype('<i2').tobytes()
    final_text = ''
    started = time.monotonic()
    silence_ms = settings.deus_local_voice_silence_ms
    async with VoskRealtimeSTT(engine.recognizer(), silence_ms=silence_ms) as stt:
        for offset in range(0, len(converted), 3200):
            await stt.send_audio(converted[offset:offset + 3200])
            while not stt._transcripts.empty():
                transcript = await stt.receive_transcript()
                if transcript.committed:
                    final_text += ' ' + transcript.text
        # The speaker then stops talking for longer than the configured end-of-sentence pause,
        # exactly as the live gateway sees it; a shorter tail would end before the commit.
        for _ in range(math.ceil(silence_ms / 100) + 5):
            await stt.send_audio(b'\x00' * 3200)
            while not stt._transcripts.empty():
                transcript = await stt.receive_transcript()
                if transcript.committed:
                    final_text += ' ' + transcript.text
    final_text = final_text.strip()
    recognition_cpu_ms = round((time.monotonic() - started) * 1000)
    if not audio or 'deus' not in final_text.lower() or final_text.lower().count('dois') != 2:
        raise RuntimeError('Local speech validation failed: ' + final_text)
    print(json.dumps({'voice': 'pm_santa', 'sample_rate': 24000,
                      'audio_bytes': len(audio), 'models_loaded_ms': loaded_ms,
                      'synthesis_ms': synthesis_ms, 'recognition_cpu_ms': recognition_cpu_ms,
                      'synthetic_transcript': final_text,
                      'note': 'Synthetic input; CPU timings exclude human microphone and network latency.'}), flush=True)


if __name__ == '__main__':
    asyncio.run(main())
