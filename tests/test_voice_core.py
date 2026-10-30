from __future__ import annotations

import io
import wave
from array import array

from sirah.core.voice import (
    FRAME_BYTES,
    AdaptiveSpeechDetector,
    PhraseBuffer,
    SpeechDetector,
    State,
    Supervisor,
    VoiceSegmenter,
    rms,
    wav_bytes,
)

SILENCE = b"\x00" * FRAME_BYTES
TONE = b"\x00\x10" * (FRAME_BYTES // 2)


def _detector(frame: bytes) -> bool:
    return frame == TONE


def test_rms_separates_silence_from_tone() -> None:
    assert rms(SILENCE) == 0
    assert rms(TONE) > 3000
    assert rms(b"") == 0


def test_segmenter_starts_with_prebuffer_and_ends_on_silence() -> None:
    segmenter = VoiceSegmenter(
        _detector, start_frames=2, silence_ms=40, prebuffer_ms=20, max_turn_ms=1000
    )
    assert segmenter.feed(SILENCE) is None
    for _ in range(17):
        assert segmenter.feed(TONE) is None
    assert segmenter.feed(SILENCE) is None
    audio = segmenter.feed(SILENCE)  # 40 ms de silencio: fin
    assert audio is not None

    with wave.open(io.BytesIO(audio), "rb") as wav:
        assert wav.getframerate() == 16000
        assert wav.getnchannels() == 1
        assert wav.getsampwidth() == 2
        assert wav.getnframes() > 0


def test_segmenter_ignores_silence_and_caps_the_turn() -> None:
    silent = VoiceSegmenter(_detector, start_frames=1, silence_ms=1000, max_turn_ms=60)
    assert all(silent.feed(SILENCE) is None for _ in range(10))

    capped = VoiceSegmenter(_detector, start_frames=1, silence_ms=1000, max_turn_ms=40)
    assert capped.feed(TONE) is None
    assert capped.feed(TONE) is None


def test_segmenter_reset_forgets_a_partial_turn() -> None:
    segmenter = VoiceSegmenter(_detector, start_frames=1, silence_ms=20)
    assert segmenter.feed(TONE) is None
    segmenter.reset()
    assert segmenter.feed(SILENCE) is None
    assert segmenter.feed(TONE) is None


def test_wav_bytes_keeps_the_pcm() -> None:
    with wave.open(io.BytesIO(wav_bytes(SILENCE * 2)), "rb") as wav:
        assert wav.getnframes() == 640
        assert wav.readframes(wav.getnframes()) == SILENCE * 2


def test_speech_detector_uses_the_rms_threshold() -> None:
    detector = SpeechDetector(min_rms=500)
    assert detector.is_speech(SILENCE) is False
    assert detector.is_speech(TONE) is True


def test_segmenter_accepts_the_real_speech_detector(monkeypatch) -> None:
    detector = SpeechDetector(min_rms=500)
    monkeypatch.setattr(detector, "_vad", None)
    segmenter = VoiceSegmenter(detector, start_frames=1, silence_ms=20, prebuffer_ms=20)
    for _ in range(16):
        assert segmenter.feed(TONE) is None
    assert segmenter.feed(SILENCE) is not None


def test_phrase_buffer_streams_sentences() -> None:
    buffer = PhraseBuffer()
    assert buffer.feed("Hola") == []
    assert buffer.feed(", mundo. ¿Qué") == ["Hola, mundo."]
    assert buffer.feed(" tal? ") == ["¿Qué tal?"]
    assert buffer.finish() == []


def test_phrase_buffer_does_not_split_after_an_abbreviation() -> None:
    buffer = PhraseBuffer()
    assert buffer.feed("Son las 3 p. m. y") == []
    assert buffer.feed(" volvemos. Hola. ") == ["Son las 3 p. m. y volvemos.", "Hola."]


def test_phrase_buffer_cuts_long_text_without_punctuation() -> None:
    buffer = PhraseBuffer(max_chars=20)
    phrases = buffer.feed("palabra " * 6)
    assert phrases
    assert all(len(phrase) <= 20 for phrase in phrases)


def test_segmenter_discards_short_voice() -> None:
    segmenter = VoiceSegmenter(
        _detector, start_frames=2, silence_ms=40, prebuffer_ms=20, max_turn_ms=1000
    )
    for _ in range(3):
        assert segmenter.feed(TONE) is None
    assert segmenter.feed(SILENCE) is None
    audio = segmenter.feed(SILENCE)
    assert audio is None


def test_segmenter_keeps_long_voice() -> None:
    segmenter = VoiceSegmenter(
        _detector, start_frames=2, silence_ms=40, prebuffer_ms=20, max_turn_ms=10000
    )
    for _ in range(20):
        assert segmenter.feed(TONE) is None
    assert segmenter.feed(SILENCE) is None
    audio = segmenter.feed(SILENCE)
    assert audio is not None
    seen: list[State] = []

    class Eyes:
        def on_state(self, state: State) -> None:
            seen.append(state)

        def on_actions(self, actions: object) -> None:
            seen.append(actions)  # type: ignore[arg-type]

        def close(self) -> None:
            seen.append(State.IDLE)

    supervisor = Supervisor(Eyes())
    supervisor.set(State.LISTENING)
    supervisor.actions(("blink",))
    supervisor.close()
    assert seen[:2] == [State.LISTENING, ("blink",)]

    null = Supervisor()
    null.set(State.SPEAKING)
    null.actions(())
    null.close()
    assert null.state is State.SPEAKING


def _level(value: int) -> bytes:
    return array("h", [value] * (FRAME_BYTES // 2)).tobytes()


def _calibrate(detector, value: int = 3000, frames: int = 25) -> None:
    for _ in range(10 + frames):
        assert detector(_level(value)) is False


def test_adaptive_detector_separates_noise_from_voice() -> None:
    detector = AdaptiveSpeechDetector()
    _calibrate(detector)
    assert detector.noise_floor == 3000
    assert detector.start_threshold == 4800
    assert detector.end_threshold == 3600
    assert detector(_level(3000)) is False
    assert detector(_level(12000)) is True
    assert detector(_level(3400)) is False


def test_adaptive_detector_never_reports_constant_noise_as_voice() -> None:
    detector = AdaptiveSpeechDetector()
    _calibrate(detector)
    assert [detector(_level(3000)) for _ in range(300)] == [False] * 300


def test_adaptive_detector_ignores_pure_silence() -> None:
    detector = AdaptiveSpeechDetector()
    assert [detector(SILENCE) for _ in range(100)] == [False] * 100


def test_adaptive_floor_persists_across_sessions() -> None:
    detector = AdaptiveSpeechDetector()
    _calibrate(detector)
    detector.start_session()
    for _ in range(10):
        assert detector(_level(3000)) is False
    assert detector.noise_floor == 3000
    assert detector(_level(12000)) is True


def test_adaptive_detector_recalibrates_after_a_long_silence() -> None:
    detector = AdaptiveSpeechDetector()
    _calibrate(detector)
    for _ in range(250):  # 5 s de silencio estable
        assert detector(_level(3000)) is False
    _calibrate(detector, value=5000)
    assert detector.noise_floor == 5000
    assert detector.pending_warning is not None
    assert "ganancia" in detector.pending_warning


def test_segmenter_counts_the_start_frames_as_voice() -> None:
    segmenter = VoiceSegmenter(
        _detector, start_frames=17, silence_ms=20, prebuffer_ms=400, max_turn_ms=10000
    )
    for _ in range(16):
        assert segmenter.feed(TONE) is None
    assert segmenter.feed(TONE) is None
    audio = segmenter.feed(SILENCE)
    assert audio is not None


def test_segmenter_discards_a_constant_noise_turn() -> None:
    segmenter = VoiceSegmenter(
        lambda frame: True, start_frames=1, silence_ms=400, prebuffer_ms=0, max_turn_ms=100
    )
    results = [segmenter.feed(TONE) for _ in range(6)]
    assert results[-1] is None
    assert segmenter.last_discard == "noise"


def test_segmenter_reports_a_short_turn(caplog) -> None:
    segmenter = VoiceSegmenter(
        _detector, start_frames=2, silence_ms=20, prebuffer_ms=20, max_turn_ms=1000
    )
    for _ in range(3):
        segmenter.feed(TONE)
    segmenter.feed(SILENCE)
    assert segmenter.feed(SILENCE) is None
    assert segmenter.last_discard == "short"


def test_high_noise_warning_names_the_exact_commands() -> None:
    detector = AdaptiveSpeechDetector()
    _calibrate(detector)

    warning = detector.pending_warning or ""

    assert "alsamixer -c 0" in warning and "(F4)" in warning
    assert "pavucontrol" in warning and "Grabación" in warning
    assert "sirah voice --check" in warning and "< 1500" in warning
