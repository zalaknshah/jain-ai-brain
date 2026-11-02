from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from .models import CanonicalEntry, Memory


_STOPWORDS = {
    "about", "after", "again", "also", "answer", "could", "from", "have", "help",
    "into", "just", "like", "more", "should", "that", "their", "them", "there",
    "these", "they", "this", "using", "what", "when", "where", "which", "with",
    "would", "your",
}


def terms(text: str) -> set[str]:
    return {item for item in re.findall(r"[a-zA-Z][a-zA-Z0-9_-]{2,}", text.lower()) if item not in _STOPWORDS}


@dataclass(frozen=True)
class GraphHit:
    node_id: str
    node_type: str
    title: str
    content: str
    score: float
    depth: int
    source_id: str | None = None


class CognitiveGraph:
    """Persistent activation graph for local GraphRAG.

    This is a symbolic neural-network analogue: nodes are concepts/memories,
    edges are typed associations, and retrieval activates nearby nodes. It is
    not a claim of biological cognition or consciousness.
    """

    def __init__(self, db_path: str | Path) -> None:
        self._connection = sqlite3.connect(str(db_path), check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS graph_nodes (
                node_id TEXT PRIMARY KEY,
                node_type TEXT NOT NULL,
                title TEXT NOT NULL,
                content TEXT NOT NULL,
                source_id TEXT,
                immutable INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS graph_edges (
                from_id TEXT NOT NULL,
                to_id TEXT NOT NULL,
                relation TEXT NOT NULL,
                weight REAL NOT NULL DEFAULT 1.0,
                PRIMARY KEY(from_id, to_id, relation)
            );
            CREATE INDEX IF NOT EXISTS graph_edges_from ON graph_edges(from_id);
            CREATE INDEX IF NOT EXISTS graph_edges_to ON graph_edges(to_id);
            """
        )
        self._connection.commit()

    def seed_canonical(self, entries: list[CanonicalEntry]) -> None:
        """Insert canonical nodes and associations without overwriting content."""
        related_pairs = {
            frozenset({"ahimsa-001", "aparigraha-001"}),
            frozenset({"ahimsa-001", "anekanta-001"}),
            frozenset({"anekanta-001", "syadvada-001"}),
            frozenset({"ahimsa-001", "action-001"}),
            frozenset({"aparigraha-001", "action-001"}),
        }
        for entry in entries:
            self._connection.execute(
                "INSERT OR IGNORE INTO graph_nodes(node_id, node_type, title, content, source_id, immutable) VALUES (?, 'canonical', ?, ?, ?, 1)",
                (f"canonical:{entry.entry_id}", entry.title, f"{entry.principle} {entry.guidance} {entry.source} {entry.work or ''} {' '.join(entry.tags)}", entry.entry_id),
            )
        for left in entries:
            for right in entries:
                if left.entry_id >= right.entry_id:
                    continue
                overlap = terms(" ".join(left.tags)) & terms(" ".join(right.tags))
                if overlap or frozenset({left.entry_id, right.entry_id}) in related_pairs:
                    weight = 0.5 + 0.1 * len(overlap)
                    self._connection.execute(
                        "INSERT OR IGNORE INTO graph_edges(from_id, to_id, relation, weight) VALUES (?, ?, 'related_principle', ?)",
                        (f"canonical:{left.entry_id}", f"canonical:{right.entry_id}", weight),
                    )
                    self._connection.execute(
                        "INSERT OR IGNORE INTO graph_edges(from_id, to_id, relation, weight) VALUES (?, ?, 'related_principle', ?)",
                        (f"canonical:{right.entry_id}", f"canonical:{left.entry_id}", weight),
                    )
        self._connection.commit()

    def add_memory(self, memory: Memory, canonical: list[CanonicalEntry]) -> None:
        node_id = f"memory:{memory.memory_id}"
        self._connection.execute(
            "INSERT OR IGNORE INTO graph_nodes(node_id, node_type, title, content, source_id, immutable) VALUES (?, 'memory', ?, ?, ?, 0)",
            (node_id, f"Memory for {memory.user_id}", memory.content, str(memory.memory_id)),
        )
        memory_terms = terms(memory.content)
        for entry in canonical:
            overlap = memory_terms & terms(f"{entry.title} {entry.principle} {entry.guidance} {' '.join(entry.tags)}")
            if overlap:
                self._connection.execute(
                    "INSERT OR REPLACE INTO graph_edges(from_id, to_id, relation, weight) VALUES (?, ?, 'aligned_with', ?)",
                    (node_id, f"canonical:{entry.entry_id}", min(1.0, 0.55 + 0.1 * len(overlap))),
                )
        self._connection.commit()

    def retrieve(self, query: str, user_id: str, max_hops: int = 2, max_nodes: int = 12) -> list[GraphHit]:
        """Run bounded seed → expand → rerank retrieval."""
        query_terms = terms(query)
        if not query_terms:
            return []
        rows = self._connection.execute(
            "SELECT node_id, node_type, title, content, source_id FROM graph_nodes WHERE node_type = 'canonical' OR (node_type = 'memory' AND node_id IN (SELECT 'memory:' || id FROM memories WHERE user_id = ?))",
            (user_id,),
        ).fetchall()
        nodes = {row["node_id"]: row for row in rows}
        active: dict[str, tuple[float, int]] = {}
        for node_id, row in nodes.items():
            overlap = len(query_terms & terms(f"{row['title']} {row['content']}"))
            if overlap:
                active[node_id] = (min(1.0, 0.25 * overlap), 0)

        frontier = set(active)
        for depth in range(1, max_hops + 1):
            if not frontier:
                break
            placeholders = ",".join("?" for _ in frontier)
            edges = self._connection.execute(
                f"SELECT from_id, to_id, weight FROM graph_edges WHERE from_id IN ({placeholders}) OR to_id IN ({placeholders})",
                tuple(frontier) + tuple(frontier),
            ).fetchall()
            next_frontier: set[str] = set()
            for edge in edges:
                neighbour = edge["to_id"] if edge["from_id"] in frontier else edge["from_id"]
                if neighbour not in nodes or neighbour in active:
                    continue
                parent = edge["from_id"] if edge["from_id"] in active else edge["to_id"]
                parent_score = active.get(parent, (0.0, depth - 1))[0]
                active[neighbour] = (parent_score * float(edge["weight"]) * 0.7, depth)
                next_frontier.add(neighbour)
            frontier = next_frontier

        ranked = sorted(active.items(), key=lambda item: (-item[1][0], item[1][1], item[0]))[:max_nodes]
        return [
            GraphHit(node_id, nodes[node_id]["node_type"], nodes[node_id]["title"], nodes[node_id]["content"], score, depth, nodes[node_id]["source_id"])
            for node_id, (score, depth) in ranked
        ]

    def stats(self) -> dict[str, int]:
        return {
            "nodes": self._connection.execute("SELECT COUNT(*) FROM graph_nodes").fetchone()[0],
            "edges": self._connection.execute("SELECT COUNT(*) FROM graph_edges").fetchone()[0],
        }

    def remove_memories(self, memory_ids: list[int]) -> None:
        for memory_id in memory_ids:
            node_id = f"memory:{memory_id}"
            self._connection.execute("DELETE FROM graph_edges WHERE from_id = ? OR to_id = ?", (node_id, node_id))
            self._connection.execute("DELETE FROM graph_nodes WHERE node_id = ? AND immutable = 0", (node_id,))
        self._connection.commit()

    def close(self) -> None:
        self._connection.close()
