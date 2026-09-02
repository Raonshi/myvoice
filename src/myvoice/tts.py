from __future__ import annotations

import gc
import importlib.util
import inspect
import os
import platform
from dataclasses import dataclass
from functools import wraps
from pathlib import Path
from typing import Protocol

from .audio import generate_test_tone
from .errors import DeviceMemoryError, TTSError
from .models import SynthesisRequest


# Chatterbox imports PyTorch lazily. Set the supported-operation fallback before
# that import so an otherwise unsupported MPS operation can run on the CPU.
os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")

SAMPLING_BAR_FORMAT = "{desc}: {n_fmt}/{total_fmt} [{elapsed}<{remaining}, {rate_fmt}]"


@dataclass(frozen=True)
class MPSRuntimeStatus:
    built: bool
    available: bool
    functional: bool
    detail: str


def inspect_mps_runtime(torch_module) -> MPSRuntimeStatus:
    """Check that MPS is compiled, visible, and can execute a small operation."""
    backend = getattr(getattr(torch_module, "backends", None), "mps", None)
    built = bool(backend and backend.is_built())
    available = bool(backend and backend.is_available())
    if not built:
        return MPSRuntimeStatus(False, False, False, "PyTorch was built without MPS support")
    if not available:
        return MPSRuntimeStatus(True, False, False, "MPS is not available to this process")
    try:
        probe = torch_module.ones(1, device="mps")
        probe.item()  # Force execution instead of accepting a lazy allocation.
        del probe
    except Exception as exc:
        return MPSRuntimeStatus(True, True, False, f"MPS operation failed: {exc}")
    return MPSRuntimeStatus(True, True, True, "MPS operation succeeded")


def resolve_torch_device(
    requested: str,
    torch_module,
    *,
    system_name: str | None = None,
    machine: str | None = None,
) -> str:
    """Resolve MyVoice's device policy without silently downgrading explicit MPS."""
    if requested == "mps":
        status = inspect_mps_runtime(torch_module)
        if not status.functional:
            raise TTSError(
                f"MPS was requested but is unavailable: {status.detail}. "
                "Run `myvoice doctor` for macOS and PyTorch diagnostics."
            )
        return "mps"
    if requested != "auto":
        return requested

    current_system = system_name or platform.system()
    current_machine = machine or platform.machine()
    if current_system == "Darwin":
        if current_machine == "arm64" and inspect_mps_runtime(torch_module).functional:
            return "mps"
        return "cpu"
    if torch_module.cuda.is_available():
        return "cuda"
    if inspect_mps_runtime(torch_module).functional:
        return "mps"
    return "cpu"


def sampling_progress_without_percentage(tqdm_factory):
    """Wrap tqdm so Chatterbox Sampling shows counts and rate without a percent."""
    @wraps(tqdm_factory)
    def wrapped(*args, **kwargs):
        if kwargs.get("desc") == "Sampling":
            kwargs["bar_format"] = SAMPLING_BAR_FORMAT
        return tqdm_factory(*args, **kwargs)

    wrapped.__myvoice_sampling_progress__ = True
    return wrapped


def configure_chatterbox_sampling_progress() -> None:
    """Install the display-only wrapper on the pinned Chatterbox T3 module once."""
    import chatterbox.models.t3.t3 as t3_module

    current = t3_module.tqdm
    if not getattr(current, "__myvoice_sampling_progress__", False):
        t3_module.tqdm = sampling_progress_without_percentage(current)


class TTSEngine(Protocol):
    name: str
    model_name: str

    def validate_runtime(self) -> None: ...
    def synthesize(self, request: SynthesisRequest) -> None: ...


class ChatterboxEngine:
    name = "chatterbox_multilingual"
    model_name = "v3"

    def __init__(self) -> None:
        self._model = None
        self._device: str | None = None
        self._requested_device: str | None = None
        self._conditionals_key: tuple[object, ...] | None = None

    def validate_runtime(self) -> None:
        missing = [name for name in ("torch", "torchaudio", "chatterbox") if importlib.util.find_spec(name) is None]
        if missing:
            raise TTSError(
                "Chatterbox runtime is not installed. Install the TTS extra with "
                "`uv sync --extra tts` (missing: " + ", ".join(missing) + ")"
            )

    def _resolve_device(self, requested: str) -> str:
        import torch
        return resolve_torch_device(requested, torch)

    def _get_model(self, device: str):
        self.validate_runtime()
        if self._model is not None and self._requested_device == device:
            return self._model
        resolved = self._resolve_device(device)
        if self._model is None or self._device != resolved:
            try:
                from chatterbox.mtl_tts import ChatterboxMultilingualTTS
                if "t3_model" not in inspect.signature(ChatterboxMultilingualTTS.from_pretrained).parameters:
                    raise TTSError(
                        "The installed Chatterbox build does not expose Multilingual V3. "
                        "Install the pinned Git revision with `uv sync --extra tts`."
                    )
                configure_chatterbox_sampling_progress()
                model = ChatterboxMultilingualTTS.from_pretrained(device=resolved, t3_model="v3")
                self._model = model
                self._device = resolved
                self._requested_device = device
                self._conditionals_key = None
            except RuntimeError as exc:
                if "out of memory" in str(exc).lower():
                    if resolved == "mps":
                        import torch

                        self._clear_after_mps_oom(torch)
                    raise DeviceMemoryError(f"TTS device ran out of memory: {exc}") from None
                raise TTSError(f"Could not load Chatterbox Multilingual V3 on {resolved}: {exc}") from exc
            except TTSError:
                raise
            except Exception as exc:
                raise TTSError(f"Could not load Chatterbox Multilingual V3 on {resolved}: {exc}") from exc
        else:
            self._requested_device = device
        return self._model

    def _conditionals_cache_key(self, model, request: SynthesisRequest) -> tuple[object, ...]:
        reference = request.reference_audio.expanduser().resolve()
        stat = reference.stat()
        return (
            id(model),
            self._device,
            str(reference),
            stat.st_size,
            stat.st_mtime_ns,
            float(request.exaggeration),
        )

    def _clear_after_mps_oom(self, torch_module) -> None:
        self._model = None
        self._device = None
        self._requested_device = None
        self._conditionals_key = None
        gc.collect()
        try:
            torch_module.mps.empty_cache()
        except Exception:
            # Preserve the original OOM as the actionable failure.
            pass

    def synthesize(self, request: SynthesisRequest) -> None:
        model = None
        wav = None
        try:
            import torch
            import torchaudio
            model = self._get_model(request.device)
            if request.seed is not None:
                torch.manual_seed(request.seed)
                if torch.cuda.is_available():
                    torch.cuda.manual_seed_all(request.seed)

            conditionals_key = self._conditionals_cache_key(model, request)
            if conditionals_key != self._conditionals_key:
                self._conditionals_key = None
                model.prepare_conditionals(
                    str(request.reference_audio.expanduser().resolve()),
                    exaggeration=request.exaggeration,
                )
                self._conditionals_key = conditionals_key

            wav = model.generate(
                request.text,
                language_id=request.language,
                audio_prompt_path=None,
                exaggeration=request.exaggeration,
                cfg_weight=request.cfg_weight,
                temperature=request.temperature,
            )
            request.output_wav.parent.mkdir(parents=True, exist_ok=True)
            torchaudio.save(str(request.output_wav), wav, model.sr)
        except RuntimeError as exc:
            if "out of memory" in str(exc).lower():
                was_mps = self._device == "mps"
                wav = None
                model = None
                if was_mps:
                    self._clear_after_mps_oom(torch)
                raise DeviceMemoryError(f"TTS device ran out of memory: {exc}") from None
            raise TTSError(f"Chatterbox generation failed: {exc}") from exc
        except TTSError:
            raise
        except Exception as exc:
            raise TTSError(f"Chatterbox generation failed: {exc}") from exc


class TestToneEngine:
    """Deterministic local engine used for tests and pipeline smoke checks."""

    name = "test_tone"
    model_name = "1"

    def validate_runtime(self) -> None:
        return None

    def synthesize(self, request: SynthesisRequest) -> None:
        duration = max(0.08, min(0.8, len(request.text) * 0.008))
        generate_test_tone(request.output_wav, duration=duration)


def create_engine(name: str) -> TTSEngine:
    if name in {"chatterbox", "chatterbox_multilingual"}:
        return ChatterboxEngine()
    if name == "test_tone":
        return TestToneEngine()
    raise TTSError(f"Unknown TTS engine: {name}")
