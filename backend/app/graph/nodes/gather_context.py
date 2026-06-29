from __future__ import annotations

from app.graph.state import MigrationState

# Max chars of converted source to include per dependency in the prompt
_MAX_CONTEXT_CHARS = 2000


def gather_context_node(state: MigrationState) -> dict:
    """GATHER_CTX: Collect already-converted dependencies to include in the LLM prompt."""
    current_file = state["current_file"]
    graph_dict = state.get("dependency_graph", {})
    converted_files = state.get("converted_files", {})

    if not current_file:
        return {"current_context": []}

    # Find direct dependencies of current_file from the graph edges
    deps: list[str] = [
        edge["target"]
        for edge in graph_dict.get("edges", [])
        if edge["source"] == current_file
    ]

    context: list[dict] = []
    for dep_path in deps:
        converted_src = converted_files.get(dep_path)
        if converted_src:
            # Find original source from parsed_files for reference
            original = next(
                (pf["raw_source"] for pf in state.get("parsed_files", [])
                 if pf["file_path"] == dep_path),
                None,
            )
            context.append({
                "file_path": dep_path,
                "original_source": (original or "")[:_MAX_CONTEXT_CHARS],
                "converted_source": converted_src[:_MAX_CONTEXT_CHARS],
            })

    msg = (
        f"[GATHER_CTX] {len(context)} converted dependencies available as context "
        f"for {current_file}."
    )
    return {"current_context": context, "messages": [msg]}
