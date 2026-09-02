from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from platformdirs import user_data_path


@dataclass(frozen=True)
class AppPaths:
    data_dir: Path
    voices_dir: Path
    jobs_dir: Path
    pronunciation_dictionaries_dir: Path

    @classmethod
    def discover(cls) -> "AppPaths":
        override = os.environ.get("MYVOICE_DATA_DIR")
        root = Path(override).expanduser() if override else user_data_path("myvoice", appauthor=False)
        return cls(root, root / "voices", root / "jobs", root / "pronunciation_dictionaries")

    def ensure(self) -> None:
        self.voices_dir.mkdir(parents=True, exist_ok=True)
        self.jobs_dir.mkdir(parents=True, exist_ok=True)
        self.pronunciation_dictionaries_dir.mkdir(parents=True, exist_ok=True)
