from __future__ import annotations
import json
import re

from app.graph.state import MigrationState
from app.mcp_servers.plan_manager_server import initialize_plan


# ── Risk assessment ────────────────────────────────────────────────────────

def _assess_risk(
    file_path: str,
    raw_source: str,
    line_count: int,
    complexity_score: float,
    complexity_class: str,
    source_language: str,
    target_language: str,
    circular_deps: list[list[str]],
) -> dict:
    reasons: list[str] = []

    # Complexity
    if complexity_class == "complex":
        reasons.append(f"High complexity score ({complexity_score:.1f})")
    elif complexity_class == "moderate":
        reasons.append(f"Moderate complexity ({complexity_score:.1f})")

    # File size
    if line_count >= 500:
        reasons.append(f"Very large file ({line_count} lines) — LLM may truncate")
    elif line_count >= 200:
        reasons.append(f"Large file ({line_count} lines)")

    # Dynamic code execution (all languages)
    if re.search(r'\beval\s*\(', raw_source):
        reasons.append("Uses eval() — dynamic code execution is hard to convert")
    if re.search(r'\bexec\s*\(', raw_source):
        reasons.append("Uses exec() — dynamic code execution")

    if source_language == "python":
        if re.search(r'metaclass\s*=', raw_source):
            reasons.append("Uses metaclasses — advanced OOP, may not map cleanly")
        if re.search(r'__import__\s*\(', raw_source):
            reasons.append("Uses __import__() — dynamic import")
        if re.search(r'\bimportlib\b', raw_source):
            reasons.append("Uses importlib — dynamic module loading")
        if re.search(r'@\w[\w.]*\s*\n\s*(?:async\s+)?def ', raw_source):
            reasons.append("Uses decorators — verify they map to target idioms")
        if re.search(r'\basyncio\b|async def ', raw_source) and target_language in ("javascript", "typescript"):
            reasons.append("asyncio patterns — async conversion needs review")
        if re.search(r'\*args|\*\*kwargs', raw_source):
            reasons.append("Uses *args/**kwargs — variadic args may need adaptation")

    elif source_language in ("javascript", "typescript"):
        if re.search(r'require\s*\(\s*[`$]', raw_source):
            reasons.append("Dynamic require() — not statically analyzable")
        if re.search(r'__proto__', raw_source):
            reasons.append("Uses __proto__ — prototype manipulation")
        if re.search(r'Object\.setPrototypeOf\s*\(', raw_source):
            reasons.append("Sets prototype directly")
        if re.search(r'new Function\s*\(', raw_source):
            reasons.append("Uses new Function() — dynamic code")
        if re.search(r'\.bind\s*\(|\.call\s*\(|\.apply\s*\(', raw_source):
            reasons.append("Uses bind/call/apply — this-binding semantics differ in Python")
        if re.search(r'\bPromise\b|\bthen\s*\(|await ', raw_source) and target_language == "python":
            reasons.append("Promise/async patterns — asyncio conversion needs review")

    # Circular dependency involvement
    in_cycle = any(file_path in cycle for cycle in circular_deps)
    if in_cycle:
        reasons.append("Part of a circular dependency — conversion order may need manual adjustment")

    # Determine risk level
    if len(reasons) >= 4 or (complexity_class == "complex" and len(reasons) >= 2):
        risk_level = "high"
    elif len(reasons) >= 1:
        risk_level = "medium"
    else:
        risk_level = "low"

    return {
        "risk_level": risk_level,
        "reasons": reasons,
        "line_count": line_count,
        "complexity_score": round(complexity_score, 2),
        "complexity_class": complexity_class,
    }


# ── Node ──────────────────────────────────────────────────────────────────

def rank_node(state: MigrationState) -> dict:
    """RANK: Initialise the Plan Manager with topological order; add per-file risk assessment."""
    if state.get("error"):
        return {}

    job_id = state["job_id"]
    parsed_files = state["parsed_files"]
    topo_order = state["topological_order"]
    source_language = state["source_language"]
    target_language = state["target_language"]
    circular_deps: list[list[str]] = state.get("circular_dependencies", [])

    # Stable-sort: deeper deps first, simpler files first within same depth
    complexity_map: dict[str, float] = {
        pf["file_path"]: pf["complexity_score"] for pf in parsed_files
    }
    graph_dict = state.get("dependency_graph", {})
    edges: list[dict] = graph_dict.get("edges", [])
    depth: dict[str, int] = {fp: 0 for fp in topo_order}
    for edge in edges:
        src, tgt = edge["source"], edge["target"]
        depth[tgt] = max(depth.get(tgt, 0), depth.get(src, 0) + 1)

    ranked_order = sorted(
        topo_order,
        key=lambda fp: (-depth.get(fp, 0), complexity_map.get(fp, 0.0)),
    )

    # Initialise the in-memory plan manager
    result = json.loads(initialize_plan(
        job_id=job_id,
        source_language=source_language,
        target_language=target_language,
        parsed_files_json=json.dumps(parsed_files),
        topological_order_json=json.dumps(ranked_order),
    ))

    if not result.get("success"):
        return {
            "error": result.get("error", "Plan initialization failed."),
            "messages": ["[RANK] ERROR: failed to initialize plan manager."],
        }

    # Build risk summary for every file
    pf_map = {pf["file_path"]: pf for pf in parsed_files}
    plan_risk_summary: dict = {}
    for fp in ranked_order:
        pf = pf_map.get(fp, {})
        plan_risk_summary[fp] = _assess_risk(
            file_path=fp,
            raw_source=pf.get("raw_source", ""),
            line_count=pf.get("line_count", 0),
            complexity_score=float(pf.get("complexity_score", 0.0)),
            complexity_class=pf.get("complexity_class", "simple") if "complexity_class" in pf
                else ("complex" if float(pf.get("complexity_score", 0)) >= 6 else
                      "moderate" if float(pf.get("complexity_score", 0)) >= 3 else "simple"),
            source_language=source_language,
            target_language=target_language,
            circular_deps=circular_deps,
        )

    dist = result.get("complexity_distribution", {})
    high_risk = sum(1 for v in plan_risk_summary.values() if v["risk_level"] == "high")
    med_risk  = sum(1 for v in plan_risk_summary.values() if v["risk_level"] == "medium")

    return {
        "topological_order": ranked_order,
        "plan_risk_summary": plan_risk_summary,
        "messages": [
            f"[RANK] Plan ready: {result['total_files']} files | "
            f"complexity: simple={dist.get('simple', 0)} moderate={dist.get('moderate', 0)} "
            f"complex={dist.get('complex', 0)} | "
            f"risk: high={high_risk} medium={med_risk} low={result['total_files'] - high_risk - med_risk}"
        ],
    }
