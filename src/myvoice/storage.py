from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from .errors import JobStateError, VoiceProfileError
from .models import GenerationJob, VoiceProfile


def atomic_write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


class VoiceProfileRepository:
    def __init__(self, root: Path):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def save(self, profile: VoiceProfile, replace: bool = False) -> Path:
        destination = self.root / profile.name
        profile_path = destination / "profile.json"
        if profile_path.exists() and not replace:
            raise VoiceProfileError(f"Voice profile '{profile.name}' already exists")
        destination.mkdir(parents=True, exist_ok=True)
        atomic_write_json(profile_path, profile.to_dict())
        return destination

    def get(self, name: str) -> VoiceProfile:
        path = self.root / name / "profile.json"
        if not path.is_file():
            raise VoiceProfileError(f"Voice profile '{name}' was not found")
        try:
            return VoiceProfile.from_dict(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
            raise VoiceProfileError(f"Voice profile '{name}' is invalid: {exc}") from exc

    def list(self) -> list[VoiceProfile]:
        result: list[VoiceProfile] = []
        for path in sorted(self.root.glob("*/profile.json")):
            try:
                result.append(VoiceProfile.from_dict(json.loads(path.read_text(encoding="utf-8"))))
            except (OSError, ValueError, TypeError, json.JSONDecodeError):
                continue
        return result

    def delete(self, name: str) -> None:
        destination = (self.root / name).resolve()
        if destination.parent != self.root.resolve() or not destination.is_dir():
            raise VoiceProfileError(f"Voice profile '{name}' was not found")
        import shutil
        shutil.rmtree(destination)


class JobRepository:
    def __init__(self, root: Path):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def job_dir(self, job_id: str) -> Path:
        destination = (self.root / job_id).resolve()
        if destination.parent != self.root.resolve():
            raise JobStateError("Invalid job id")
        return destination

    def save(self, job: GenerationJob) -> Path:
        destination = self.job_dir(job.id)
        destination.mkdir(parents=True, exist_ok=True)
        atomic_write_json(destination / "job.json", job.to_dict())
        return destination

    def get(self, job_id: str) -> GenerationJob:
        path = self.job_dir(job_id) / "job.json"
        if not path.is_file():
            raise JobStateError(f"Job '{job_id}' was not found")
        try:
            return GenerationJob.from_dict(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
            raise JobStateError(f"Job '{job_id}' is invalid: {exc}") from exc

    def list(self) -> list[GenerationJob]:
        jobs: list[GenerationJob] = []
        for path in sorted(self.root.glob("*/job.json"), reverse=True):
            try:
                jobs.append(GenerationJob.from_dict(json.loads(path.read_text(encoding="utf-8"))))
            except (OSError, ValueError, TypeError, json.JSONDecodeError):
                continue
        return jobs
