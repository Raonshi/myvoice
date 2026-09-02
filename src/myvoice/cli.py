from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from . import __version__
from .config import AppPaths
from .desktop_api import diagnostic_snapshot
from .errors import MyVoiceError
from .services import EnrollmentService, GenerationService
from .storage import JobRepository, VoiceProfileRepository


console = Console()
app = typer.Typer(name="myvoice", help="Local-first voice-cloning TTS pipeline", no_args_is_help=False, invoke_without_command=True)
voices_app = typer.Typer(help="Manage voice profiles")
jobs_app = typer.Typer(help="Inspect generation jobs")
app.add_typer(voices_app, name="voices")
app.add_typer(jobs_app, name="jobs")


def dependencies() -> tuple[AppPaths, VoiceProfileRepository, JobRepository, GenerationService]:
    paths = AppPaths.discover()
    paths.ensure()
    voices = VoiceProfileRepository(paths.voices_dir)
    jobs = JobRepository(paths.jobs_dir)
    return paths, voices, jobs, GenerationService(voices, jobs)


def progress(event: str, payload: dict) -> None:
    if event == "validation.issue":
        style = "yellow" if payload["severity"] == "warning" else "red"
        console.print(f"[{style}]{payload['severity'].upper()}[/{style}] {payload['message']}")
    elif event == "enroll.reference":
        console.print(f"Prepared reference {payload['completed']}/{payload['total']}: {Path(payload['source']).name}")
    elif event == "segment.started":
        console.print(f"Generating {payload['segment_id']} ({payload['order']}/{payload['total']})")
    elif event == "segment.cached":
        console.print(f"Reusing {payload['segment_id']}")
    elif event == "job.completed":
        console.print(f"[green]Completed[/green] {payload['output']}")


def json_progress(event: str, payload: dict) -> None:
    console.print_json(json.dumps({"type": event, **payload}, ensure_ascii=False))


def handle_error(exc: Exception) -> None:
    if isinstance(exc, MyVoiceError):
        console.print(f"[red]Error:[/red] {exc}", highlight=False)
        raise typer.Exit(exc.exit_code)
    console.print_exception(show_locals=False)
    raise typer.Exit(50)


@app.callback()
def main(
    ctx: typer.Context,
    version: Annotated[bool, typer.Option("--version", help="Show version and exit")] = False,
) -> None:
    if version:
        console.print(__version__)
        raise typer.Exit()
    if ctx.invoked_subcommand is None:
        try:
            from .tui import ShellTUI
            _, voices, jobs, service = dependencies()
            ShellTUI(voices, jobs, service, console=console).run()
        except Exception as exc:
            handle_error(exc)


@app.command()
def enroll(
    samples_dir: Annotated[Path, typer.Argument(exists=True, file_okay=False, readable=True)],
    name: Annotated[str, typer.Option("--name", "-n", help="Voice profile name")],
    language: Annotated[str, typer.Option("--language", "-l")] = "ko",
    engine: Annotated[str, typer.Option("--engine")] = "chatterbox_multilingual",
    consent: Annotated[bool, typer.Option("--i-have-rights", help="Confirm this is your voice or you have explicit permission")] = False,
    replace: Annotated[bool, typer.Option("--replace")] = False,
) -> None:
    """Validate and enroll reference audio for a reusable voice profile."""
    try:
        _, voices, _, _ = dependencies()
        profile = EnrollmentService(voices).enroll(
            samples_dir, name=name, language=language, engine_name=engine,
            consent_confirmed=consent, replace=replace, progress=progress,
        )
        console.print(f"[green]Voice profile created:[/green] {profile.name}")
        console.print(f"Samples: {profile.sample_count} · Total: {profile.total_duration_seconds:.1f}s")
    except Exception as exc:
        handle_error(exc)


@app.command()
def speak(
    script: Annotated[Path, typer.Argument(exists=True, dir_okay=False, readable=True)],
    voice: Annotated[str, typer.Option("--voice", "-v")],
    output: Annotated[Path, typer.Option("--output", "-o")],
    device: Annotated[str, typer.Option("--device")] = "auto",
    pronunciation_dict: Annotated[Path | None, typer.Option("--pronunciation-dict")] = None,
    max_chars: Annotated[int, typer.Option("--max-chars", min=20)] = 180,
    keep_master_wav: Annotated[bool, typer.Option("--keep-master-wav/--no-keep-master-wav")] = True,
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
    json_output: Annotated[bool, typer.Option("--json")] = False,
    engine: Annotated[str | None, typer.Option("--engine", hidden=True)] = None,
) -> None:
    """Generate segmented speech from a TXT or Markdown script."""
    try:
        _, _, _, service = dependencies()
        job = service.create_job(
            script, voice, output, device=device, pronunciation_dict=pronunciation_dict,
            max_chars=max_chars, keep_master_wav=keep_master_wav, engine_override=engine,
        )
        callback = json_progress if json_output else progress
        console.print(f"Job: {job.id} · Segments: {len(job.segments)}")
        result = service.generate(job, progress=callback, dry_run=dry_run)
        if dry_run:
            console.print(f"[green]Dry run complete.[/green] Inspect with: myvoice inspect {result.id}")
    except Exception as exc:
        handle_error(exc)


@app.command()
def resume(job_id: str) -> None:
    """Resume an incomplete generation job."""
    try:
        _, _, _, service = dependencies()
        service.resume(job_id, progress=progress)
    except Exception as exc:
        handle_error(exc)


@app.command()
def regenerate(
    job_id: str,
    segment_id: str,
    text: Annotated[str | None, typer.Option("--text", help="Override normalized segment text")] = None,
) -> None:
    """Regenerate one segment and rebuild the final AAC."""
    try:
        _, _, _, service = dependencies()
        service.regenerate(job_id, segment_id, text_override=text, progress=progress)
    except Exception as exc:
        handle_error(exc)


@app.command()
def inspect(job_id: str) -> None:
    """Show a job and all segment states."""
    try:
        _, _, jobs, _ = dependencies()
        job = jobs.get(job_id)
        console.print(f"[bold]{job.id}[/bold] · {job.status} · {job.voice_name}")
        console.print(job.script_path)
        table = Table("ID", "Status", "Rev", "Text", "Duration")
        for segment in job.segments:
            table.add_row(segment.id, segment.status, str(segment.revision), segment.normalized_text, f"{segment.duration_seconds:.2f}s" if segment.duration_seconds else "-")
        console.print(table)
    except Exception as exc:
        handle_error(exc)


@voices_app.command("list")
def voices_list() -> None:
    _, voices, _, _ = dependencies()
    table = Table("Name", "Language", "Engine", "Samples", "Duration")
    for profile in voices.list():
        table.add_row(profile.name, profile.language, profile.engine, str(profile.sample_count), f"{profile.total_duration_seconds:.1f}s")
    console.print(table)


@voices_app.command("show")
def voices_show(name: str) -> None:
    try:
        _, voices, _, _ = dependencies()
        console.print_json(json.dumps(voices.get(name).to_dict(), ensure_ascii=False))
    except Exception as exc:
        handle_error(exc)


@voices_app.command("delete")
def voices_delete(name: str, yes: Annotated[bool, typer.Option("--yes")] = False) -> None:
    if not yes and not typer.confirm(f"Delete voice profile '{name}' and its references?"):
        raise typer.Abort()
    try:
        _, voices, _, _ = dependencies()
        voices.delete(name)
        console.print(f"Deleted {name}")
    except Exception as exc:
        handle_error(exc)


@jobs_app.command("list")
def jobs_list() -> None:
    _, _, jobs, _ = dependencies()
    table = Table("Job", "Status", "Voice", "Segments", "Output")
    for job in jobs.list():
        table.add_row(job.id, job.status, job.voice_name, str(len(job.segments)), job.output_path)
    console.print(table)


@app.command()
def doctor() -> None:
    """Diagnose the local runtime without changing it."""
    paths, _, _, _ = dependencies()
    table = Table("Check", "Result", "Detail")
    for check in diagnostic_snapshot(paths)["checks"]:
        table.add_row(check["name"], check["status"].upper(), check["detail"])
    console.print(table)


@app.command("desktop-api", hidden=True)
def desktop_api(request: Annotated[Path, typer.Argument(exists=True, dir_okay=False, readable=True)]) -> None:
    """Run one machine-readable request for the native desktop app."""
    from .desktop_api import DesktopAPI

    try:
        payload = json.loads(request.read_text(encoding="utf-8"))
        code = DesktopAPI().run(payload)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        DesktopAPI().emit("result", ok=False, error=f"Invalid desktop request: {exc}", exit_code=2)
        code = 2
    if code:
        raise typer.Exit(code)


if __name__ == "__main__":
    app()
