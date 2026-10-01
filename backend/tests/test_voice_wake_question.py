import pytest

from app.voice_session.session import SessionState, VoiceSession
from app.voice_session.stt import STTTranscript


@pytest.mark.parametrize(('spoken', 'expected'), [
    ('Deus, quanto é dez mais cinco?', 'quanto é dez mais cinco?'),
    ('Quanto é dez mais cinco, Deus?', 'Quanto é dez mais cinco'),
    ('Quanto é dez mais cinco, Deus, responda só o número.', 'Quanto é dez mais cinco responda só o número.'),
])
def test_first_voice_question_survives_wake_word_position(spoken, expected):
    session = VoiceSession('wake-position')
    decision = session.on_transcript(STTTranscript(text=spoken, committed=True))
    assert decision.command == expected
    assert decision.turn_id == 1
    assert decision.acknowledge
    assert session.state == SessionState.COMMITTING
