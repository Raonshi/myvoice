from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class AudioMetadata:
    path: str
    duration_seconds: float
    sample_rate: int
    channels: int
    codec: str
    peak_dbfs: float | None = None
    silence_ratio: float | None = None
    sha256: str | None = None


@dataclass(frozen=True)
class ValidationIssue:
    severity: str
    code: str
    message: str
    path: str | None = None


@dataclass
class VoiceProfile:
    id: str
    name: str
    language: str
    engine: str
    engine_model: str
    created_at: str
    references: list[str]
    primary_reference: str
    sample_count: int
    total_duration_seconds: float
    consent_confirmed: bool
    schema_version: int = 1
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "VoiceProfile":
        if data.get("schema_version") != 1:
            raise ValueError("Unsupported VoiceProfile schema version")
        return cls(**data)


@dataclass
class DocumentBlock:
    id: str
    kind: str
    text: str
    pause_after_ms: int


@dataclass
class SpeechDocument:
    source_path: str
    source_hash: str
    blocks: list[DocumentBlock]


@dataclass
class SpeechSegment:
    id: str
    order: int
    source_block_id: str
    source_text: str
    normalized_text: str
    pause_after_ms: int
    content_hash: str
    status: str = "pending"
    revision: int = 1
    audio_path: str | None = None
    duration_seconds: float | None = None
    attempts: int = 0
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SpeechSegment":
        return cls(**data)


@dataclass
class GenerationJob:
    id: str
    status: str
    created_at: str
    updated_at: str
    script_path: str
    script_hash: str
    voice_name: str
    voice_id: str
    engine: str
    engine_model: str
    language: str
    device: str
    output_path: str
    keep_master_wav: bool
    segments: list[SpeechSegment]
    settings: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    schema_version: int = 1

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["segments"] = [segment.to_dict() for segment in self.segments]
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "GenerationJob":
        if data.get("schema_version") != 1:
            raise ValueError("Unsupported GenerationJob schema version")
        payload = dict(data)
        payload["segments"] = [SpeechSegment.from_dict(item) for item in data["segments"]]
        return cls(**payload)

    def touch(self, status: str | None = None) -> None:
        if status:
            self.status = status
        self.updated_at = utc_now()


@dataclass(frozen=True)
class SynthesisRequest:
    text: str
    language: str
    reference_audio: Path
    output_wav: Path
    device: str = "auto"
    seed: int | None = None
    exaggeration: float = 0.5
    cfg_weight: float = 0.5
    temperature: float = 0.8
