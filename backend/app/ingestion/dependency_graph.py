from __future__ import annotations
from pathlib import Path, PurePosixPath

import networkx as nx

from app.code_analysis.models import ParsedFile

# Extensions to try when resolving bare JS/TS import paths
_JS_CANDIDATE_EXTS = [".js", ".jsx", ".ts", ".tsx", "/index.js", "/index.ts", "/index.jsx", "/index.tsx"]


class DependencyGraph:
    def __init__(self) -> None:
        self.graph: nx.DiGraph = nx.DiGraph()
        # Maps various path representations → canonical rel_path in graph
        self._path_index: dict[str, str] = {}

    # ------------------------------------------------------------------
    # Build
    # ------------------------------------------------------------------

    def build(self, parsed_files: list[ParsedFile], repo_root: str) -> nx.DiGraph:
        self.graph.clear()
        self._path_index.clear()

        # First pass: add every file as a node and build the path index
        for pf in parsed_files:
            self.graph.add_node(
                pf.file_path,
                language=pf.language,
                line_count=pf.line_count,
                complexity_score=pf.complexity_score,
                num_classes=len(pf.classes),
                num_functions=len(pf.functions),
                num_imports=len(pf.imports),
                status="pending",
            )
            self._index_path(pf.file_path, repo_root)

        # Second pass: resolve local deps → add edges
        for pf in parsed_files:
            for raw_dep in pf.local_dependencies:
                resolved = self._resolve(raw_dep, pf.file_path, repo_root)
                if resolved and resolved != pf.file_path:
                    self.graph.add_edge(pf.file_path, resolved)

            # For Python, also try each import's full module name as a local path.
            # external_dependencies only stores root package (e.g. "models"), but
            # pf.imports has the full dotted name (e.g. "models.user").
            if pf.language == "python":
                for imp in pf.imports:
                    if not imp.is_relative and imp.module:
                        resolved = self._resolve_python_module(imp.module)
                        if resolved and resolved != pf.file_path:
                            self.graph.add_edge(pf.file_path, resolved)

        return self.graph

    def _index_path(self, rel_path: str, repo_root: str) -> None:
        p = PurePosixPath(rel_path)
        self._path_index[rel_path] = rel_path
        # Without extension: "models/user"
        no_ext = str(p.with_suffix(""))
        self._path_index[no_ext] = rel_path
        # Stem only: "user"
        self._path_index[p.stem] = rel_path
        # Absolute-style
        self._path_index[str(Path(repo_root) / rel_path)] = rel_path
        # Python dotted module style: "models/user" → "models.user"
        self._path_index[no_ext.replace("/", ".")] = rel_path

    def _resolve(self, dep_path: str, from_file: str, repo_root: str) -> str | None:
        # Normalise separators
        dep = dep_path.replace("\\", "/")

        # Direct hit
        if dep in self._path_index:
            return self._path_index[dep]

        # Strip repo root prefix and try again
        rr = repo_root.replace("\\", "/").rstrip("/") + "/"
        if dep.startswith(rr):
            dep = dep[len(rr):]
            if dep in self._path_index:
                return self._path_index[dep]

        # Try adding common extensions (JS/TS bare paths)
        for ext in _JS_CANDIDATE_EXTS:
            candidate = dep.rstrip("/") + ext
            if candidate in self._path_index:
                return self._path_index[candidate]

        # Resolve relative paths against the importing file's directory
        from_dir = PurePosixPath(from_file.replace("\\", "/")).parent
        if dep.startswith("."):
            resolved = str(from_dir / dep).replace("\\", "/")
            if resolved in self._path_index:
                return self._path_index[resolved]
            for ext in _JS_CANDIDATE_EXTS:
                candidate = resolved.rstrip("/") + ext
                if candidate in self._path_index:
                    return self._path_index[candidate]

        return None

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get_topological_order(self) -> list[str]:
        """Files ordered so dependencies come before dependents (leaves first).

        Edges run importer → dependency, so nx.topological_sort puts importers
        first. We reverse to get dependencies (leaf nodes) first, which is the
        order we need: convert a dependency before anything that imports it.
        """
        try:
            return list(reversed(list(nx.topological_sort(self.graph))))
        except nx.NetworkXUnfeasible:
            dag = self._break_cycles()
            return list(reversed(list(nx.topological_sort(dag))))

    def get_circular_dependencies(self) -> list[list[str]]:
        return [list(c) for c in nx.simple_cycles(self.graph)]

    def get_dependencies(self, file_path: str) -> list[str]:
        """Files that file_path directly imports."""
        return list(self.graph.successors(file_path))

    def get_dependents(self, file_path: str) -> list[str]:
        """Files that directly import file_path."""
        return list(self.graph.predecessors(file_path))

    def get_all_dependencies(self, file_path: str) -> list[str]:
        """Transitive closure of dependencies."""
        return list(nx.descendants(self.graph, file_path))

    def get_all_dependents(self, file_path: str) -> list[str]:
        """Transitive closure of dependents."""
        return list(nx.ancestors(self.graph, file_path))

    def complexity_rank(self) -> list[tuple[str, float]]:
        """All files sorted by complexity descending."""
        return sorted(
            [(n, d["complexity_score"]) for n, d in self.graph.nodes(data=True)],
            key=lambda x: x[1],
            reverse=True,
        )

    def update_status(self, file_path: str, status: str) -> None:
        if file_path in self.graph:
            self.graph.nodes[file_path]["status"] = status

    def to_dict(self) -> dict:
        return {
            "nodes": [
                {"id": n, **d} for n, d in self.graph.nodes(data=True)
            ],
            "edges": [
                {"source": u, "target": v} for u, v in self.graph.edges()
            ],
            "node_count": self.graph.number_of_nodes(),
            "edge_count": self.graph.number_of_edges(),
            "has_cycles": not nx.is_directed_acyclic_graph(self.graph),
        }

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _resolve_python_module(self, module_name: str) -> str | None:
        """Try to match a Python dotted module name to a known project file."""
        # "models.user" → try "models/user", "models/user.py", "models/user/__init__.py"
        as_path = module_name.replace(".", "/")
        for candidate in (
            as_path,
            as_path + ".py",
            as_path + "/__init__.py",
            module_name,
        ):
            if candidate in self._path_index:
                return self._path_index[candidate]
        return None

    def _break_cycles(self) -> nx.DiGraph:
        """Return a DAG with cycle-creating edges removed (minimum feedback arc set heuristic)."""
        dag = self.graph.copy()
        for cycle in nx.simple_cycles(dag):
            if len(cycle) >= 2:
                dag.remove_edge(cycle[-1], cycle[0])
                if nx.is_directed_acyclic_graph(dag):
                    break
        return dag
