from __future__ import annotations
import operator
from typing import Annotated, TypedDict


class MigrationState(TypedDict):
    # ── Job metadata ────────────────────────────────────────────────
    job_id: str
    source_language: str
    target_language: str

    # ── Input ───────────────────────────────────────────────────────
    repo_url: str | None          # GitHub HTTPS URL (mutually exclusive with zip_path)
    zip_path: str | None          # Absolute path to an uploaded ZIP file
    repo_root: str | None         # Set after clone/extract; absolute path on disk

    # ── INGEST output ───────────────────────────────────────────────
    repo_files: list[dict]        # List of RepoFile.model_dump() dicts

    # ── PROFILE output ──────────────────────────────────────────────
    parsed_files: list[dict]      # List of ParsedFile.model_dump() dicts

    # ── CLASSIFY output ─────────────────────────────────────────────
    dependency_graph: dict        # DependencyGraph.to_dict() snapshot
    topological_order: list[str]  # File paths in dependency-first order
    circular_dependencies: list[list[str]]
    is_too_complex: bool          # Triggers WARN branch if True
    complexity_warning: str | None

    # ── RANK output ─────────────────────────────────────────────────
    plan_risk_summary: dict       # Per-file risk analysis shown on the Review page

    # ── Execution loop (PICK_NEXT → COMMIT) ─────────────────────────
    current_file: str | None          # Relative path of file being converted
    current_source: str | None        # Original source text
    current_converted: str | None     # LLM-generated converted code (latest attempt)
    current_context: list[dict]       # Already-converted dependencies for prompt context
    current_validation_errors: list[dict]
    self_correction_attempts: int     # Reset to 0 for each new file

    # ── Accumulated results ──────────────────────────────────────────
    converted_files: dict[str, str]   # file_path -> converted_source
    failed_files: list[str]           # Files that failed all retries
    flagged_files: list[str]          # Files flagged for human review

    # ── Final output ────────────────────────────────────────────────
    output_repo_path: str | None      # Where converted files were written
    pr_url: str | None                # GitHub PR URL (if created)
    commit_sha: str | None            # Final commit SHA

    # ── Diagnostics (append-only across all nodes) ───────────────────
    messages: Annotated[list[str], operator.add]
    error: str | None


def initial_state(
    job_id: str,
    source_language: str,
    target_language: str,
    repo_url: str | None = None,
    zip_path: str | None = None,
) -> MigrationState:
    """Return a fully initialised state dict ready to feed into the graph."""
    return MigrationState(
        job_id=job_id,
        source_language=source_language,
        target_language=target_language,
        repo_url=repo_url,
        zip_path=zip_path,
        repo_root=None,
        repo_files=[],
        parsed_files=[],
        dependency_graph={},
        topological_order=[],
        circular_dependencies=[],
        is_too_complex=False,
        complexity_warning=None,
        plan_risk_summary={},
        current_file=None,
        current_source=None,
        current_converted=None,
        current_context=[],
        current_validation_errors=[],
        self_correction_attempts=0,
        converted_files={},
        failed_files=[],
        flagged_files=[],
        output_repo_path=None,
        pr_url=None,
        commit_sha=None,
        messages=[],
        error=None,
    )
