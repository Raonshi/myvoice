from __future__ import annotations

import shutil
from pathlib import Path

from myvoice.audio import AudioPreprocessor, AudioValidator, generate_test_tone
from myvoice.services import EnrollmentService, GenerationService
from myvoice.storage import JobRepository, VoiceProfileRepository
from myvoice.tts import TestToneEngine


class FakeAACEncoder:
    def encode(self, source_wav: Path, destination: Path, bitrate: str = "192k") -> Path:
        del bitrate
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_wav, destination)
        return destination


def test_enroll_generate_resume_and_regenerate(tmp_path: Path) -> None:
    samples = tmp_path / "samples"
    samples.mkdir()
    for index in range(5):
        generate_test_tone(samples / f"voice-{index}.wav", duration=0.12 + index * 0.01)

    voices = VoiceProfileRepository(tmp_path / "data" / "voices")
    jobs = JobRepository(tmp_path / "data" / "jobs")
    enrollment = EnrollmentService(
        voices,
        validator=AudioValidator(minimum_seconds=0.1),
        preprocessor=AudioPreprocessor(sample_rate=24000),
    )
    profile = enrollment.enroll(samples, "youtube", consent_confirmed=True)
    assert profile.sample_count == 5
    assert (voices.root / "youtube" / profile.primary_reference).is_file()

    script = tmp_path / "script.md"
    script.write_text("# 테스트\n\n첫 번째 문장입니다. 두 번째 문장입니다.\n\n마지막 문단입니다.", encoding="utf-8")
    output = tmp_path / "narration.aac"
    service = GenerationService(
        voices, jobs, engine_factory=lambda _: TestToneEngine(), encoder=FakeAACEncoder()
    )
    job = service.create_job(script, "youtube", output, engine_override="test_tone", max_chars=24)
    completed = service.generate(job)
    assert completed.status == "completed"
    assert output.is_file()
    before = {segment.id: segment.audio_path for segment in completed.segments}

    same = service.resume(completed.id)
    assert same.status == "completed"
    revised = service.regenerate(completed.id, "seg-0002", text_override="수정한 문장입니다.")
    assert revised.status == "completed"
    changed = next(segment for segment in revised.segments if segment.id == "seg-0002")
    assert changed.revision == 2
    assert changed.audio_path != before["seg-0002"]
    for segment in revised.segments:
        if segment.id != "seg-0002":
            assert segment.audio_path == before[segment.id]
