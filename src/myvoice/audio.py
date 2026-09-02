from __future__ import annotations

import hashlib
import json
import math
import os
import re
import shutil
import struct
import subprocess
import tempfile
import wave
from array import array
from pathlib import Path
from dataclasses import replace
from typing import Iterable

from .errors import AudioToolError, InputValidationError
from .models import AudioMetadata, ValidationIssue


SUPPORTED_EXTENSIONS = {".wav", ".wave", ".flac", ".aac", ".m4a", ".mp3", ".ogg"}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def executable(name: str) -> str | None:
    return shutil.which(name)


def run_checked(args: list[str], *, error_context: str) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(args, check=True, text=True, capture_output=True)
    except FileNotFoundError as exc:
        raise AudioToolError(f"Required executable was not found: {args[0]}") from exc
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or "unknown error").strip()
        raise AudioToolError(f"{error_context}: {detail}") from exc


class AudioProbe:
    def probe(self, path: Path) -> AudioMetadata:
        path = path.expanduser().resolve()
        if not path.is_file():
            raise InputValidationError(f"Audio file does not exist: {path}")
        if executable("ffprobe"):
            metadata = self._probe_ffmpeg(path)
            if executable("ffmpeg"):
                peak, silence_ratio = self._quality_ffmpeg(path, metadata.duration_seconds)
                metadata = replace(metadata, peak_dbfs=peak, silence_ratio=silence_ratio)
            return metadata
        if path.suffix.lower() in {".wav", ".wave"}:
            return self._probe_wave(path)
        raise AudioToolError("ffprobe is required for non-WAV audio files")

    def _probe_ffmpeg(self, path: Path) -> AudioMetadata:
        result = run_checked(
            [
                "ffprobe", "-v", "error", "-select_streams", "a:0",
                "-show_entries", "stream=codec_name,sample_rate,channels:format=duration",
                "-of", "json", str(path),
            ],
            error_context=f"Could not inspect {path.name}",
        )
        try:
            payload = json.loads(result.stdout)
            stream = payload["streams"][0]
            duration = float(payload["format"]["duration"])
            return AudioMetadata(
                path=str(path), duration_seconds=duration,
                sample_rate=int(stream["sample_rate"]), channels=int(stream["channels"]),
                codec=str(stream["codec_name"]), sha256=sha256_file(path),
            )
        except (KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise AudioToolError(f"ffprobe returned invalid metadata for {path.name}") from exc

    def _probe_wave(self, path: Path) -> AudioMetadata:
        try:
            with wave.open(str(path), "rb") as reader:
                frames = reader.getnframes()
                rate = reader.getframerate()
                channels = reader.getnchannels()
                sample_width = reader.getsampwidth()
                raw = reader.readframes(frames)
        except (wave.Error, OSError) as exc:
            raise InputValidationError(f"Invalid WAV file {path.name}: {exc}") from exc
        peak_dbfs = self._peak_dbfs(raw, sample_width)
        return AudioMetadata(
            path=str(path), duration_seconds=frames / rate if rate else 0.0,
            sample_rate=rate, channels=channels, codec=f"pcm_s{sample_width * 8}le",
            peak_dbfs=peak_dbfs, sha256=sha256_file(path),
        )

    def _quality_ffmpeg(self, path: Path, duration: float) -> tuple[float | None, float | None]:
        result = run_checked(
            [
                "ffmpeg", "-nostdin", "-hide_banner", "-i", str(path),
                "-af", "silencedetect=noise=-45dB:d=0.35,volumedetect", "-f", "null", "-",
            ],
            error_context=f"Could not analyze {path.name}",
        )
        max_match = re.search(r"max_volume:\s*(-?(?:inf|\d+(?:\.\d+)?))\s*dB", result.stderr)
        peak = None
        if max_match:
            peak = float("-inf") if max_match.group(1) == "-inf" else float(max_match.group(1))
        silence_starts = [float(value) for value in re.findall(r"silence_start:\s*([0-9.]+)", result.stderr)]
        silence_ends = [
            (float(end), float(length))
            for end, length in re.findall(r"silence_end:\s*([0-9.]+)\s*\|\s*silence_duration:\s*([0-9.]+)", result.stderr)
        ]
        silence_seconds = sum(length for _, length in silence_ends)
        if len(silence_starts) > len(silence_ends) and duration > 0:
            silence_seconds += max(0.0, duration - silence_starts[-1])
        ratio = min(1.0, silence_seconds / duration) if duration > 0 else None
        return peak, ratio

    @staticmethod
    def _peak_dbfs(raw: bytes, sample_width: int) -> float | None:
        if not raw or sample_width not in (1, 2, 4):
            return None
        if sample_width == 1:
            values = [abs(value - 128) for value in raw]
            full_scale = 127
        elif sample_width == 2:
            values = array("h")
            values.frombytes(raw)
            values = [abs(value) for value in values]
            full_scale = 32767
        else:
            values = array("i")
            values.frombytes(raw)
            values = [abs(value) for value in values]
            full_scale = 2147483647
        peak = max(values, default=0)
        return 20 * math.log10(peak / full_scale) if peak else float("-inf")


class AudioValidator:
    def __init__(
        self,
        probe: AudioProbe | None = None,
        minimum_files: int | None = None,
        minimum_seconds: float | None = None,
    ):
        self.probe = probe or AudioProbe()
        self.minimum_files = minimum_files
        self.minimum_seconds = minimum_seconds

    def discover(self, directory: Path) -> list[Path]:
        directory = directory.expanduser().resolve()
        if not directory.is_dir():
            raise InputValidationError(f"Sample directory does not exist: {directory}")
        return sorted(path for path in directory.iterdir() if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS)

    def validate(self, files: Iterable[Path]) -> tuple[list[AudioMetadata], list[ValidationIssue]]:
        file_list = list(files)
        issues: list[ValidationIssue] = []
        if not file_list:
            issues.append(ValidationIssue("fail", "audio.no_files", "At least one supported audio file is required"))
        elif self.minimum_files is not None and len(file_list) < self.minimum_files:
            issues.append(ValidationIssue("fail", "audio.minimum_files", f"At least {self.minimum_files} audio files are required; found {len(file_list)}"))
        metadata: list[AudioMetadata] = []
        for path in file_list:
            try:
                item = self.probe.probe(path)
                metadata.append(item)
                if self.minimum_seconds is not None and item.duration_seconds + 1e-6 < self.minimum_seconds:
                    issues.append(ValidationIssue("fail", "audio.minimum_duration", f"Audio must be at least {self.minimum_seconds:.1f}s; found {item.duration_seconds:.2f}s", str(path)))
                if item.peak_dbfs is not None and item.peak_dbfs > -0.1:
                    issues.append(ValidationIssue("warning", "audio.possible_clipping", f"Peak level is {item.peak_dbfs:.2f} dBFS", str(path)))
                if item.peak_dbfs is not None and item.peak_dbfs < -35:
                    issues.append(ValidationIssue("warning", "audio.low_level", f"Peak level is very low at {item.peak_dbfs:.2f} dBFS", str(path)))
                if item.silence_ratio is not None and item.silence_ratio >= 0.8:
                    issues.append(ValidationIssue("fail", "audio.excessive_silence", f"Silence ratio is {item.silence_ratio:.0%}", str(path)))
                elif item.silence_ratio is not None and item.silence_ratio >= 0.5:
                    issues.append(ValidationIssue("warning", "audio.high_silence", f"Silence ratio is {item.silence_ratio:.0%}", str(path)))
            except (InputValidationError, AudioToolError) as exc:
                issues.append(ValidationIssue("fail", "audio.invalid", str(exc), str(path)))
        return metadata, issues

    @staticmethod
    def raise_for_failures(issues: Iterable[ValidationIssue]) -> None:
        failures = [issue for issue in issues if issue.severity == "fail"]
        if failures:
            detail = "\n".join(f"- {item.path + ': ' if item.path else ''}{item.message}" for item in failures)
            raise InputValidationError(f"Audio validation failed:\n{detail}")


class AudioPreprocessor:
    def __init__(self, sample_rate: int = 24000):
        self.sample_rate = sample_rate

    def process(self, source: Path, destination: Path) -> Path:
        destination.parent.mkdir(parents=True, exist_ok=True)
        if executable("ffmpeg"):
            run_checked(
                [
                    "ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
                    "-i", str(source), "-map_metadata", "-1", "-ac", "1", "-ar", str(self.sample_rate),
                    "-af", (
                        "silenceremove=start_periods=1:start_duration=0.05:start_threshold=-50dB,"
                        "areverse,silenceremove=start_periods=1:start_duration=0.05:start_threshold=-50dB,areverse"
                    ),
                    "-c:a", "pcm_s16le", str(destination),
                ],
                error_context=f"Could not preprocess {source.name}",
            )
            return destination
        if source.suffix.lower() not in {".wav", ".wave"}:
            raise AudioToolError("FFmpeg is required to preprocess non-WAV files")
        self._copy_wave_pcm16(source, destination)
        return destination

    def _copy_wave_pcm16(self, source: Path, destination: Path) -> None:
        try:
            with wave.open(str(source), "rb") as reader:
                if reader.getnchannels() != 1 or reader.getframerate() != self.sample_rate or reader.getsampwidth() != 2:
                    raise AudioToolError(
                        f"FFmpeg is unavailable and {source.name} is not mono {self.sample_rate} Hz PCM16 WAV"
                    )
                params = reader.getparams()
                frames = reader.readframes(reader.getnframes())
            with wave.open(str(destination), "wb") as writer:
                writer.setparams(params)
                writer.writeframes(frames)
        except wave.Error as exc:
            raise AudioToolError(f"Could not preprocess {source.name}: {exc}") from exc


def write_silence(path: Path, milliseconds: int, sample_rate: int = 24000) -> None:
    frames = max(0, round(sample_rate * milliseconds / 1000))
    with wave.open(str(path), "wb") as writer:
        writer.setnchannels(1)
        writer.setsampwidth(2)
        writer.setframerate(sample_rate)
        writer.writeframes(b"\x00\x00" * frames)


class AudioAssembler:
    def __init__(self, sample_rate: int = 24000):
        self.sample_rate = sample_rate

    def concatenate(self, segments: list[tuple[Path, int]], destination: Path) -> Path:
        if not segments:
            raise AudioToolError("No audio segments are available to assemble")
        destination.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary_name = tempfile.mkstemp(
            prefix=f".{destination.stem}.", suffix=".wav", dir=destination.parent
        )
        os.close(fd)
        temporary = Path(temporary_name)
        try:
            if executable("ffmpeg"):
                self._concatenate_with_ffmpeg_normalization(segments, temporary)
            else:
                self._concatenate_pcm_wave(segments, temporary)
            os.replace(temporary, destination)
        finally:
            temporary.unlink(missing_ok=True)
        return destination

    def _concatenate_with_ffmpeg_normalization(
        self, segments: list[tuple[Path, int]], destination: Path
    ) -> None:
        with tempfile.TemporaryDirectory(prefix="myvoice-assembly-", dir=destination.parent) as temp_dir:
            normalized: list[tuple[Path, int]] = []
            for index, (source, pause_ms) in enumerate(segments, 1):
                target = Path(temp_dir) / f"{index:05d}.wav"
                run_checked(
                    [
                        "ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
                        "-i", str(source), "-map_metadata", "-1", "-ac", "1",
                        "-ar", str(self.sample_rate), "-c:a", "pcm_s16le", str(target),
                    ],
                    error_context=f"Could not normalize generated segment {source.name}",
                )
                normalized.append((target, pause_ms))
            self._concatenate_pcm_wave(normalized, destination)

    @staticmethod
    def _concatenate_pcm_wave(segments: list[tuple[Path, int]], destination: Path) -> None:
        first_path = segments[0][0]
        try:
            with wave.open(str(first_path), "rb") as first_reader:
                expected = (
                    first_reader.getnchannels(),
                    first_reader.getsampwidth(),
                    first_reader.getframerate(),
                )
        except (wave.Error, OSError) as exc:
            raise AudioToolError(f"Invalid segment WAV {first_path.name}: {exc}") from exc

        try:
            with wave.open(str(destination), "wb") as output:
                output.setnchannels(expected[0])
                output.setsampwidth(expected[1])
                output.setframerate(expected[2])
                for path, pause_ms in segments:
                    try:
                        with wave.open(str(path), "rb") as reader:
                            current = (
                                reader.getnchannels(),
                                reader.getsampwidth(),
                                reader.getframerate(),
                            )
                            if current != expected:
                                raise AudioToolError(f"Segment format mismatch: {path.name}")
                            output.writeframes(reader.readframes(reader.getnframes()))
                    except (wave.Error, OSError) as exc:
                        raise AudioToolError(f"Invalid segment WAV {path.name}: {exc}") from exc
                    pause_frames = round(expected[2] * pause_ms / 1000)
                    output.writeframes(
                        b"\x00" * pause_frames * expected[0] * expected[1]
                    )
        except wave.Error as exc:
            raise AudioToolError(f"Could not write master WAV: {exc}") from exc


class AACEncoder:
    def encode(self, source_wav: Path, destination: Path, bitrate: str = "192k") -> Path:
        if not executable("ffmpeg"):
            raise AudioToolError("FFmpeg is required to encode AAC-LC output")
        destination.parent.mkdir(parents=True, exist_ok=True)
        run_checked(
            [
                "ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y", "-i", str(source_wav),
                "-c:a", "aac", "-profile:a", "aac_low", "-b:a", bitrate, "-ac", "1", "-f", "adts", str(destination),
            ],
            error_context="AAC-LC encoding failed",
        )
        return destination


def generate_test_tone(path: Path, duration: float = 0.2, sample_rate: int = 24000, frequency: float = 220.0) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frames = int(sample_rate * duration)
    with wave.open(str(path), "wb") as writer:
        writer.setnchannels(1)
        writer.setsampwidth(2)
        writer.setframerate(sample_rate)
        values = (int(2000 * math.sin(2 * math.pi * frequency * index / sample_rate)) for index in range(frames))
        writer.writeframes(b"".join(struct.pack("<h", value) for value in values))
