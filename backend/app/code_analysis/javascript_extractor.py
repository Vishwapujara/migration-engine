from __future__ import annotations
from pathlib import Path

import tree_sitter_javascript as tsjs
from tree_sitter import Language, Node

from .base import LanguageExtractor
from .models import FunctionInfo, ClassInfo, ImportInfo


class JavaScriptExtractor(LanguageExtractor):
    language_name = "javascript"
    extensions = [".js", ".jsx", ".mjs", ".cjs"]

    def _build_language(self) -> Language:
        return Language(tsjs.language())

    # ------------------------------------------------------------------
    # Imports — node type is "import_statement" in tree-sitter-javascript
    # ------------------------------------------------------------------

    def _extract_imports(self, root: Node, src: bytes) -> list[ImportInfo]:
        imports: list[ImportInfo] = []
        seen: set[str] = set()

        for node in root.children:
            imp = None
            if node.type == "import_statement":
                imp = self._parse_import_statement(node, src)
            elif node.type in ("expression_statement",):
                # require() at top level: `require('x')` or `const x = require('x')`
                inner = node.children[0] if node.children else None
                if inner and inner.type == "call_expression":
                    imp = self._parse_require_call(inner, src)
            elif node.type in ("lexical_declaration", "variable_declaration"):
                for child in node.children:
                    if child.type == "variable_declarator":
                        val = child.child_by_field_name("value")
                        if val and val.type == "call_expression":
                            imp = self._parse_require_call(val, src)

            if imp and imp.raw not in seen:
                seen.add(imp.raw)
                imports.append(imp)

        return imports

    def _parse_import_statement(self, node: Node, src: bytes) -> ImportInfo | None:
        raw = self._text(node, src)

        # Source string is a direct child of type "string"
        string_node = next((c for c in node.children if c.type == "string"), None)
        if not string_node:
            return None

        # Get the actual text from the string_fragment child
        fragment = next(
            (c for c in string_node.children if c.type == "string_fragment"), None
        )
        module = self._text(fragment, src) if fragment else self._text(string_node, src).strip("'\"")

        names: list[str] = []
        clause = next((c for c in node.children if c.type == "import_clause"), None)
        if clause:
            for child in clause.children:
                if child.type == "identifier":
                    # default import: `import React from 'react'`
                    names.append(self._text(child, src))
                elif child.type == "named_imports":
                    for spec in child.children:
                        if spec.type == "import_specifier":
                            name_node = next(
                                (c for c in spec.children if c.type == "identifier"), None
                            )
                            if name_node:
                                names.append(self._text(name_node, src))
                elif child.type == "namespace_import":
                    names.append("*")

        is_relative = module.startswith(".") or module.startswith("/")
        return ImportInfo(raw=raw, module=module, names=names, is_relative=is_relative)

    def _parse_require_call(self, node: Node, src: bytes) -> ImportInfo | None:
        func_node = node.child_by_field_name("function")
        if not func_node or self._text(func_node, src) != "require":
            return None
        args_node = node.child_by_field_name("arguments")
        if not args_node:
            return None
        string_node = next((c for c in args_node.children if c.type == "string"), None)
        if not string_node:
            return None
        fragment = next(
            (c for c in string_node.children if c.type == "string_fragment"), None
        )
        module = self._text(fragment, src) if fragment else self._text(string_node, src).strip("'\"")
        is_relative = module.startswith(".") or module.startswith("/")
        return ImportInfo(raw=self._text(node, src), module=module, names=[], is_relative=is_relative)

    # ------------------------------------------------------------------
    # Functions
    # ------------------------------------------------------------------

    def _extract_top_level_functions(self, root: Node, src: bytes) -> list[FunctionInfo]:
        functions = []
        for child in root.children:
            fn = self._try_extract_function(child, src)
            if fn:
                functions.append(fn)
        return functions

    def _try_extract_function(self, node: Node, src: bytes) -> FunctionInfo | None:
        if node.type == "function_declaration":
            return self._parse_function_declaration(node, src)

        if node.type in ("lexical_declaration", "variable_declaration"):
            for child in node.children:
                if child.type == "variable_declarator":
                    value_node = child.child_by_field_name("value")
                    name_node = child.child_by_field_name("name")
                    if value_node and value_node.type in (
                        "arrow_function", "function_expression"
                    ) and name_node:
                        return self._parse_arrow_or_expr(value_node, name_node, src)

        if node.type == "export_statement":
            for child in node.children:
                fn = self._try_extract_function(child, src)
                if fn:
                    return fn

        return None

    def _parse_function_declaration(self, node: Node, src: bytes) -> FunctionInfo:
        is_async = any(c.type == "async" for c in node.children)
        name_node = node.child_by_field_name("name")
        name = self._text(name_node, src) if name_node else "<anonymous>"
        params = self._extract_params(node.child_by_field_name("parameters"), src)
        return FunctionInfo(
            name=name,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            params=params,
            is_async=is_async,
        )

    def _parse_arrow_or_expr(
        self, fn_node: Node, name_node: Node, src: bytes
    ) -> FunctionInfo:
        is_async = any(c.type == "async" for c in fn_node.children)
        name = self._text(name_node, src)
        params_node = fn_node.child_by_field_name("parameters") or fn_node.child_by_field_name("parameter")
        params = self._extract_params(params_node, src) if params_node else []
        return FunctionInfo(
            name=name,
            start_line=fn_node.start_point[0] + 1,
            end_line=fn_node.end_point[0] + 1,
            params=params,
            is_async=is_async,
        )

    def _extract_params(self, params_node: Node | None, src: bytes) -> list[str]:
        if not params_node:
            return []
        params = []
        for child in params_node.children:
            if child.type == "identifier":
                params.append(self._text(child, src))
            elif child.type in (
                "required_parameter", "optional_parameter", "rest_pattern",
                "assignment_pattern",
            ):
                name_node = next(
                    (c for c in child.children if c.type == "identifier"), None
                )
                if name_node:
                    params.append(self._text(name_node, src))
        return params

    # ------------------------------------------------------------------
    # Classes — heritage is a child node of type "class_heritage", not a field
    # ------------------------------------------------------------------

    def _extract_classes(self, root: Node, src: bytes) -> list[ClassInfo]:
        classes = []
        for child in root.children:
            cls = self._try_extract_class(child, src)
            if cls:
                classes.append(cls)
        return classes

    def _try_extract_class(self, node: Node, src: bytes) -> ClassInfo | None:
        if node.type == "class_declaration":
            return self._parse_class(node, src)
        if node.type == "export_statement":
            for child in node.children:
                cls = self._try_extract_class(child, src)
                if cls:
                    return cls
        return None

    def _parse_class(self, node: Node, src: bytes) -> ClassInfo:
        name_node = node.child_by_field_name("name")
        name = self._text(name_node, src) if name_node else "<anonymous>"

        # class_heritage is a sibling child node, not a named field
        bases: list[str] = []
        heritage_node = next(
            (c for c in node.children if c.type == "class_heritage"), None
        )
        if heritage_node:
            for child in heritage_node.children:
                if child.type in ("identifier", "member_expression"):
                    bases.append(self._text(child, src))

        methods: list[FunctionInfo] = []
        body_node = node.child_by_field_name("body")
        if body_node:
            for child in body_node.children:
                if child.type == "method_definition":
                    m = self._parse_method(child, src)
                    if m:
                        methods.append(m)

        return ClassInfo(
            name=name,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            bases=bases,
            methods=methods,
        )

    def _parse_method(self, node: Node, src: bytes) -> FunctionInfo | None:
        # Methods use property_identifier for the name, not identifier
        name_node = next(
            (c for c in node.children if c.type in ("property_identifier", "identifier")),
            None,
        )
        if not name_node:
            return None
        name = self._text(name_node, src)
        is_async = any(c.type == "async" for c in node.children)
        # JS methods use formal_parameters, not parameters
        params_node = next(
            (c for c in node.children if c.type in ("formal_parameters", "parameters")),
            None,
        )
        params = self._extract_params(params_node, src)
        return FunctionInfo(
            name=name,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            params=params,
            is_async=is_async,
        )

    # ------------------------------------------------------------------
    # Dependencies
    # ------------------------------------------------------------------

    def _classify_dependencies(
        self, imports: list[ImportInfo], file_path: str
    ) -> tuple[list[str], list[str]]:
        local: list[str] = []
        external: list[str] = []
        base_dir = Path(file_path).parent

        for imp in imports:
            module = imp.module
            if module.startswith(".") or module.startswith("/"):
                local.append(str(base_dir / module))
            else:
                # Strip scoped package prefix for the root package name
                pkg = module.lstrip("@").split("/")[0]
                external.append(pkg)

        return list(dict.fromkeys(local)), list(dict.fromkeys(external))
