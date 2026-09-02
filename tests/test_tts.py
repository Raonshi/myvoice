from __future__ import annotations

import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from myvoice.errors import DeviceMemoryError, TTSError
from myvoice.models import SynthesisRequest
from myvoice.tts import (
    SAMPLING_BAR_FORMAT,
    ChatterboxEngine,
    inspect_mps_runtime,
    resolve_torch_device,
    sampling_progress_without_percentage,
)


class FakeMPSBackend:
    def __init__(self, *, built: bool = True, available: bool = True) -> None:
        self._built = built
        self._available = available

    def is_built(self) -> bool:
        return self._built

    def is_available(self) -> bool:
        return self._available


class FakeProbe:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error

    def item(self) -> int:
        if self.error:
            raise self.error
        return 1


class FakeTorch:
    def __init__(
        self,
        *,
        built: bool = True,
        available: bool = True,
        operation_error: Exception | None = None,
        cuda_available: bool = False,
    ) -> None:
        self.backends = SimpleNamespace(mps=FakeMPSBackend(built=built, available=available))
        self.cuda = SimpleNamespace(
            is_available=lambda: cuda_available,
            manual_seed_all=lambda _seed: None,
        )
        self.mps_empty_cache_calls = 0
        self.mps = SimpleNamespace(empty_cache=self._empty_cache)
        self.operation_error = operation_error

    def ones(self, _size: int, *, device: str):
        assert device == "mps"
        return FakeProbe(self.operation_error)

    def manual_seed(self, _seed: int) -> None:
        return None

    def _empty_cache(self) -> None:
        self.mps_empty_cache_calls += 1


class FakeTorchaudio:
    @staticmethod
    def save(path: str, _wav, _sample_rate: int) -> None:
        Path(path).write_bytes(b"fake-wav")


class FakeChatterboxModel:
    sr = 24000

    def __init__(self) -> None:
        self.prepared: list[tuple[str, float]] = []
        self.generated_prompts: list[str | None] = []
        self.prepare_error: Exception | None = None
        self.generate_error: Exception | None = None

    def prepare_conditionals(self, path: str, *, exaggeration: float) -> None:
        if self.prepare_error:
            raise self.prepare_error
        self.prepared.append((path, exaggeration))

    def generate(self, _text: str, **kwargs):
        if self.generate_error:
            raise self.generate_error
        self.generated_prompts.append(kwargs["audio_prompt_path"])
        return object()


def make_request(tmp_path: Path, *, exaggeration: float = 0.5) -> SynthesisRequest:
    reference = tmp_path / "reference.wav"
    reference.write_bytes(b"reference")
    return SynthesisRequest(
        text="테스트 문장입니다.",
        language="ko",
        reference_audio=reference,
        output_wav=tmp_path / "output.wav",
        device="mps",
        exaggeration=exaggeration,
    )


def install_fake_runtime(monkeypatch, torch_module: FakeTorch) -> None:
    monkeypatch.setitem(sys.modules, "torch", torch_module)
    monkeypatch.setitem(sys.modules, "torchaudio", FakeTorchaudio())


def test_mps_runtime_requires_a_successful_operation() -> None:
    assert inspect_mps_runtime(FakeTorch()).functional
    unavailable = inspect_mps_runtime(FakeTorch(available=False))
    assert unavailable.built
    assert not unavailable.available
    assert not unavailable.functional
    broken = inspect_mps_runtime(FakeTorch(operation_error=RuntimeError("Metal failed")))
    assert broken.available
    assert not broken.functional
    assert "Metal failed" in broken.detail


def test_auto_device_prefers_mps_only_for_native_apple_silicon() -> None:
    torch_module = FakeTorch()
    assert resolve_torch_device(
        "auto", torch_module, system_name="Darwin", machine="arm64"
    ) == "mps"
    assert resolve_torch_device(
        "auto", torch_module, system_name="Darwin", machine="x86_64"
    ) == "cpu"
    assert resolve_torch_device(
        "auto", FakeTorch(operation_error=RuntimeError("failed")),
        system_name="Darwin", machine="arm64",
    ) == "cpu"


def test_explicit_mps_does_not_silently_fall_back() -> None:
    with pytest.raises(TTSError, match="myvoice doctor"):
        resolve_torch_device("mps", FakeTorch(available=False))


def test_sampling_progress_format_omits_percentage() -> None:
    captured: list[dict] = []

    def fake_tqdm(*_args, **kwargs):
        captured.append(kwargs)
        return object()

    wrapped = sampling_progress_without_percentage(fake_tqdm)
    wrapped(range(3), desc="Sampling", bar_format="{percentage}%")
    wrapped(range(3), desc="Other")

    assert captured[0]["bar_format"] == SAMPLING_BAR_FORMAT
    assert "percentage" not in captured[0]["bar_format"]
    assert "bar_format" not in captured[1]


def test_conditionals_are_reused_for_same_reference(tmp_path: Path, monkeypatch) -> None:
    torch_module = FakeTorch()
    install_fake_runtime(monkeypatch, torch_module)
    model = FakeChatterboxModel()
    engine = ChatterboxEngine()
    engine._model = model
    engine._device = "mps"
    engine._requested_device = "mps"
    monkeypatch.setattr(engine, "_get_model", lambda _device: model)
    request = make_request(tmp_path)

    engine.synthesize(request)
    engine.synthesize(request)

    assert model.prepared == [(str(request.reference_audio.resolve()), 0.5)]
    assert model.generated_prompts == [None, None]
    assert request.output_wav.read_bytes() == b"fake-wav"


def test_conditionals_cache_invalidates_on_input_change(tmp_path: Path, monkeypatch) -> None:
    install_fake_runtime(monkeypatch, FakeTorch())
    model = FakeChatterboxModel()
    engine = ChatterboxEngine()
    engine._device = "mps"
    monkeypatch.setattr(engine, "_get_model", lambda _device: model)
    request = make_request(tmp_path)

    engine.synthesize(request)
    changed_exaggeration = SynthesisRequest(
        **{**request.__dict__, "exaggeration": 0.7, "output_wav": tmp_path / "second.wav"}
    )
    engine.synthesize(changed_exaggeration)
    original_stat = request.reference_audio.stat()
    os.utime(
        request.reference_audio,
        ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns + 1_000_000),
    )
    engine.synthesize(changed_exaggeration)

    assert [item[1] for item in model.prepared] == [0.5, 0.7, 0.7]


def test_failed_conditionals_are_not_cached(tmp_path: Path, monkeypatch) -> None:
    install_fake_runtime(monkeypatch, FakeTorch())
    model = FakeChatterboxModel()
    model.prepare_error = ValueError("bad reference")
    engine = ChatterboxEngine()
    engine._device = "mps"
    monkeypatch.setattr(engine, "_get_model", lambda _device: model)
    request = make_request(tmp_path)

    with pytest.raises(TTSError, match="bad reference"):
        engine.synthesize(request)
    assert engine._conditionals_key is None

    model.prepare_error = None
    engine.synthesize(request)
    assert len(model.prepared) == 1


def test_mps_oom_clears_model_and_allocator_cache(tmp_path: Path, monkeypatch) -> None:
    torch_module = FakeTorch()
    install_fake_runtime(monkeypatch, torch_module)
    model = FakeChatterboxModel()
    model.generate_error = RuntimeError("MPS backend out of memory")
    engine = ChatterboxEngine()
    engine._model = model
    engine._device = "mps"
    engine._requested_device = "mps"
    monkeypatch.setattr(engine, "_get_model", lambda _device: model)

    with pytest.raises(DeviceMemoryError, match="out of memory"):
        engine.synthesize(make_request(tmp_path))

    assert engine._model is None
    assert engine._device is None
    assert engine._conditionals_key is None
    assert torch_module.mps_empty_cache_calls == 1
