from __future__ import annotations
from pathlib import Path

import tree_sitter_python as tspython
from tree_sitter import Language, Node

from .base import LanguageExtractor
from .models import FunctionInfo, ClassInfo, ImportInfo


class PythonExtractor(LanguageExtractor):
    language_name = "python"
    extensions = [".py"]

    def _build_language(self) -> Language:
        return Language(tspython.language())

    # ------------------------------------------------------------------
    # Imports
    # ------------------------------------------------------------------

    def _extract_imports(self, root: Node, src: bytes) -> list[ImportInfo]:
        imports: list[ImportInfo] = []
        for node in root.children:
            if node.type == "import_statement":
                imports.extend(self._parse_import_statement(node, src))
            elif node.type == "import_from_statement":
                imports.append(self._parse_import_from_statement(node, src))
            elif node.type == "decorated_definition":
                pass  # decorators are not imports
        return imports

    def _parse_import_statement(self, node: Node, src: bytes) -> list[ImportInfo]:
        results = []
        for child in node.children:
            if child.type in ("dotted_name", "aliased_import"):
                if child.type == "aliased_import":
                    name_node = child.child_by_field_name("name") or child.children[0]
                    alias_node = child.child_by_field_name("alias")
                    module = self._text(name_node, src)
                    alias = self._text(alias_node, src) if alias_node else None
                else:
                    module = self._text(child, src)
                    alias = None
                results.append(ImportInfo(
                    raw=self._text(node, src),
                    module=module,
                    names=[],
                    is_relative=False,
                    alias=alias,
                ))
        return results

    def _parse_import_from_statement(self, node: Node, src: bytes) -> ImportInfo:
        raw = self._text(node, src)
        module = ""
        is_relative = False
        names: list[str] = []

        for child in node.children:
            if child.type == "relative_import":
                is_relative = True
                inner = child.child_by_field_name("name") or next(
                    (c for c in child.children if c.type == "dotted_name"), None
                )
                module = self._text(inner, src) if inner else ""
            elif child.type == "dotted_name" and module == "":
                module = self._text(child, src)
            elif child.type == "wildcard_import":
                names.append("*")
            elif child.type in ("dotted_name", "identifier") and module != "":
                names.append(self._text(child, src))
            elif child.type == "aliased_import":
                name_node = child.child_by_field_name("name") or child.children[0]
                names.append(self._text(name_node, src))

        return ImportInfo(raw=raw, module=module, names=names, is_relative=is_relative)

    # ------------------------------------------------------------------
    # Functions
    # ------------------------------------------------------------------

    def _extract_top_level_functions(self, root: Node, src: bytes) -> list[FunctionInfo]:
        functions = []
        for child in root.children:
            if child.type == "function_definition":
                functions.append(self._parse_function(child, src, decorators=[]))
            elif child.type == "decorated_definition":
                decorators, inner = self._split_decorated(child, src)
                if inner and inner.type == "function_definition":
                    functions.append(self._parse_function(inner, src, decorators=decorators))
        return functions

    def _parse_function(
        self, node: Node, src: bytes, decorators: list[str]
    ) -> FunctionInfo:
        is_async = any(c.type == "async" for c in node.children)
        name_node = next((c for c in node.children if c.type == "identifier"), None)
        name = self._text(name_node, src) if name_node else "<unknown>"

        params_node = node.child_by_field_name("parameters")
        params = self._extract_params(params_node, src) if params_node else []

        return_node = node.child_by_field_name("return_type")
        return_type = self._text(return_node, src) if return_node else None

        return FunctionInfo(
            name=name,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            params=params,
            is_async=is_async,
            decorators=decorators,
            return_type=return_type,
        )

    def _extract_params(self, params_node: Node, src: bytes) -> list[str]:
        params = []
        for child in params_node.children:
            if child.type in (
                "identifier", "typed_parameter", "typed_default_parameter",
                "default_parameter", "list_splat_pattern", "dictionary_splat_pattern",
                "keyword_separator",
            ):
                name_node = next(
                    (c for c in child.children if c.type == "identifier"), None
                ) if child.type not in ("identifier", "keyword_separator") else child
                if name_node and name_node.type == "identifier":
                    params.append(self._text(name_node, src))
        return params

    # ------------------------------------------------------------------
    # Classes
    # ------------------------------------------------------------------

    def _extract_classes(self, root: Node, src: bytes) -> list[ClassInfo]:
        classes = []
        for child in root.children:
            if child.type == "class_definition":
                classes.append(self._parse_class(child, src, decorators=[]))
            elif child.type == "decorated_definition":
                decorators, inner = self._split_decorated(child, src)
                if inner and inner.type == "class_definition":
                    classes.append(self._parse_class(inner, src, decorators=decorators))
        return classes

    def _parse_class(
        self, node: Node, src: bytes, decorators: list[str]
    ) -> ClassInfo:
        name_node = next((c for c in node.children if c.type == "identifier"), None)
        name = self._text(name_node, src) if name_node else "<unknown>"

        bases_node = node.child_by_field_name("superclasses")
        bases: list[str] = []
        if bases_node:
            for b in bases_node.children:
                if b.type in ("identifier", "dotted_name"):
                    bases.append(self._text(b, src))

        body_node = node.child_by_field_name("body")
        methods: list[FunctionInfo] = []
        if body_node:
            for child in body_node.children:
                if child.type == "function_definition":
                    methods.append(self._parse_function(child, src, decorators=[]))
                elif child.type == "decorated_definition":
                    decs, inner = self._split_decorated(child, src)
                    if inner and inner.type == "function_definition":
                        methods.append(self._parse_function(inner, src, decorators=decs))

        return ClassInfo(
            name=name,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            bases=bases,
            methods=methods,
            decorators=decorators,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _split_decorated(
        self, node: Node, src: bytes
    ) -> tuple[list[str], Node | None]:
        decorators = []
        inner = None
        for child in node.children:
            if child.type == "decorator":
                deco_text = self._text(child, src).lstrip("@").strip()
                decorators.append(deco_text)
            elif child.type in ("function_definition", "class_definition"):
                inner = child
        return decorators, inner

    def _classify_dependencies(
        self, imports: list[ImportInfo], file_path: str
    ) -> tuple[list[str], list[str]]:
        local: list[str] = []
        external: list[str] = []
        base_dir = Path(file_path).parent

        for imp in imports:
            if imp.is_relative:
                # Convert relative module to a relative file path
                parts = imp.module.replace(".", "/") if imp.module else ""
                candidate = str(base_dir / parts) + ".py" if parts else str(base_dir)
                local.append(candidate)
            else:
                # Heuristic: single-segment lowercase names starting without capital
                # are likely stdlib or third-party; project packages are harder to know
                # Without full project context, all absolute imports go to external
                external.append(imp.module.split(".")[0])

        return local, list(dict.fromkeys(external))
