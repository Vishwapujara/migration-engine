from __future__ import annotations

from app.graph.state import MigrationState
from app.code_analysis.models import ParsedFile
from app.ingestion.dependency_graph import DependencyGraph
from app.config import settings


def classify_node(state: MigrationState) -> dict:
    """CLASSIFY: Build dependency graph, detect cycles, flag overly complex codebases."""
    if state.get("error"):
        return {}

    parsed_files = [ParsedFile.model_validate(pf) for pf in state["parsed_files"]]
    repo_root = state.get("repo_root") or ""

    dg = DependencyGraph()
    dg.build(parsed_files, repo_root)

    topo_order = dg.get_topological_order()
    circular_deps = dg.get_circular_dependencies()
    graph_dict = dg.to_dict()

    total = len(parsed_files)
    cycle_count = len(circular_deps)

    is_too_complex = (
        total > settings.max_files_for_migration
        or cycle_count > 10
    )

    warning: str | None = None
    if is_too_complex:
        reasons: list[str] = []
        if total > settings.max_files_for_migration:
            reasons.append(
                f"{total} files exceeds the limit of {settings.max_files_for_migration}"
            )
        if cycle_count > 10:
            reasons.append(f"{cycle_count} circular dependency cycles detected")
        warning = "Complexity warning: " + "; ".join(reasons) + ". Migration will proceed with caution."

    complexity_dist = {"simple": 0, "moderate": 0, "complex": 0}
    for pf in parsed_files:
        s = pf.complexity_score
        if s < 3.0:
            complexity_dist["simple"] += 1
        elif s < 6.0:
            complexity_dist["moderate"] += 1
        else:
            complexity_dist["complex"] += 1

    return {
        "dependency_graph": graph_dict,
        "topological_order": topo_order,
        "circular_dependencies": circular_deps,
        "is_too_complex": is_too_complex,
        "complexity_warning": warning,
        "messages": [
            f"[CLASSIFY] {total} files | "
            f"{graph_dict['edge_count']} dependency edges | "
            f"{cycle_count} cycles | "
            f"complexity={complexity_dist} | "
            f"too_complex={is_too_complex}"
        ],
    }


def route_complexity(state: MigrationState) -> str:
    """Conditional edge: too_complex -> warn, else -> rank."""
    return "warn" if state.get("is_too_complex") else "rank"
