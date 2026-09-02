from __future__ import annotations

from pathlib import Path

import pytest

from myvoice.errors import InputValidationError, PronunciationDictionaryError
from myvoice.models import PronunciationEntry
from myvoice.storage import PronunciationDictionaryRepository
from myvoice.text_pipeline import PronunciationDictionary


def test_pronunciation_dictionary_crud_and_runtime_loading(tmp_path: Path) -> None:
    repository = PronunciationDictionaryRepository(tmp_path / "dictionaries")
    created = repository.save(
        name="카메라",
        language="ko",
        entries=[PronunciationEntry("Nikon", "니콘"), PronunciationEntry("ISO", "아이에스오")],
    )

    assert repository.get(created.id) == created
    assert repository.list() == [created]
    assert PronunciationDictionary.load(repository.path(created.id)).apply("Nikon ISO") == "니콘 아이에스오"

    updated = repository.save(
        dictionary_id=created.id,
        name="카메라 용어",
        language="ko",
        entries=[PronunciationEntry("Nikon", "니콘")],
    )
    assert updated.created_at == created.created_at
    assert updated.name == "카메라 용어"
    assert len(updated.entries) == 1

    repository.delete(created.id)
    assert repository.list() == []


def test_pronunciation_dictionary_rejects_duplicate_names_and_entries(tmp_path: Path) -> None:
    repository = PronunciationDictionaryRepository(tmp_path / "dictionaries")
    repository.save(name="기본", language="ko", entries=[PronunciationEntry("A", "에이")])

    with pytest.raises(PronunciationDictionaryError, match="already exists"):
        repository.save(name="기본", language="ko", entries=[PronunciationEntry("B", "비")])
    with pytest.raises(PronunciationDictionaryError, match="Duplicate pronunciation source"):
        repository.save(
            name="중복",
            language="ko",
            entries=[PronunciationEntry("A", "에이"), PronunciationEntry("A", "아")],
        )


def test_external_yaml_loads_as_unsaved_draft_and_rejects_duplicate_keys(tmp_path: Path) -> None:
    repository = PronunciationDictionaryRepository(tmp_path / "dictionaries")
    source = tmp_path / "camera.yaml"
    source.write_text("version: 1\nlanguage: ko\nentries:\n  Nikon: 니콘\n", encoding="utf-8")

    draft = repository.load_external(source)

    assert draft.id == ""
    assert draft.name == "camera"
    assert draft.entries == [PronunciationEntry("Nikon", "니콘")]

    source.write_text("entries:\n  Nikon: 니콘\n  Nikon: 나이콘\n", encoding="utf-8")
    with pytest.raises(InputValidationError, match="duplicate key"):
        repository.load_external(source)

    source.write_text("version: 2\nentries:\n  Nikon: 니콘\n", encoding="utf-8")
    with pytest.raises(InputValidationError, match="Unsupported"):
        repository.load_external(source)
