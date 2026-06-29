from __future__ import annotations
from pathlib import Path

from .base import LanguageExtractor
from .python_extractor import PythonExtractor
from .javascript_extractor import JavaScriptExtractor
from .typescript_extractor import TypeScriptExtractor, TSXExtractor
from .models import ParsedFile


_EXTRACTORS: list[LanguageExtractor] = [
    PythonExtractor(),
    JavaScriptExtractor(),
    TypeScriptExtractor(),
    TSXExtractor(),
]

_EXTENSION_MAP: dict[str, LanguageExtractor] = {}
for _extractor in _EXTRACTORS:
    for _ext in _extractor.extensions:
        _EXTENSION_MAP[_ext] = _extractor

_NAME_MAP: dict[str, LanguageExtractor] = {
    e.language_name: e for e in _EXTRACTORS
}


def get_extractor_for_file(file_path: str) -> LanguageExtractor | None:
    ext = Path(file_path).suffix.lower()
    return _EXTENSION_MAP.get(ext)


def get_extractor_for_language(language: str) -> LanguageExtractor | None:
    return _NAME_MAP.get(language.lower())


def detect_language(file_path: str) -> str | None:
    extractor = get_extractor_for_file(file_path)
    return extractor.language_name if extractor else None


def parse_file(file_path: str, source: str) -> ParsedFile | None:
    extractor = get_extractor_for_file(file_path)
    if extractor is None:
        return None
    return extractor.extract(file_path, source)


def supported_extensions() -> list[str]:
    return list(_EXTENSION_MAP.keys())
