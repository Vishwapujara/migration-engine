from __future__ import annotations
from abc import ABC, abstractmethod
from pathlib import Path

from tree_sitter import Language, Parser, Node

from .models import ParsedFile, FunctionInfo, ClassInfo, ImportInfo


class LanguageExtractor(ABC):
    language_name: str
    extensions: list[str]

    def __init__(self) -> None:
        self._language: Language = self._build_language()
        self._parser: Parser = Parser(self._language)

    @abstractmethod
    def _build_language(self) -> Language:
        ...

    def extract(self, file_path: str, source: str) -> ParsedFile:
        source_bytes = source.encode("utf-8")
        tree = self._parser.parse(source_bytes)
        root = tree.root_node

        imports = self._extract_imports(root, source_bytes)
        functions = self._extract_top_level_functions(root, source_bytes)
        classes = self._extract_classes(root, source_bytes)

        local_deps, external_deps = self._classify_dependencies(imports, file_path)
        complexity = self._compute_complexity(source, functions, classes, imports)

        return ParsedFile(
            file_path=file_path,
            language=self.language_name,
            imports=imports,
            functions=functions,
            classes=classes,
            raw_source=source,
            line_count=source.count("\n") + 1,
            complexity_score=complexity,
            local_dependencies=local_deps,
            external_dependencies=external_deps,
        )

    @abstractmethod
    def _extract_imports(self, root: Node, src: bytes) -> list[ImportInfo]:
        ...

    @abstractmethod
    def _extract_top_level_functions(self, root: Node, src: bytes) -> list[FunctionInfo]:
        ...

    @abstractmethod
    def _extract_classes(self, root: Node, src: bytes) -> list[ClassInfo]:
        ...

    @abstractmethod
    def _classify_dependencies(
        self, imports: list[ImportInfo], file_path: str
    ) -> tuple[list[str], list[str]]:
        ...

    def _compute_complexity(
        self,
        source: str,
        functions: list[FunctionInfo],
        classes: list[ClassInfo],
        imports: list[ImportInfo],
    ) -> float:
        lines = source.count("\n") + 1
        score = (
            min(lines / 100, 4.0)
            + min(len(functions) * 0.15, 2.0)
            + min(len(classes) * 0.25, 2.0)
            + min(len(imports) * 0.05, 1.0)
            + min(sum(len(c.methods) for c in classes) * 0.05, 1.0)
        )
        return round(min(score, 10.0), 2)

    @staticmethod
    def _text(node: Node, src: bytes) -> str:
        return src[node.start_byte:node.end_byte].decode("utf-8", errors="replace")

    @staticmethod
    def _walk(node: Node, *types: str):
        if node.type in types:
            yield node
        for child in node.children:
            yield from LanguageExtractor._walk(child, *types)

    @staticmethod
    def _direct_children_of_type(node: Node, *types: str) -> list[Node]:
        return [c for c in node.children if c.type in types]
