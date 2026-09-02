from __future__ import annotations

from pathlib import Path

from myvoice.text_pipeline import KoreanTextNormalizer, PronunciationDictionary, ScriptParser, Segmenter


def test_markdown_parser_reads_labels_not_urls(tmp_path: Path) -> None:
    script = tmp_path / "script.md"
    script.write_text(
        "# 제목\n\n오늘은 **Nikon Z fc**입니다. [공식 홈페이지](https://example.com)를 참고했습니다.\n\n```python\nprint('skip')\n```\n",
        encoding="utf-8",
    )
    document = ScriptParser().parse(script)
    combined = " ".join(block.text for block in document.blocks)
    assert "제목" in combined
    assert "Nikon Z fc" in combined
    assert "공식 홈페이지" in combined
    assert "https://" not in combined
    assert "print" not in combined


def test_pronunciation_and_segmentation(tmp_path: Path) -> None:
    script = tmp_path / "script.txt"
    script.write_text("Nikon Z fc를 소개합니다. 두 번째 문장입니다.\n\n새 문단입니다.", encoding="utf-8")
    document = ScriptParser().parse(script)
    normalizer = KoreanTextNormalizer(PronunciationDictionary({"Nikon": "니콘", "Z fc": "지 에프씨"}))
    segments = Segmenter(max_chars=20).segment(document, normalizer)
    assert len(segments) >= 3
    assert segments[0].id == "seg-0001"
    assert "니콘 지 에프씨" in segments[0].normalized_text
    assert segments[-1].pause_after_ms == 850


def test_korean_number_date_time_and_units() -> None:
    normalizer = KoreanTextNormalizer()
    result = normalizer.normalize("2026-09-02 14:30에 ISO 6400, 24.5mm, 50%를 확인합니다.")
    assert "이천이십육년 구월 이일" in result
    assert "십사시 삼십분" in result
    assert "육천사백" in result
    assert "이십사점 오 밀리미터" in result
    assert "오십 퍼센트" in result
