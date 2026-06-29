from __future__ import annotations
from pathlib import Path

from app.graph.state import MigrationState
from app.ingestion.repo_loader import clone_github_repo, extract_zip, walk_repo


def ingest_node(state: MigrationState) -> dict:
    """INGEST: Clone repo or extract ZIP, walk source files."""
    job_id = state["job_id"]
    source_language = state["source_language"]

    try:
        if state.get("repo_url"):
            repo_root = clone_github_repo(state["repo_url"], job_id)
            source = f"GitHub: {state['repo_url']}"
        elif state.get("zip_path"):
            repo_root = extract_zip(Path(state["zip_path"]), job_id)
            source = f"ZIP: {state['zip_path']}"
        else:
            return {
                "error": "No repo_url or zip_path provided.",
                "messages": ["[INGEST] ERROR: no input source specified."],
            }

        result = walk_repo(repo_root, source_language)

        return {
            "repo_root": str(repo_root),
            "repo_files": [f.model_dump() for f in result.files],
            "messages": [
                f"[INGEST] Source: {source}",
                f"[INGEST] Found {len(result.files)} {source_language} files "
                f"(skipped {result.skipped_count}, errors {result.error_count}).",
            ],
        }

    except Exception as exc:
        return {
            "error": str(exc),
            "messages": [f"[INGEST] ERROR: {exc}"],
        }
