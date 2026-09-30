from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FRONTEND = ROOT / "frontend" / "src"
BACKEND = ROOT / "backend" / "app"


def test_legacy_voice_subsystem_is_gone():
    obsolete = [
        FRONTEND / "voice.ts",
        ROOT / "frontend" / "e2e" / "deus-voice-latency.spec.ts",
        BACKEND / "api" / "voice.py",
        BACKEND / "services" / "voice.py",
        BACKEND / "schemas" / "voice.py",
        ROOT / "backend" / "tests" / "test_voice.py",
    ]
    assert [str(path.relative_to(ROOT)) for path in obsolete if path.exists()] == []


def test_production_frontend_has_no_browser_speech_recognition_or_legacy_voice_endpoints():
    source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in FRONTEND.rglob("*")
        if path.suffix in {".ts", ".tsx"}
    )

    assert "SpeechRecognition" not in source
    assert "webkitSpeechRecognition" not in source
    assert "/voice/synthesize" not in source
    assert "/voice/transcribe" not in source
