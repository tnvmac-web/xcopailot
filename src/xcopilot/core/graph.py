"""Knowledge graph — structural project indexing with NetworkX."""

from __future__ import annotations

import ast
from pathlib import Path

import networkx as nx
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer


class _GraphFileHandler(FileSystemEventHandler):
    """Watchdog handler for project file changes."""

    def __init__(self, graph: KnowledgeGraph) -> None:
        self.graph = graph

    def on_modified(self, event) -> None:
        if event.src_path.endswith(".py"):
            self.graph.rebuild_file(event.src_path)

    def on_created(self, event) -> None:
        if event.src_path.endswith(".py"):
            self.graph.rebuild_file(event.src_path)

    def on_deleted(self, event) -> None:
        if event.src_path.endswith(".py"):
            self.graph.remove_file(event.src_path)


class KnowledgeGraph:
    """NetworkX-based knowledge graph for code structure."""

    def __init__(self) -> None:
        self.graph = nx.DiGraph()
        self.project_root: Path | None = None
        self._watcher: Observer | None = None
        self._handler: _GraphFileHandler | None = None

    def build(self, project_root: str) -> None:
        """Build knowledge graph from all Python files in project."""
        self.project_root = Path(project_root)
        self.graph.clear()

        for py_file in self.project_root.rglob("*.py"):
            if "__pycache__" in str(py_file):
                continue
            self._parse_file(py_file)

    def _parse_file(self, file_path: Path) -> None:
        """Parse a Python file and add nodes/edges to graph."""
        try:
            content = file_path.read_text(encoding="utf-8")
            tree = ast.parse(content)
        except (SyntaxError, UnicodeDecodeError):
            return

        rel_path = str(file_path.relative_to(self.project_root))

        # Add file node
        self.graph.add_node(rel_path, type="file")

        # Extract imports
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    self.graph.add_node(alias.name, type="module")
                    self.graph.add_edge(rel_path, alias.name, relation="imports")
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                for alias in node.names:
                    full_name = f"{module}.{alias.name}" if module else alias.name
                    self.graph.add_node(full_name, type="module")
                    self.graph.add_edge(rel_path, full_name, relation="imports_from")

            # Extract function/class definitions
            if isinstance(node, ast.FunctionDef):
                func_name = f"{rel_path}::{node.name}"
                self.graph.add_node(func_name, type="function", file=rel_path)
                self.graph.add_edge(rel_path, func_name, relation="defines")
            elif isinstance(node, ast.ClassDef):
                class_name = f"{rel_path}::{node.name}"
                self.graph.add_node(class_name, type="class", file=rel_path)
                self.graph.add_edge(rel_path, class_name, relation="defines")

    def rebuild_file(self, file_path: str) -> None:
        """Rebuild graph for a single changed file."""
        path = Path(file_path)
        if self.project_root and path.is_relative_to(self.project_root):
            rel_path = str(path.relative_to(self.project_root))
            # Remove old nodes for this file
            nodes_to_remove = [
                n
                for n, d in self.graph.nodes(data=True)
                if d.get("file") == rel_path or n == rel_path
            ]
            self.graph.remove_nodes_from(nodes_to_remove)
            # Re-parse
            self._parse_file(path)

    def remove_file(self, file_path: str) -> None:
        """Remove file from graph."""
        path = Path(file_path)
        if self.project_root and path.is_relative_to(self.project_root):
            rel_path = str(path.relative_to(self.project_root))
            nodes_to_remove = [
                n
                for n, d in self.graph.nodes(data=True)
                if d.get("file") == rel_path or n == rel_path
            ]
            self.graph.remove_nodes_from(nodes_to_remove)

    def query(self, query_str: str) -> list:
        """Search graph for nodes matching query."""
        results = []
        query_lower = query_str.lower()
        query_words = query_lower.split()

        for node, data in self.graph.nodes(data=True):
            # Check node name for any query word
            node_lower = node.lower()
            if (
                any(word in node_lower for word in query_words)
                or any(word in str(data).lower() for word in query_words)
                or data.get("type") in ("function", "class")
                and any(word in node_lower for word in query_words)
            ):
                results.append({"node": node, **data})

        # Also check edges for relation matches
        for u, v, data in self.graph.edges(data=True):
            relation = data.get("relation", "")
            if any(word in relation.lower() for word in query_words):
                # Add both nodes
                if u not in [r["node"] for r in results]:
                    results.append({"node": u, **self.graph.nodes[u]})
                if v not in [r["node"] for r in results]:
                    results.append({"node": v, **self.graph.nodes[v]})

        return results

    def stats(self) -> dict:
        """Return graph statistics."""
        return {
            "nodes": self.graph.number_of_nodes(),
            "edges": self.graph.number_of_edges(),
            "density": nx.density(self.graph) if self.graph.number_of_nodes() > 0 else 0,
        }

    def node_count(self) -> int:
        """Return number of nodes."""
        return self.graph.number_of_nodes()

    def edge_count(self) -> int:
        """Return number of edges."""
        return self.graph.number_of_edges()

    def watch_changes(self) -> Observer:
        """Start watching project files for changes."""
        if self._watcher is not None:
            self._watcher.stop()

        self._handler = _GraphFileHandler(self)
        self._watcher = Observer()

        if self.project_root:
            self._watcher.schedule(self._handler, str(self.project_root), recursive=True)

        self._watcher.start()
        return self._watcher

    def stop_watching(self) -> None:
        """Stop the file watcher."""
        if self._watcher is not None:
            self._watcher.stop()
            self._watcher.join(timeout=1.0)
            self._watcher = None
            self._handler = None
