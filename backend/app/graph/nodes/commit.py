from __future__ import annotations
import json
from pathlib import Path

from app.graph.state import MigrationState
from app.config import settings
from app.mcp_servers.plan_manager_server import (
    update_file_status,
    get_progress,
    get_full_plan,
)

_TARGET_EXTENSION: dict[tuple[str, str], str] = {
    ("python", "javascript"): ".js",
    ("javascript", "python"): ".py",
    ("javascript", "typescript"): ".ts",
}

_SOURCE_EXTENSIONS: dict[str, list[str]] = {
    "python": [".py"],
    "javascript": [".js", ".jsx", ".mjs", ".cjs"],
    "typescript": [".ts", ".tsx"],
}


def _converted_path(file_path: str, src_lang: str, tgt_lang: str) -> str:
    """Return the file_path with its extension swapped to the target language."""
    p = Path(file_path)
    tgt_ext = _TARGET_EXTENSION.get((src_lang, tgt_lang), p.suffix)
    # Keep .jsx → .tsx for JS→TS; otherwise apply the mapping
    if src_lang == "javascript" and tgt_lang == "typescript" and p.suffix == ".jsx":
        tgt_ext = ".tsx"
    return str(p.with_suffix(tgt_ext))


def commit_node(state: MigrationState) -> dict:
    """COMMIT: Write the converted file to disk, record it in the plan, loop to PICK_NEXT."""
    file_path = state.get("current_file")
    if not file_path:
        return {}

    converted = state.get("current_converted") or ""
    job_id = state["job_id"]
    src_lang = state["source_language"]
    tgt_lang = state["target_language"]

    # Determine output path
    out_rel = _converted_path(file_path, src_lang, tgt_lang)
    out_abs = settings.workspace_dir / job_id / "output" / out_rel
    out_abs.parent.mkdir(parents=True, exist_ok=True)
    out_abs.write_text(converted, encoding="utf-8")

    # Update plan manager
    update_file_status(
        job_id, file_path, "converted",
        converted_source=converted,
        validation_errors=json.dumps([]),
    )

    # Accumulate converted_files (return a new dict — LangGraph replaces the field)
    updated_converted = {**state.get("converted_files", {}), file_path: converted}

    return {
        "converted_files": updated_converted,
        "current_file": None,
        "current_source": None,
        "current_converted": None,
        "current_validation_errors": [],
        "messages": [f"[COMMIT] {file_path} -> {out_rel} ({len(converted)} chars)."],
    }


def flag_node(state: MigrationState) -> dict:
    """FLAG: Mark file as requiring human review after max retries exceeded."""
    file_path = state.get("current_file")
    if not file_path:
        return {}

    job_id = state["job_id"]
    errors = state.get("current_validation_errors", [])

    update_file_status(
        job_id, file_path, "flagged",
        converted_source=state.get("current_converted") or "",
        validation_errors=json.dumps(errors),
    )

    updated_flagged = state.get("flagged_files", []) + [file_path]

    return {
        "flagged_files": updated_flagged,
        "current_file": None,
        "current_source": None,
        "current_converted": None,
        "current_validation_errors": [],
        "messages": [
            f"[FLAG] {file_path} flagged for human review "
            f"({len(errors)} unresolved errors after "
            f"{state.get('self_correction_attempts', 0)} retries)."
        ],
    }


def done_node(state: MigrationState) -> dict:
    """DONE: Write final report; optionally create git commit and GitHub PR."""
    job_id = state["job_id"]

    progress = json.loads(get_progress(job_id))
    full_plan = json.loads(get_full_plan(job_id))

    # Write JSON report
    output_dir = settings.workspace_dir / job_id / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / "migration_report.json"

    report = {
        "job_id": job_id,
        "source_language": state["source_language"],
        "target_language": state["target_language"],
        "stats": progress,
        "converted_files": list(state.get("converted_files", {}).keys()),
        "failed_files": state.get("failed_files", []),
        "flagged_files": state.get("flagged_files", []),
        "circular_dependencies": state.get("circular_dependencies", []),
        "complexity_warning": state.get("complexity_warning"),
        "output_directory": str(output_dir),
    }
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    # Write Markdown summary
    md_path = output_dir / "migration_report.md"
    md_lines = [
        f"# Migration Report: {state['source_language']} → {state['target_language']}",
        "",
        f"**Job ID:** {job_id}",
        f"**Total files:** {progress['total']}",
        f"**Converted:** {progress['converted']}",
        f"**Flagged:** {progress['flagged']}",
        f"**Failed:** {progress['failed']}",
        f"**Completion:** {progress['percent_complete']}%",
        "",
        "## Files",
    ]
    for entry in full_plan.get("files", []):
        icon = {"converted": "✅", "flagged": "⚠️", "failed": "❌", "pending": "⏳"}.get(
            entry["status"], "?"
        )
        md_lines.append(f"- {icon} `{entry['file_path']}` ({entry['complexity_class']})")
    md_path.write_text("\n".join(md_lines), encoding="utf-8")

    msgs = [
        f"[DONE] Migration complete: "
        f"{progress['converted']}/{progress['total']} converted, "
        f"{progress['flagged']} flagged.",
        f"[DONE] Report written to {output_dir}",
    ]

    if state.get("complexity_warning"):
        msgs.append(f"[DONE] Note: {state['complexity_warning']}")

    return {
        "output_repo_path": str(output_dir),
        "messages": msgs,
    }
