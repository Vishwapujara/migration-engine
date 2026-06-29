from __future__ import annotations

import tree_sitter_typescript as tsts
from tree_sitter import Language, Node

from .javascript_extractor import JavaScriptExtractor
from .models import FunctionInfo, ClassInfo, ImportInfo


class TypeScriptExtractor(JavaScriptExtractor):
    language_name = "typescript"
    extensions = [".ts"]

    def _build_language(self) -> Language:
        return Language(tsts.language_typescript())

    def _extract_params(self, params_node: Node | None, src: bytes) -> list[str]:
        if not params_node:
            return []
        params = []
        for child in params_node.children:
            if child.type in (
                "identifier", "required_parameter", "optional_parameter",
                "rest_pattern", "assignment_pattern",
            ):
                name_node = (
                    next(
                        (c for c in child.children if c.type == "identifier"), None
                    )
                    if child.type != "identifier"
                    else child
                )
                if name_node:
                    params.append(self._text(name_node, src))
        return params

    def _extract_top_level_functions(self, root: Node, src: bytes) -> list[FunctionInfo]:
        functions = super()._extract_top_level_functions(root, src)

        # Also capture ambient/exported functions declared with type annotations
        for child in root.children:
            if child.type in ("ambient_declaration", "export_statement"):
                for sub in child.children:
                    fn = self._try_extract_function(sub, src)
                    if fn and not any(f.name == fn.name for f in functions):
                        functions.append(fn)

        return functions

    def _extract_classes(self, root: Node, src: bytes) -> list[ClassInfo]:
        classes = super()._extract_classes(root, src)

        # Handle abstract classes and ambient declarations
        for child in root.children:
            if child.type == "abstract_class_declaration":
                cls = self._parse_class(child, src)
                if not any(c.name == cls.name for c in classes):
                    classes.append(cls)

        return classes


class TSXExtractor(TypeScriptExtractor):
    language_name = "tsx"
    extensions = [".tsx", ".jsx"]

    def _build_language(self) -> Language:
        return Language(tsts.language_tsx())
