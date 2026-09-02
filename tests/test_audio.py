from __future__ import annotations

from pathlib import Path

import pytest

from myvoice.audio import AACEncoder, AudioAssembler, AudioProbe, AudioValidator, executable, generate_test_tone, run_checked
from myvoice.errors import InputValidationError


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


def test_minimum_file_count_fails(tmp_path: Path) -> None:
    path = tmp_path / "one.wav"
    generate_test_tone(path, duration=0.2)
    validator = AudioValidator(minimum_seconds=0.1)
    _, issues = validator.validate([path])
    with pytest.raises(InputValidationError):
        validator.raise_for_failures(issues)


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
