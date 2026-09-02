from __future__ import annotations

import json
import os
import tempfile
import uuid
from pathlib import Path

import yaml

from .errors import JobStateError, PronunciationDictionaryError, VoiceProfileError
from .models import GenerationJob, PronunciationDictionaryRecord, PronunciationEntry, VoiceProfile, utc_now
from .text_pipeline import load_pronunciation_dictionary_file


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


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
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


class PronunciationDictionaryRepository:
    def __init__(self, root: Path):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def save(
        self,
        *,
        name: str,
        language: str,
        entries: list[PronunciationEntry | dict[str, str]],
        dictionary_id: str | None = None,
    ) -> PronunciationDictionaryRecord:
        normalized_name = name.strip()
        normalized_language = language.strip()
        if not normalized_name:
            raise PronunciationDictionaryError("Pronunciation dictionary name is required")
        if not normalized_language:
            raise PronunciationDictionaryError("Pronunciation dictionary language is required")

        normalized_entries: list[PronunciationEntry] = []
        sources: set[str] = set()
        for item in entries:
            source_value = item.source if isinstance(item, PronunciationEntry) else item.get("source", "")
            pronunciation_value = (
                item.pronunciation if isinstance(item, PronunciationEntry) else item.get("pronunciation", "")
            )
            if not isinstance(source_value, str) or not isinstance(pronunciation_value, str):
                raise PronunciationDictionaryError("Pronunciation entries must contain string values")
            source = source_value.strip()
            pronunciation = pronunciation_value.strip()
            if not source or not pronunciation:
                raise PronunciationDictionaryError("Every pronunciation entry requires source and pronunciation text")
            if source in sources:
                raise PronunciationDictionaryError(f"Duplicate pronunciation source: {source}")
            sources.add(source)
            normalized_entries.append(PronunciationEntry(source, pronunciation))
        if not normalized_entries:
            raise PronunciationDictionaryError("Pronunciation dictionary must contain at least one entry")

        existing: PronunciationDictionaryRecord | None = None
        if dictionary_id:
            existing = self.get(dictionary_id)
        for item in self.list():
            if item.name.casefold() == normalized_name.casefold() and item.id != dictionary_id:
                raise PronunciationDictionaryError(f"Pronunciation dictionary '{normalized_name}' already exists")

        now = utc_now()
        record = PronunciationDictionaryRecord(
            id=dictionary_id or f"dictionary-{uuid.uuid4().hex}",
            name=normalized_name,
            language=normalized_language,
            entries=normalized_entries,
            created_at=existing.created_at if existing else now,
            updated_at=now,
        )
        payload = {
            "version": record.schema_version,
            "id": record.id,
            "name": record.name,
            "language": record.language,
            "created_at": record.created_at,
            "updated_at": record.updated_at,
            "entries": {entry.source: entry.pronunciation for entry in record.entries},
        }
        atomic_write_text(
            self._path(record.id),
            yaml.safe_dump(payload, allow_unicode=True, sort_keys=False),
        )
        return record

    def get(self, dictionary_id: str) -> PronunciationDictionaryRecord:
        path = self._path(dictionary_id)
        if not path.is_file():
            raise PronunciationDictionaryError(f"Pronunciation dictionary '{dictionary_id}' was not found")
        return self._read(path)

    def list(self) -> list[PronunciationDictionaryRecord]:
        records: list[PronunciationDictionaryRecord] = []
        for path in sorted(self.root.glob("*.yaml")):
            try:
                records.append(self._read(path))
            except PronunciationDictionaryError:
                continue
        return sorted(records, key=lambda item: item.name.casefold())

    def delete(self, dictionary_id: str) -> None:
        path = self._path(dictionary_id)
        if not path.is_file():
            raise PronunciationDictionaryError(f"Pronunciation dictionary '{dictionary_id}' was not found")
        path.unlink()

    def load_external(self, path: Path) -> PronunciationDictionaryRecord:
        language, entries = load_pronunciation_dictionary_file(path)
        now = utc_now()
        return PronunciationDictionaryRecord(
            id="",
            name=path.expanduser().stem,
            language=language,
            entries=[PronunciationEntry(source.strip(), pronunciation.strip()) for source, pronunciation in entries.items()],
            created_at=now,
            updated_at=now,
        )

    def path(self, dictionary_id: str) -> Path:
        record = self.get(dictionary_id)
        return self._path(record.id)

    def _path(self, dictionary_id: str) -> Path:
        destination = (self.root / f"{dictionary_id}.yaml").resolve()
        if not dictionary_id or destination.parent != self.root.resolve():
            raise PronunciationDictionaryError("Invalid pronunciation dictionary id")
        return destination

    def _read(self, path: Path) -> PronunciationDictionaryRecord:
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
            if not isinstance(data, dict) or data.get("version") != 1:
                raise ValueError("unsupported schema version")
            if data.get("id") != path.stem:
                raise ValueError("dictionary id does not match its file name")
            entries = data.get("entries")
            if not isinstance(entries, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in entries.items()):
                raise ValueError("entries must be string key/value pairs")
            return PronunciationDictionaryRecord(
                id=str(data["id"]),
                name=str(data["name"]),
                language=str(data["language"]),
                entries=[PronunciationEntry(source, pronunciation) for source, pronunciation in entries.items()],
                created_at=str(data["created_at"]),
                updated_at=str(data["updated_at"]),
                schema_version=int(data["version"]),
            )
        except (OSError, KeyError, TypeError, ValueError, yaml.YAMLError) as exc:
            raise PronunciationDictionaryError(f"Pronunciation dictionary '{path.stem}' is invalid: {exc}") from exc


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
