from __future__ import annotations
import shutil
import zipfile
from pathlib import Path

from git import Repo
from pydantic import BaseModel

from app.config import settings, LANGUAGE_EXTENSIONS, SKIP_DIRS, SKIP_EXTENSIONS
from app.code_analysis.registry import detect_language, parse_file
from app.code_analysis.models import ParsedFile


class RepoFile(BaseModel):
    rel_path: str
    abs_path: str
    source: str
    language: str
    size_kb: float


class LoadResult(BaseModel):
    repo_root: str
    files: list[RepoFile]
    parsed: list[ParsedFile]
    source_language: str
    skipped_count: int
    error_count: int


def clone_github_repo(url: str, job_id: str) -> Path:
    target = settings.workspace_dir / job_id / "repo"
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True)

    clone_kwargs: dict = {"to_path": str(target), "depth": 1}
    if settings.github_token:
        # Inject token into HTTPS URL for private repos
        if url.startswith("https://"):
            url = url.replace("https://", f"https://{settings.github_token}@", 1)

    Repo.clone_from(url, **clone_kwargs)
    return target


def extract_zip(zip_path: Path, job_id: str) -> Path:
    target = settings.workspace_dir / job_id / "repo"
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True)

    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(target)

    # If the ZIP contained a single top-level folder, descend into it
    contents = list(target.iterdir())
    if len(contents) == 1 and contents[0].is_dir():
        return contents[0]
    return target


def walk_repo(repo_root: Path, source_language: str) -> LoadResult:
    allowed_exts = set(LANGUAGE_EXTENSIONS.get(source_language, []))
    max_bytes = settings.max_file_size_kb * 1024

    files: list[RepoFile] = []
    parsed: list[ParsedFile] = []
    skipped = 0
    errors = 0

    for abs_path in _iter_files(repo_root):
        rel_path = abs_path.relative_to(repo_root).as_posix()

        if abs_path.suffix.lower() not in allowed_exts:
            skipped += 1
            continue

        if abs_path.stat().st_size > max_bytes:
            skipped += 1
            continue

        try:
            source = abs_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            errors += 1
            continue

        lang = detect_language(str(abs_path))
        if lang is None:
            skipped += 1
            continue

        rf = RepoFile(
            rel_path=rel_path,
            abs_path=str(abs_path),
            source=source,
            language=lang,
            size_kb=round(abs_path.stat().st_size / 1024, 2),
        )
        files.append(rf)

        pf = parse_file(rel_path, source)
        if pf:
            parsed.append(pf)
        else:
            errors += 1

    return LoadResult(
        repo_root=str(repo_root),
        files=files,
        parsed=parsed,
        source_language=source_language,
        skipped_count=skipped,
        error_count=errors,
    )


def _iter_files(root: Path):
    for item in root.rglob("*"):
        if not item.is_file():
            continue
        # Skip any path component that matches a skip-dir name
        if any(part in SKIP_DIRS for part in item.parts):
            continue
        if item.suffix.lower() in SKIP_EXTENSIONS:
            continue
        yield item
