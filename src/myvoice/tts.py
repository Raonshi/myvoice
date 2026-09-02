from __future__ import annotations

import importlib.util
import inspect
from pathlib import Path
from typing import Protocol

from .audio import generate_test_tone
from .errors import DeviceMemoryError, TTSError
from .models import SynthesisRequest


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

    def validate_runtime(self) -> None:
        missing = [name for name in ("torch", "torchaudio", "chatterbox") if importlib.util.find_spec(name) is None]
        if missing:
            raise TTSError(
                "Chatterbox runtime is not installed. Install the TTS extra with "
                "`uv sync --extra tts` (missing: " + ", ".join(missing) + ")"
            )

    def _resolve_device(self, requested: str) -> str:
        import torch
        if requested != "auto":
            return requested
        if torch.cuda.is_available():
            return "cuda"
        if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
            return "mps"
        return "cpu"

    def _get_model(self, device: str):
        self.validate_runtime()
        resolved = self._resolve_device(device)
        if self._model is None or self._device != resolved:
            try:
                from chatterbox.mtl_tts import ChatterboxMultilingualTTS
                if "t3_model" not in inspect.signature(ChatterboxMultilingualTTS.from_pretrained).parameters:
                    raise TTSError(
                        "The installed Chatterbox build does not expose Multilingual V3. "
                        "Install the pinned Git revision with `uv sync --extra tts`."
                    )
                self._model = ChatterboxMultilingualTTS.from_pretrained(device=resolved, t3_model="v3")
                self._device = resolved
            except TTSError:
                raise
            except Exception as exc:
                raise TTSError(f"Could not load Chatterbox Multilingual V3 on {resolved}: {exc}") from exc
        return self._model

    def synthesize(self, request: SynthesisRequest) -> None:
        try:
            import torch
            import torchaudio
            model = self._get_model(request.device)
            if request.seed is not None:
                torch.manual_seed(request.seed)
                if torch.cuda.is_available():
                    torch.cuda.manual_seed_all(request.seed)
            wav = model.generate(
                request.text,
                language_id=request.language,
                audio_prompt_path=str(request.reference_audio),
                exaggeration=request.exaggeration,
                cfg_weight=request.cfg_weight,
                temperature=request.temperature,
            )
            request.output_wav.parent.mkdir(parents=True, exist_ok=True)
            torchaudio.save(str(request.output_wav), wav, model.sr)
        except RuntimeError as exc:
            if "out of memory" in str(exc).lower():
                raise DeviceMemoryError(f"TTS device ran out of memory: {exc}") from exc
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
