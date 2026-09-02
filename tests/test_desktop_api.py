from __future__ import annotations

import io
import json
from pathlib import Path

from myvoice.audio import generate_test_tone
from myvoice.desktop_api import DesktopAPI


def events(output: io.StringIO) -> list[dict]:
    return [json.loads(line) for line in output.getvalue().splitlines()]


def test_desktop_api_covers_enroll_snapshot_and_dry_run(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("MYVOICE_DATA_DIR", str(tmp_path / "data"))
    samples = tmp_path / "samples"
    samples.mkdir()
    generate_test_tone(samples / "voice.wav", duration=0.12)

    output = io.StringIO()
    api = DesktopAPI(output)
    assert api.run({
        "operation": "enroll",
        "payload": {
            "samples_dir": str(samples), "name": "desktop",
            "language": "ko", "consent_confirmed": True,
        },
    }) == 0
    enroll_result = events(output)[-1]
    assert enroll_result["ok"] is True
    assert enroll_result["data"]["metadata"]["selection_method"] == "signal_quality_v2"

    script = tmp_path / "script.txt"
    script.write_text("안녕하세요. 데스크톱 테스트입니다.", encoding="utf-8")
    output = io.StringIO()
    api = DesktopAPI(output)
    assert api.run({
        "operation": "speak",
        "payload": {
            "script": str(script), "voice": "desktop",
            "output": str(tmp_path / "result.aac"), "dry_run": True,
        },
    }) == 0
    assert events(output)[-1]["data"]["status"] == "segmented"

    output = io.StringIO()
    assert DesktopAPI(output).run({"operation": "snapshot"}) == 0
    snapshot = events(output)[-1]["data"]
    assert [voice["name"] for voice in snapshot["voices"]] == ["desktop"]
    assert len(snapshot["jobs"]) == 1


def test_desktop_api_returns_structured_error(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("MYVOICE_DATA_DIR", str(tmp_path / "data"))
    output = io.StringIO()

    code = DesktopAPI(output).run({"operation": "inspect_job", "payload": {"job_id": "missing"}})

    result = events(output)[-1]
    assert code == 40
    assert result["ok"] is False
    assert result["exit_code"] == 40
