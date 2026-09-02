from __future__ import annotations

import argparse
import importlib.metadata
import importlib.util
import json
import platform
import shutil
import sys
from pathlib import Path
from typing import Any, TextIO

from . import __version__
from .audio import executable
from .config import AppPaths
from .errors import MyVoiceError
from .services import EnrollmentService, GenerationService
from .storage import JobRepository, VoiceProfileRepository
from .tts import inspect_mps_runtime, resolve_torch_device


def _dependencies() -> tuple[AppPaths, VoiceProfileRepository, JobRepository, GenerationService]:
    paths = AppPaths.discover()
    paths.ensure()
    voices = VoiceProfileRepository(paths.voices_dir)
    jobs = JobRepository(paths.jobs_dir)
    return paths, voices, jobs, GenerationService(voices, jobs)


def diagnostic_snapshot(paths: AppPaths) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []

    def add(name: str, status: str, detail: str) -> None:
        checks.append({"name": name, "status": status, "detail": detail})

    python_ok = (3, 11) <= sys.version_info[:2] < (3, 13)
    add("Python", "ok" if python_ok else "fail", sys.version.split()[0])
    add("FFmpeg", "ok" if executable("ffmpeg") else "fail", executable("ffmpeg") or "not found")
    add("FFprobe", "ok" if executable("ffprobe") else "fail", executable("ffprobe") or "not found")
    for package, module in (("chatterbox-tts", "chatterbox"), ("torch", "torch"), ("torchaudio", "torchaudio")):
        found = importlib.util.find_spec(module) is not None
        try:
            version = importlib.metadata.version(package) if found else "not installed"
        except importlib.metadata.PackageNotFoundError:
            version = "installed, version unknown"
        add(package, "ok" if found else "missing", version)

    selected_device = "cpu"
    if platform.system() == "Darwin":
        machine = platform.machine()
        native = machine == "arm64"
        add("macOS", "ok", f"{platform.mac_ver()[0] or 'unknown'} · {machine}")
        add("Apple Silicon", "ok" if native else "warning", "native arm64" if native else "Intel or Rosetta; synthesis will use CPU")
        if importlib.util.find_spec("torch") is not None:
            import torch

            mps = inspect_mps_runtime(torch)
            add("MPS built", "ok" if mps.built else "fail", str(mps.built))
            add("MPS available", "ok" if mps.available else "warning", str(mps.available))
            add("MPS operation", "ok" if mps.functional else "warning", mps.detail)
            selected_device = resolve_torch_device("auto", torch, system_name="Darwin", machine=machine)
            add("Auto device", "ok" if selected_device == "mps" else "warning", selected_device)
    add("Data directory", "ok", str(paths.data_dir))
    free = shutil.disk_usage(paths.data_dir).free / (1024**3)
    add("Free disk", "ok" if free >= 5 else "warning", f"{free:.1f} GiB")
    return {"version": __version__, "auto_device": selected_device, "checks": checks}


class DesktopAPI:
    def __init__(self, output: TextIO = sys.stdout):
        self.output = output

    def emit(self, event_type: str, **payload: Any) -> None:
        print(json.dumps({"type": event_type, **payload}, ensure_ascii=False), file=self.output, flush=True)

    def progress(self, event: str, payload: dict) -> None:
        self.emit("progress", event=event, payload=payload)

    def execute(self, request: dict[str, Any]) -> dict[str, Any]:
        operation = request.get("operation")
        payload = request.get("payload") or {}
        paths, voices, jobs, service = _dependencies()
        if operation == "snapshot":
            return {
                "version": __version__, "data_dir": str(paths.data_dir),
                "voices": [item.to_dict() for item in voices.list()],
                "jobs": [item.to_dict() for item in jobs.list()],
            }
        if operation == "doctor":
            return diagnostic_snapshot(paths)
        if operation == "enroll":
            profile = EnrollmentService(voices).enroll(
                Path(payload["samples_dir"]), name=payload["name"],
                language=payload.get("language", "ko"),
                engine_name=payload.get("engine", "chatterbox_multilingual"),
                consent_confirmed=bool(payload.get("consent_confirmed")),
                replace=bool(payload.get("replace")), progress=self.progress,
            )
            return profile.to_dict()
        if operation == "speak":
            pronunciation = payload.get("pronunciation_dict")
            job = service.create_job(
                Path(payload["script"]), payload["voice"], Path(payload["output"]),
                device=payload.get("device", "auto"),
                pronunciation_dict=Path(pronunciation) if pronunciation else None,
                max_chars=int(payload.get("max_chars", 180)),
                keep_master_wav=bool(payload.get("keep_master_wav", True)),
                engine_override=payload.get("engine"),
            )
            return service.generate(job, progress=self.progress, dry_run=bool(payload.get("dry_run"))).to_dict()
        if operation == "resume":
            return service.resume(payload["job_id"], progress=self.progress).to_dict()
        if operation == "regenerate":
            return service.regenerate(
                payload["job_id"], payload["segment_id"],
                text_override=payload.get("text"), progress=self.progress,
            ).to_dict()
        if operation == "delete_voice":
            voices.delete(payload["name"])
            return {"deleted": payload["name"]}
        if operation == "inspect_job":
            return jobs.get(payload["job_id"]).to_dict()
        raise ValueError(f"Unsupported desktop operation: {operation}")

    def run(self, request: dict[str, Any]) -> int:
        try:
            self.emit("ready", version=__version__)
            result = self.execute(request)
            self.emit("result", ok=True, data=result)
            return 0
        except Exception as exc:
            code = exc.exit_code if isinstance(exc, MyVoiceError) else 50
            self.emit("result", ok=False, error=str(exc), exit_code=code)
            return code


def main() -> None:
    parser = argparse.ArgumentParser(description="JSON bridge for the MyVoice macOS app")
    parser.add_argument("request", type=Path, help="Path to a JSON request")
    args = parser.parse_args()
    try:
        request = json.loads(args.request.read_text(encoding="utf-8"))
        if not isinstance(request, dict):
            raise ValueError("Desktop request must be a JSON object")
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        DesktopAPI().emit("result", ok=False, error=f"Invalid desktop request: {exc}", exit_code=2)
        raise SystemExit(2) from exc
    raise SystemExit(DesktopAPI().run(request))


if __name__ == "__main__":
    main()
