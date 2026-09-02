from __future__ import annotations

import shutil
import uuid
from datetime import datetime
from pathlib import Path
from typing import Callable

from .audio import AACEncoder, AudioAssembler, AudioPreprocessor, AudioProbe, AudioValidator
from .errors import InputValidationError, JobStateError, TTSError
from .models import GenerationJob, SynthesisRequest, VoiceProfile, utc_now
from .storage import JobRepository, VoiceProfileRepository
from .text_pipeline import KoreanTextNormalizer, PronunciationDictionary, ScriptParser, Segmenter
from .tts import TTSEngine, create_engine


ProgressCallback = Callable[[str, dict], None]


def _noop_progress(event: str, payload: dict) -> None:
    del event, payload


class EnrollmentService:
    def __init__(self, voices: VoiceProfileRepository, validator: AudioValidator | None = None, preprocessor: AudioPreprocessor | None = None):
        self.voices = voices
        self.validator = validator or AudioValidator()
        self.preprocessor = preprocessor or AudioPreprocessor()

    def enroll(
        self,
        samples_dir: Path,
        name: str,
        language: str = "ko",
        engine_name: str = "chatterbox_multilingual",
        consent_confirmed: bool = False,
        replace: bool = False,
        progress: ProgressCallback = _noop_progress,
    ) -> VoiceProfile:
        if not name or any(part in name for part in ("/", "\\", "..")):
            raise InputValidationError("Voice profile name must be a simple name without path separators")
        if not consent_confirmed:
            raise InputValidationError("Voice ownership/authorization consent must be confirmed")
        files = self.validator.discover(samples_dir)
        metadata, issues = self.validator.validate(files)
        for issue in issues:
            progress("validation.issue", {"severity": issue.severity, "message": issue.message, "path": issue.path})
        self.validator.raise_for_failures(issues)

        staging = self.voices.root / f".{name}.staging-{uuid.uuid4().hex[:8]}"
        references_dir = staging / "references"
        try:
            references: list[str] = []
            for index, item in enumerate(metadata, 1):
                destination = references_dir / f"{index:03d}.wav"
                self.preprocessor.process(Path(item.path), destination)
                references.append(str(Path("references") / destination.name))
                progress("enroll.reference", {"completed": index, "total": len(metadata), "source": item.path})
            longest = max(range(len(metadata)), key=lambda idx: metadata[idx].duration_seconds)
            profile = VoiceProfile(
                id=f"voice-{uuid.uuid4().hex}", name=name, language=language,
                engine=engine_name, engine_model="v3", created_at=utc_now(),
                references=references, primary_reference=references[longest],
                sample_count=len(metadata), total_duration_seconds=sum(item.duration_seconds for item in metadata),
                consent_confirmed=True,
                metadata={
                    "source_sha256": [item.sha256 for item in metadata],
                    "warnings": [issue.message for issue in issues if issue.severity == "warning"],
                    "profile_type": "reference_audio",
                },
            )
            final = self.voices.root / name
            if final.exists():
                if not replace:
                    raise InputValidationError(f"Voice profile '{name}' already exists")
                backup = self.voices.root / f".{name}.backup-{uuid.uuid4().hex[:8]}"
                final.rename(backup)
                try:
                    staging.rename(final)
                    shutil.rmtree(backup)
                except Exception:
                    if final.exists():
                        shutil.rmtree(final)
                    backup.rename(final)
                    raise
            else:
                staging.rename(final)
            self.voices.save(profile, replace=True)
            progress("enroll.completed", {"name": name, "samples": len(metadata)})
            return profile
        finally:
            if staging.exists():
                shutil.rmtree(staging)


class GenerationService:
    def __init__(
        self,
        voices: VoiceProfileRepository,
        jobs: JobRepository,
        engine_factory: Callable[[str], TTSEngine] = create_engine,
        probe: AudioProbe | None = None,
        assembler: AudioAssembler | None = None,
        encoder: AACEncoder | None = None,
    ):
        self.voices = voices
        self.jobs = jobs
        self.engine_factory = engine_factory
        self.probe = probe or AudioProbe()
        self.assembler = assembler or AudioAssembler()
        self.encoder = encoder or AACEncoder()

    def create_job(
        self,
        script: Path,
        voice_name: str,
        output: Path,
        device: str = "auto",
        pronunciation_dict: Path | None = None,
        max_chars: int = 180,
        keep_master_wav: bool = True,
        engine_override: str | None = None,
    ) -> GenerationJob:
        profile = self.voices.get(voice_name)
        document = ScriptParser().parse(script)
        pronunciation = PronunciationDictionary.load(pronunciation_dict)
        segments = Segmenter(max_chars=max_chars).segment(document, KoreanTextNormalizer(pronunciation))
        job_id = f"job-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}"
        engine_name = engine_override or profile.engine
        now = utc_now()
        job = GenerationJob(
            id=job_id, status="segmented", created_at=now, updated_at=now,
            script_path=str(script.expanduser().resolve()), script_hash=document.source_hash,
            voice_name=profile.name, voice_id=profile.id, engine=engine_name,
            engine_model=profile.engine_model, language=profile.language, device=device,
            output_path=str(output.expanduser().resolve()), keep_master_wav=keep_master_wav,
            segments=segments,
            settings={"max_chars": max_chars, "bitrate": "192k", "seed": None},
        )
        job_dir = self.jobs.save(job)
        shutil.copy2(script.expanduser().resolve(), job_dir / f"script.original{script.suffix.lower()}")
        (job_dir / "script.normalized.txt").write_text("\n\n".join(item.normalized_text for item in segments) + "\n", encoding="utf-8")
        return job

    def generate(self, job: GenerationJob, progress: ProgressCallback = _noop_progress, dry_run: bool = False) -> GenerationJob:
        if dry_run:
            progress("job.dry_run", {"job_id": job.id, "segments": len(job.segments)})
            return job
        profile = self.voices.get(job.voice_name)
        if profile.id != job.voice_id:
            raise JobStateError("Voice profile changed after this job was created")
        engine = self.engine_factory(job.engine)
        engine.validate_runtime()
        job_dir = self.jobs.job_dir(job.id)
        reference = self.voices.root / profile.name / profile.primary_reference
        if not reference.is_file():
            raise JobStateError(f"Voice reference is missing: {reference}")
        job.touch("generating")
        self.jobs.save(job)
        for segment in job.segments:
            target = job_dir / "segments" / f"{segment.id}-r{segment.revision}.wav"
            if segment.status == "completed" and segment.audio_path and (job_dir / segment.audio_path).is_file():
                progress("segment.cached", {"segment_id": segment.id})
                continue
            self._generate_segment(job, segment, target, reference, engine, progress)
        return self._assemble_and_encode(job, progress)

    def _generate_segment(self, job, segment, target, reference, engine, progress) -> None:
        maximum_attempts = 3
        last_error: Exception | None = None
        for attempt in range(1, maximum_attempts + 1):
            segment.attempts += 1
            progress("segment.started", {"segment_id": segment.id, "order": segment.order, "total": len(job.segments), "attempt": attempt})
            try:
                engine.synthesize(
                    SynthesisRequest(
                        text=segment.normalized_text, language=job.language,
                        reference_audio=reference, output_wav=target, device=job.device,
                        seed=job.settings.get("seed"),
                    )
                )
                metadata = self.probe.probe(target)
                if metadata.duration_seconds <= 0.05:
                    raise TTSError("Generated audio is unexpectedly short")
                segment.status = "completed"
                segment.audio_path = str(target.relative_to(self.jobs.job_dir(job.id)))
                segment.duration_seconds = metadata.duration_seconds
                segment.error = None
                job.touch()
                self.jobs.save(job)
                progress("segment.completed", {"segment_id": segment.id, "order": segment.order, "total": len(job.segments)})
                return
            except Exception as exc:
                last_error = exc
                if target.exists():
                    target.unlink()
        segment.status = "failed"
        segment.error = str(last_error)
        job.error = f"{segment.id}: {last_error}"
        job.touch("failed")
        self.jobs.save(job)
        raise TTSError(f"{segment.id} generation failed after {maximum_attempts} attempts: {last_error}")

    def _assemble_and_encode(self, job: GenerationJob, progress: ProgressCallback) -> GenerationJob:
        job_dir = self.jobs.job_dir(job.id)
        segment_files: list[tuple[Path, int]] = []
        for segment in job.segments:
            if segment.status != "completed" or not segment.audio_path:
                raise JobStateError(f"Segment {segment.id} is not complete")
            segment_files.append((job_dir / segment.audio_path, segment.pause_after_ms))
        master = job_dir / "master.wav"
        output = Path(job.output_path)
        try:
            job.touch("assembling")
            self.jobs.save(job)
            self.assembler.concatenate(segment_files, master)
            progress("job.assembled", {"job_id": job.id, "master": str(master)})
            job.touch("encoding")
            self.jobs.save(job)
            self.encoder.encode(master, output, bitrate=str(job.settings.get("bitrate", "192k")))
            if not job.keep_master_wav:
                master.unlink(missing_ok=True)
            job.error = None
            job.touch("completed")
            self.jobs.save(job)
            progress("job.completed", {"job_id": job.id, "output": str(output)})
            return job
        except Exception as exc:
            job.error = str(exc)
            job.touch("failed")
            self.jobs.save(job)
            progress("job.failed", {"job_id": job.id, "error": str(exc)})
            raise

    def resume(self, job_id: str, progress: ProgressCallback = _noop_progress) -> GenerationJob:
        job = self.jobs.get(job_id)
        if job.status == "completed":
            return job
        return self.generate(job, progress=progress)

    def regenerate(
        self,
        job_id: str,
        segment_id: str,
        text_override: str | None = None,
        progress: ProgressCallback = _noop_progress,
    ) -> GenerationJob:
        job = self.jobs.get(job_id)
        segment = next((item for item in job.segments if item.id == segment_id), None)
        if segment is None:
            raise JobStateError(f"Segment '{segment_id}' was not found in {job_id}")
        if text_override:
            segment.normalized_text = text_override.strip()
        segment.revision += 1
        segment.status = "pending"
        segment.audio_path = None
        segment.error = None
        job.touch("regenerating")
        self.jobs.save(job)
        return self.generate(job, progress=progress)
