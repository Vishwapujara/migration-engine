from __future__ import annotations
from pydantic import BaseModel, Field


class FunctionInfo(BaseModel):
    name: str
    start_line: int
    end_line: int
    params: list[str] = Field(default_factory=list)
    is_async: bool = False
    decorators: list[str] = Field(default_factory=list)
    return_type: str | None = None


class ClassInfo(BaseModel):
    name: str
    start_line: int
    end_line: int
    bases: list[str] = Field(default_factory=list)
    methods: list[FunctionInfo] = Field(default_factory=list)
    decorators: list[str] = Field(default_factory=list)


class ImportInfo(BaseModel):
    raw: str
    module: str
    names: list[str] = Field(default_factory=list)
    is_relative: bool = False
    alias: str | None = None


class ParsedFile(BaseModel):
    file_path: str
    language: str
    imports: list[ImportInfo] = Field(default_factory=list)
    classes: list[ClassInfo] = Field(default_factory=list)
    functions: list[FunctionInfo] = Field(default_factory=list)
    raw_source: str
    line_count: int
    complexity_score: float = Field(ge=0.0, le=10.0)
    local_dependencies: list[str] = Field(default_factory=list)
    external_dependencies: list[str] = Field(default_factory=list)

    def summary(self) -> dict:
        return {
            "file_path": self.file_path,
            "language": self.language,
            "line_count": self.line_count,
            "complexity_score": self.complexity_score,
            "num_classes": len(self.classes),
            "num_functions": len(self.functions),
            "num_imports": len(self.imports),
            "local_deps": self.local_dependencies,
        }
