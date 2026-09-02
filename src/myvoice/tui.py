from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from rich.console import Console
from rich.table import Table

from .errors import InputValidationError
from .models import VoiceProfile
from .services import EnrollmentService, GenerationService
from .storage import JobRepository, VoiceProfileRepository


InputFunction = Callable[[str], str]


class ShellTUI:
    """Line-oriented terminal menu that works in a normal Bash/Zsh session."""

    def __init__(
        self,
        voices: VoiceProfileRepository,
        jobs: JobRepository,
        generation: GenerationService,
        *,
        console: Console | None = None,
        input_fn: InputFunction = input,
    ) -> None:
        self.voices = voices
        self.jobs = jobs
        self.generation = generation
        self.console = console or Console()
        self.input = input_fn

    def run(self) -> None:
        self.console.print("\n[bold]MyVoice[/bold] — Voice cloning TTS\n")
        while True:
            self.console.print("[1] Enroll voice")
            self.console.print("[2] Generate AAC")
            self.console.print("[3] List voices")
            self.console.print("[4] List jobs")
            self.console.print("[0] Exit")
            choice = self._ask("Select: ").strip().lower()
            if choice in {"0", "q", "quit", "exit"}:
                self.console.print("Bye.")
                return
            try:
                if choice == "1":
                    profile = self.enroll_flow()
                    if profile and self._confirm("Continue to Generate now?", default=True):
                        self.generate_flow(preferred_voice=profile.name)
                elif choice == "2":
                    self.generate_flow()
                elif choice == "3":
                    self.show_voices()
                elif choice == "4":
                    self.show_jobs()
                else:
                    self.console.print("[yellow]Enter a number from 0 to 4.[/yellow]")
            except (EOFError, KeyboardInterrupt):
                self.console.print("\nCancelled.")
                return
            except Exception as exc:
                self.console.print(f"[red]Error:[/red] {exc}", highlight=False)
            self.console.print()

    def enroll_flow(self) -> VoiceProfile | None:
        self.console.print("\n[bold]Enroll voice[/bold]")
        samples = self._required_path("Sample folder", directory=True)
        name = self._required_text("Profile name")
        language = self._ask("Language [ko]: ").strip() or "ko"
        if not self._confirm("Is this your voice, or do you have explicit permission?", default=False):
            self.console.print("Enrollment cancelled: permission confirmation is required.")
            return None
        profile = EnrollmentService(self.voices).enroll(
            samples,
            name=name,
            language=language,
            consent_confirmed=True,
            progress=self._progress,
        )
        self.console.print(
            f"[green]Created voice profile:[/green] {profile.name} "
            f"({profile.sample_count} files, {profile.total_duration_seconds:.1f}s)"
        )
        return profile

    def generate_flow(self, preferred_voice: str | None = None) -> None:
        self.console.print("\n[bold]Generate AAC[/bold]")
        profile = self.select_voice(preferred_voice=preferred_voice)
        script = self._required_path("TXT/Markdown script", directory=False)
        suggested = script.with_suffix(".aac")
        output_text = self._ask(f"Output AAC [{suggested}]: ").strip()
        output = Path(output_text).expanduser() if output_text else suggested
        device = self._ask("Device [auto]: ").strip() or "auto"
        dry_run = self._confirm("Dry run only?", default=False)
        job = self.generation.create_job(
            script,
            profile.name,
            output,
            device=device,
        )
        self.console.print(f"Job: {job.id} · Segments: {len(job.segments)}")
        self.generation.generate(job, progress=self._progress, dry_run=dry_run)
        if dry_run:
            self.console.print(f"[green]Dry run complete.[/green] Job: {job.id}")

    def select_voice(self, preferred_voice: str | None = None) -> VoiceProfile:
        profiles = self.voices.list()
        if not profiles:
            raise InputValidationError("No enrolled voices are available. Run Enroll first.")
        self.console.print("\nAvailable enrolled voices:")
        table = Table("No.", "Name", "Language", "Samples", "Duration")
        default_index: int | None = None
        for index, profile in enumerate(profiles, 1):
            if profile.name == preferred_voice:
                default_index = index
            label = f"{profile.name} *" if profile.name == preferred_voice else profile.name
            table.add_row(str(index), label, profile.language, str(profile.sample_count), f"{profile.total_duration_seconds:.1f}s")
        self.console.print(table)
        while True:
            default_hint = f" [{default_index}]" if default_index else ""
            answer = self._ask(f"Select enrolled voice{default_hint}: ").strip()
            if not answer and default_index:
                return profiles[default_index - 1]
            try:
                selected = int(answer)
            except ValueError:
                self.console.print("[yellow]Enter the number shown in the list.[/yellow]")
                continue
            if 1 <= selected <= len(profiles):
                return profiles[selected - 1]
            self.console.print(f"[yellow]Choose a number from 1 to {len(profiles)}.[/yellow]")

    def show_voices(self) -> None:
        profiles = self.voices.list()
        if not profiles:
            self.console.print("No enrolled voices.")
            return
        table = Table("Name", "Language", "Engine", "Samples", "Duration")
        for profile in profiles:
            table.add_row(
                profile.name,
                profile.language,
                profile.engine,
                str(profile.sample_count),
                f"{profile.total_duration_seconds:.1f}s",
            )
        self.console.print(table)

    def show_jobs(self) -> None:
        jobs = self.jobs.list()
        if not jobs:
            self.console.print("No generation jobs.")
            return
        table = Table("Job", "Status", "Voice", "Segments", "Output")
        for job in jobs:
            table.add_row(job.id, job.status, job.voice_name, str(len(job.segments)), job.output_path)
        self.console.print(table)

    def _progress(self, event: str, payload: dict) -> None:
        if event == "validation.issue":
            style = "yellow" if payload["severity"] == "warning" else "red"
            self.console.print(f"[{style}]{payload['severity'].upper()}[/{style}] {payload['message']}")
        elif event == "enroll.reference":
            self.console.print(
                f"Preparing reference {payload['completed']}/{payload['total']}: "
                f"{Path(payload['source']).name}"
            )
        elif event == "segment.started":
            self.console.print(f"Generating {payload['segment_id']} ({payload['order']}/{payload['total']})")
        elif event == "segment.cached":
            self.console.print(f"Reusing {payload['segment_id']}")
        elif event == "job.completed":
            self.console.print(f"[green]Completed:[/green] {payload['output']}")

    def _ask(self, prompt: str) -> str:
        return self.input(prompt)

    def _required_text(self, label: str) -> str:
        while True:
            value = self._ask(f"{label}: ").strip()
            if value:
                return value
            self.console.print(f"[yellow]{label} is required.[/yellow]")

    def _required_path(self, label: str, *, directory: bool) -> Path:
        while True:
            value = self._required_text(label)
            path = Path(value).expanduser().resolve()
            valid = path.is_dir() if directory else path.is_file()
            if valid:
                return path
            expected = "folder" if directory else "file"
            self.console.print(f"[yellow]That {expected} does not exist: {path}[/yellow]")

    def _confirm(self, question: str, *, default: bool) -> bool:
        suffix = "[Y/n]" if default else "[y/N]"
        while True:
            value = self._ask(f"{question} {suffix}: ").strip().lower()
            if not value:
                return default
            if value in {"y", "yes"}:
                return True
            if value in {"n", "no"}:
                return False
            self.console.print("[yellow]Enter y or n.[/yellow]")
