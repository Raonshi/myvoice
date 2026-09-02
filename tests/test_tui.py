from __future__ import annotations

from io import StringIO
from pathlib import Path

from rich.console import Console

from myvoice.models import VoiceProfile, utc_now
from myvoice.services import GenerationService
from myvoice.storage import JobRepository, VoiceProfileRepository
from myvoice.tui import ShellTUI


def save_profile(repository: VoiceProfileRepository, name: str) -> VoiceProfile:
    profile_dir = repository.root / name / "references"
    profile_dir.mkdir(parents=True)
    (profile_dir / "001.wav").write_bytes(b"fixture")
    profile = VoiceProfile(
        id=f"voice-{name}",
        name=name,
        language="ko",
        engine="test_tone",
        engine_model="1",
        created_at=utc_now(),
        references=["references/001.wav"],
        primary_reference="references/001.wav",
        sample_count=5,
        total_duration_seconds=55.0,
        consent_confirmed=True,
    )
    repository.save(profile)
    return profile


def make_ui(tmp_path: Path, answers: list[str]) -> tuple[ShellTUI, StringIO]:
    voices = VoiceProfileRepository(tmp_path / "voices")
    jobs = JobRepository(tmp_path / "jobs")
    output = StringIO()
    iterator = iter(answers)
    ui = ShellTUI(
        voices,
        jobs,
        GenerationService(voices, jobs),
        console=Console(file=output, force_terminal=False, width=100),
        input_fn=lambda _prompt: next(iterator),
    )
    return ui, output


def test_generate_voice_is_selected_from_enrolled_list(tmp_path: Path) -> None:
    ui, output = make_ui(tmp_path, ["2"])
    first = save_profile(ui.voices, "calm")
    second = save_profile(ui.voices, "youtube")
    selected = ui.select_voice()
    assert selected.id == second.id
    rendered = output.getvalue()
    assert first.name in rendered
    assert second.name in rendered


def test_newly_enrolled_voice_is_default_but_still_listed(tmp_path: Path) -> None:
    ui, output = make_ui(tmp_path, [""])
    save_profile(ui.voices, "calm")
    created = save_profile(ui.voices, "youtube")
    selected = ui.select_voice(preferred_voice=created.name)
    assert selected.name == "youtube"
    assert "youtube *" in output.getvalue()


def test_shell_menu_exits_without_full_screen_ui(tmp_path: Path) -> None:
    ui, output = make_ui(tmp_path, ["0"])
    ui.run()
    rendered = output.getvalue()
    assert "[1] Enroll voice" in rendered
    assert "[2] Generate AAC" in rendered
    assert "Bye." in rendered
