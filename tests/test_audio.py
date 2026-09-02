from __future__ import annotations

from pathlib import Path

import pytest

from myvoice.audio import AACEncoder, AudioAssembler, AudioProbe, AudioValidator, ReferenceQualityScorer, executable, generate_test_tone, run_checked
from myvoice.errors import InputValidationError
from myvoice.models import AudioMetadata


def test_wave_probe_and_minimum_duration(tmp_path: Path) -> None:
    paths = []
    for index in range(5):
        path = tmp_path / f"{index}.wav"
        generate_test_tone(path, duration=0.12)
        paths.append(path)
    validator = AudioValidator(minimum_seconds=0.1)
    metadata, issues = validator.validate(paths)
    assert len(metadata) == 5
    assert not [item for item in issues if item.severity == "fail"]
    assert AudioProbe().probe(paths[0]).sample_rate == 24000


def test_empty_audio_list_fails() -> None:
    validator = AudioValidator()
    _, issues = validator.validate([])
    with pytest.raises(InputValidationError):
        validator.raise_for_failures(issues)


def test_default_validator_accepts_one_short_audio_file(tmp_path: Path) -> None:
    path = tmp_path / "one.wav"
    generate_test_tone(path, duration=0.08)

    metadata, issues = AudioValidator().validate([path])

    assert len(metadata) == 1
    assert not [item for item in issues if item.severity == "fail"]


def test_reference_quality_prefers_clean_prompt_in_useful_window() -> None:
    scorer = ReferenceQualityScorer()
    clean = AudioMetadata("clean.wav", 8.0, 24000, 1, "pcm_s16le", -3.0, 0.03)
    long_noisy = AudioMetadata("long.wav", 18.0, 24000, 1, "pcm_s16le", -0.05, 0.45)

    clean_score, clean_reasons = scorer.score(clean)
    noisy_score, _ = scorer.score(long_noisy)

    assert clean_score > noisy_score
    assert "권장 길이(6~10초)" in clean_reasons


def test_assembler_adds_pause(tmp_path: Path) -> None:
    first = tmp_path / "first.wav"
    second = tmp_path / "second.wav"
    output = tmp_path / "master.wav"
    generate_test_tone(first, duration=0.1)
    generate_test_tone(second, duration=0.1)
    AudioAssembler().concatenate([(first, 100), (second, 0)], output)
    assert 0.29 <= AudioProbe().probe(output).duration_seconds <= 0.31


@pytest.mark.skipif(not executable("ffmpeg") or not executable("ffprobe"), reason="FFmpeg is not installed")
def test_aac_lc_encoding(tmp_path: Path) -> None:
    source = tmp_path / "master.wav"
    output = tmp_path / "narration.aac"
    generate_test_tone(source, duration=0.5)
    AACEncoder().encode(source, output)
    result = run_checked(
        [
            "ffprobe", "-v", "error", "-select_streams", "a:0",
            "-show_entries", "stream=codec_name,profile,channels", "-of", "json", str(output),
        ],
        error_context="Could not inspect AAC test output",
    )
    assert '"codec_name": "aac"' in result.stdout
    assert '"profile": "LC"' in result.stdout
    assert '"channels": 1' in result.stdout


@pytest.mark.skipif(not executable("ffmpeg") or not executable("ffprobe"), reason="FFmpeg is not installed")
def test_assembler_normalizes_float32_chatterbox_wav(tmp_path: Path) -> None:
    pcm_source = tmp_path / "source-pcm16.wav"
    float_source = tmp_path / "source-float32.wav"
    master = tmp_path / "master.wav"
    generate_test_tone(pcm_source, duration=0.2)
    run_checked(
        [
            "ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
            "-i", str(pcm_source), "-c:a", "pcm_f32le", str(float_source),
        ],
        error_context="Could not create float32 WAV fixture",
    )

    AudioAssembler().concatenate([(float_source, 100), (float_source, 0)], master)

    result = run_checked(
        [
            "ffprobe", "-v", "error", "-select_streams", "a:0",
            "-show_entries", "stream=codec_name,sample_rate,channels", "-of", "json", str(master),
        ],
        error_context="Could not inspect normalized master WAV",
    )
    assert '"codec_name": "pcm_s16le"' in result.stdout
    assert '"sample_rate": "24000"' in result.stdout
    assert '"channels": 1' in result.stdout
    assert 0.49 <= AudioProbe().probe(master).duration_seconds <= 0.51


def test_assembler_does_not_leave_new_partial_master(tmp_path: Path, monkeypatch) -> None:
    broken = tmp_path / "broken.wav"
    broken.write_bytes(b"not a wave file")
    master = tmp_path / "master.wav"
    monkeypatch.setattr("myvoice.audio.executable", lambda _name: None)

    with pytest.raises(Exception, match="Invalid segment WAV"):
        AudioAssembler().concatenate([(broken, 0)], master)

    assert not master.exists()
