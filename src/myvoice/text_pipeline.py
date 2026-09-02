from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Iterable

import yaml
from markdown_it import MarkdownIt
from markdown_it.token import Token

from .errors import InputValidationError
from .models import DocumentBlock, SpeechDocument, SpeechSegment


def hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class ScriptParser:
    def parse(self, path: Path) -> SpeechDocument:
        path = path.expanduser().resolve()
        if not path.is_file():
            raise InputValidationError(f"Script file does not exist: {path}")
        try:
            text = path.read_text(encoding="utf-8-sig")
        except (OSError, UnicodeError) as exc:
            raise InputValidationError(f"Could not read script as UTF-8: {exc}") from exc
        if not text.strip():
            raise InputValidationError("Script is empty")
        suffix = path.suffix.lower()
        if suffix == ".txt":
            blocks = self._parse_txt(text)
        elif suffix in {".md", ".markdown"}:
            blocks = self._parse_markdown(text)
        else:
            raise InputValidationError("Only .txt, .md, and .markdown scripts are supported")
        if not blocks:
            raise InputValidationError("Script has no readable content")
        return SpeechDocument(str(path), hash_text(text), blocks)

    @staticmethod
    def _parse_txt(text: str) -> list[DocumentBlock]:
        parts = [part.strip() for part in re.split(r"\n\s*\n", text) if part.strip()]
        return [DocumentBlock(f"txt-p-{index:04d}", "paragraph", re.sub(r"\s+", " ", part), 850) for index, part in enumerate(parts, 1)]

    def _parse_markdown(self, text: str) -> list[DocumentBlock]:
        tokens = MarkdownIt("commonmark", {"html": False}).parse(text)
        blocks: list[DocumentBlock] = []
        pending_kind = "paragraph"
        for token in tokens:
            if token.type == "heading_open":
                pending_kind = "heading"
            elif token.type in {"paragraph_open", "blockquote_open", "list_item_open"} and pending_kind != "heading":
                pending_kind = "list_item" if token.type == "list_item_open" else "paragraph"
            elif token.type == "inline":
                content = self._inline_text(token.children or [])
                content = re.sub(r"\s+", " ", content).strip()
                if content:
                    pause = 1100 if pending_kind == "heading" else 650 if pending_kind == "list_item" else 850
                    blocks.append(DocumentBlock(f"md-{pending_kind}-{len(blocks) + 1:04d}", pending_kind, content, pause))
                pending_kind = "paragraph"
            elif token.type in {"fence", "code_block", "html_block"}:
                continue
        return blocks

    @staticmethod
    def _inline_text(children: list[Token]) -> str:
        parts: list[str] = []
        for child in children:
            if child.type in {"text", "code_inline"}:
                parts.append(child.content)
            elif child.type in {"softbreak", "hardbreak"}:
                parts.append(" ")
            elif child.type == "image":
                alt = child.content.strip()
                if alt:
                    parts.append(alt)
        return "".join(parts)


class PronunciationDictionary:
    def __init__(self, entries: dict[str, str] | None = None):
        self.entries = entries or {}

    @classmethod
    def load(cls, path: Path | None) -> "PronunciationDictionary":
        if path is None:
            return cls()
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except (OSError, UnicodeError, yaml.YAMLError) as exc:
            raise InputValidationError(f"Could not read pronunciation dictionary: {exc}") from exc
        entries = data.get("entries", data)
        if not isinstance(entries, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in entries.items()):
            raise InputValidationError("Pronunciation dictionary entries must be string key/value pairs")
        return cls(entries)

    def apply(self, text: str) -> str:
        result = text
        for source in sorted(self.entries, key=len, reverse=True):
            result = result.replace(source, self.entries[source])
        return result


class KoreanTextNormalizer:
    _spaces = re.compile(r"\s+")
    _thousands = re.compile(r"(?<![\w.])([0-9]{1,3}(?:,[0-9]{3})+)(?![\w.])")
    _date = re.compile(r"(?<!\d)(\d{4})[-./](\d{1,2})[-./](\d{1,2})(?!\d)")
    _time = re.compile(r"(?<!\d)(\d{1,2}):(\d{2})(?!\d)")
    _decimal_with_unit = re.compile(r"(?<![\w.])(\d+)\.(\d+)(\s*)(kg|km|mm|cm|GB|MB|kHz|Hz)(?![A-Za-z])", re.IGNORECASE)
    _decimal = re.compile(r"(?<![\w.])(\d+)\.(\d+)(?![\w.])")
    _number_with_unit = re.compile(r"(?<![\w.])(\d+)(\s*)(%|kg|km|mm|cm|GB|MB|kHz|Hz|원)(?![A-Za-z])", re.IGNORECASE)
    _integer = re.compile(r"(?<![\w.])\d+(?![\w.])")
    _unit_readings = {
        "%": "퍼센트", "kg": "킬로그램", "km": "킬로미터", "mm": "밀리미터",
        "cm": "센티미터", "gb": "기가바이트", "mb": "메가바이트",
        "khz": "킬로헤르츠", "hz": "헤르츠", "원": "원",
    }

    def __init__(self, pronunciation: PronunciationDictionary | None = None):
        self.pronunciation = pronunciation or PronunciationDictionary()

    def normalize(self, text: str) -> str:
        value = text.replace("\u00a0", " ").strip()
        value = self.pronunciation.apply(value)
        value = self._thousands.sub(lambda match: match.group(1).replace(",", ""), value)
        value = self._date.sub(
            lambda match: (
                f"{self._integer_to_korean(int(match.group(1)))}년 "
                f"{self._integer_to_korean(int(match.group(2)))}월 "
                f"{self._integer_to_korean(int(match.group(3)))}일"
            ),
            value,
        )
        value = self._time.sub(
            lambda match: (
                f"{self._integer_to_korean(int(match.group(1)))}시 "
                f"{self._integer_to_korean(int(match.group(2)))}분"
            ),
            value,
        )
        value = self._decimal_with_unit.sub(
            lambda match: (
                f"{self._integer_to_korean(int(match.group(1)))}점 "
                + " ".join(self._digit_to_korean(int(digit)) for digit in match.group(2))
                + " "
                + self._unit_readings[match.group(4).lower()]
            ),
            value,
        )
        value = self._decimal.sub(
            lambda match: (
                f"{self._integer_to_korean(int(match.group(1)))}점 "
                + " ".join(self._digit_to_korean(int(digit)) for digit in match.group(2))
            ),
            value,
        )
        value = self._number_with_unit.sub(
            lambda match: (
                self._integer_to_korean(int(match.group(1)))
                + " "
                + self._unit_readings[match.group(3).lower()]
            ),
            value,
        )
        value = self._integer.sub(lambda match: self._integer_to_korean(int(match.group(0))), value)
        value = value.replace("…", "...").replace("—", "-").replace("–", "-")
        value = self._spaces.sub(" ", value)
        return value.strip()

    @staticmethod
    def _digit_to_korean(value: int) -> str:
        return ("영", "일", "이", "삼", "사", "오", "육", "칠", "팔", "구")[value]

    @classmethod
    def _integer_to_korean(cls, value: int) -> str:
        if value == 0:
            return "영"
        if value < 0:
            return "마이너스 " + cls._integer_to_korean(-value)
        digits = ("", "일", "이", "삼", "사", "오", "육", "칠", "팔", "구")
        small_units = ("", "십", "백", "천")
        large_units = ("", "만", "억", "조", "경")
        groups: list[int] = []
        remaining = value
        while remaining:
            groups.append(remaining % 10000)
            remaining //= 10000
        parts: list[str] = []
        for group_index in range(len(groups) - 1, -1, -1):
            group = groups[group_index]
            if group == 0:
                continue
            group_parts: list[str] = []
            for position in range(3, -1, -1):
                digit = (group // (10 ** position)) % 10
                if digit == 0:
                    continue
                if digit != 1 or position == 0:
                    group_parts.append(digits[digit])
                group_parts.append(small_units[position])
            parts.append("".join(group_parts) + large_units[group_index])
        return "".join(parts)


class Segmenter:
    sentence_boundary = re.compile(r"(?<=[.!?。！？])\s+")

    def __init__(self, max_chars: int = 180, sentence_pause_ms: int = 450):
        if max_chars < 20:
            raise ValueError("max_chars must be at least 20")
        self.max_chars = max_chars
        self.sentence_pause_ms = sentence_pause_ms

    def segment(self, document: SpeechDocument, normalizer: KoreanTextNormalizer) -> list[SpeechSegment]:
        result: list[SpeechSegment] = []
        for block in document.blocks:
            normalized = normalizer.normalize(block.text)
            pieces = self._split(normalized)
            for index, piece in enumerate(pieces):
                pause = block.pause_after_ms if index == len(pieces) - 1 else self.sentence_pause_ms
                digest = hash_text(f"{document.source_hash}|{block.id}|{piece}|{pause}")
                order = len(result) + 1
                result.append(
                    SpeechSegment(
                        id=f"seg-{order:04d}", order=order, source_block_id=block.id,
                        source_text=block.text, normalized_text=piece, pause_after_ms=pause,
                        content_hash=digest,
                    )
                )
        if not result:
            raise InputValidationError("No speech segments were produced")
        return result

    def _split(self, text: str) -> list[str]:
        if len(text) <= self.max_chars:
            return [text]
        sentences = [piece.strip() for piece in self.sentence_boundary.split(text) if piece.strip()]
        if len(sentences) == 1:
            sentences = self._hard_split(text)
        result: list[str] = []
        current = ""
        for sentence in sentences:
            if len(sentence) > self.max_chars:
                if current:
                    result.append(current)
                    current = ""
                result.extend(self._hard_split(sentence))
            elif not current:
                current = sentence
            elif len(current) + 1 + len(sentence) <= self.max_chars:
                current = f"{current} {sentence}"
            else:
                result.append(current)
                current = sentence
        if current:
            result.append(current)
        return result

    def _hard_split(self, text: str) -> list[str]:
        chunks: list[str] = []
        remaining = text.strip()
        while len(remaining) > self.max_chars:
            window = remaining[: self.max_chars + 1]
            candidates = [window.rfind(marker) for marker in (", ", "; ", " ")]
            cut = max(candidates)
            if cut < self.max_chars // 2:
                cut = self.max_chars
            chunks.append(remaining[:cut].strip(" ,;"))
            remaining = remaining[cut:].strip()
        if remaining:
            chunks.append(remaining)
        return chunks
