from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from .models import CanonicalEntry, Memory
from .text import lexical_terms
from .retrieval_limits import ScanBudget, query_terms as bounded_query_terms, result_limit
from . import retrieval_limits
from .memory_scope import DEFAULT_SCOPE, validate_memory_scope
from .temporal import eligible_for_recall, normalize_expiration, recall_time


_STOPWORDS = {
    "about", "after", "again", "also", "answer", "could", "from", "have", "help",
    "into", "just", "like", "more", "should", "that", "their", "them", "there",
    "these", "they", "this", "using", "what", "when", "where", "which", "with",
    "would", "your",
}


def terms(text: str) -> set[str]:
    return {item for item in lexical_terms(text)
            if item not in _STOPWORDS and (not item.isascii() or len(item) >= 3)}


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

    def __init__(self, db_path: str | Path, connection: sqlite3.Connection | None = None) -> None:
        self._owns_connection = connection is None
        self._connection = connection if connection is not None else sqlite3.connect(str(db_path), check_same_thread=False)
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
        self._canonical_node_ids: dict[str, str] = {}
        self._canonical_prefix = "canonical:unbound:"

    def seed_canonical(self, entries: list[CanonicalEntry]) -> None:
        """Bind this graph instance to one immutable, content-addressed corpus.

        Legacy and other-version nodes stay on disk but are never admitted to
        this instance's retrieval scope. Shared-DB engines may use different
        corpora without rewriting one another's evidence or private memories.
        """
        payload = json.dumps([entry.to_dict() for entry in sorted(entries, key=lambda item: item.entry_id)],
                             sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        version = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        node_ids = {entry.entry_id: f"canonical:{version}:{entry.entry_id}" for entry in entries}
        if len(node_ids) != len(entries):
            raise ValueError("Canonical entry IDs must be unique")
        # Publish the active in-memory scope only after all nodes and edges
        # commit; a failed startup/rebind leaves the previous scope unchanged.
        with self._connection:
            self._connection.execute("BEGIN IMMEDIATE")
            self._seed_canonical(entries, node_ids)
        self._canonical_node_ids = node_ids
        self._canonical_prefix = f"canonical:{version}:"

    def _seed_canonical(self, entries: list[CanonicalEntry], node_ids: dict[str, str]) -> None:
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
                (node_ids[entry.entry_id], entry.title, f"{entry.principle} {entry.guidance} {entry.source} {entry.work or ''} {' '.join(entry.tags)}", entry.entry_id),
            )
        for left in entries:
            for right in entries:
                if left.entry_id >= right.entry_id:
                    continue
                overlap = terms(" ".join(left.tags)) & terms(" ".join(right.tags))
                if overlap or frozenset({left.entry_id, right.entry_id}) in related_pairs:
                    weight = 0.5 + 0.1 * len(overlap)
                    for first, second in [(left.entry_id, right.entry_id), (right.entry_id, left.entry_id)]:
                        self._connection.execute(
                            "INSERT OR IGNORE INTO graph_edges(from_id, to_id, relation, weight) VALUES (?, ?, 'related_principle', ?)",
                            (node_ids[first], node_ids[second], weight),
                        )

    def add_memory(self, memory: Memory, canonical: list[CanonicalEntry], *, commit: bool = True) -> None:
        node_id = f"memory:{memory.memory_id}"
        self._connection.execute(
            "INSERT OR IGNORE INTO graph_nodes(node_id, node_type, title, content, source_id, immutable) VALUES (?, 'memory', ?, ?, ?, 0)",
            (node_id, f"Memory for {memory.user_id}", memory.content, str(memory.memory_id)),
        )
        memory_terms = terms(memory.content)
        for entry in canonical:
            if entry.entry_id not in self._canonical_node_ids:
                continue
            overlap = memory_terms & terms(f"{entry.title} {entry.principle} {entry.guidance} {' '.join(entry.tags)}")
            if overlap:
                self._connection.execute(
                    "INSERT OR REPLACE INTO graph_edges(from_id, to_id, relation, weight) VALUES (?, ?, 'aligned_with', ?)",
                    (node_id, self._canonical_node_ids[entry.entry_id], min(1.0, 0.55 + 0.1 * len(overlap))),
                )
        if commit:
            self._connection.commit()

    def retrieve(self, query: str, user_id: str, max_hops: int = 2, max_nodes: int = 12, *, at: str | None = None, memory_scope: str = DEFAULT_SCOPE) -> list[GraphHit]:
        """Run bounded seed → expand → rerank retrieval."""
        memory_scope = validate_memory_scope(memory_scope)
        bounded_query_terms(query)
        result_limit(max_nodes)
        if type(max_hops) is not int or not 0 <= max_hops <= 2:
            raise ValueError("graph retrieval max_hops must be an integer from 0 through 2")
        query_terms = terms(query)
        if not query_terms:
            return []
        at = recall_time() if at is None else normalize_expiration(at)
        rows = self._connection.execute(
            "SELECT g.node_id, g.node_type, g.title, g.content, g.source_id, m.expires_at FROM graph_nodes g LEFT JOIN memories m ON g.node_id = 'memory:' || m.id WHERE (g.node_type = 'canonical' AND g.node_id LIKE ?) OR (g.node_type = 'memory' AND m.user_id = ? AND m.memory_scope = ?)",
            (self._canonical_prefix + '%', user_id, memory_scope),
        )
        active_canonical_ids = set(self._canonical_node_ids.values())
        nodes, budget = {}, ScanBudget()
        for row in rows:
            budget.include(row['title'], row['content'])
            if ((row['node_type'] == 'canonical' and row['node_id'] in active_canonical_ids)
                    or (row['node_type'] == 'memory' and eligible_for_recall(row['expires_at'], at))):
                nodes[row['node_id']] = row
        active: dict[str, tuple[float, int]] = {}
        for node_id, row in nodes.items():
            overlap = len(query_terms & terms(f"{row['title']} {row['content']}"))
            if overlap:
                active[node_id] = (min(1.0, 0.25 * overlap), 0)

        frontier = set(active)
        edge_rows = 0
        for depth in range(1, max_hops + 1):
            if not frontier:
                break
            next_scores: dict[str, float] = {}
            ordered = sorted(frontier)
            # At most 800 SQL parameters, including on older SQLite builds.
            for start in range(0, len(ordered), 400):
                chunk = ordered[start:start + 400]
                placeholders = ",".join("?" for _ in chunk)
                edges = self._connection.execute(
                    f"SELECT from_id, to_id, weight FROM graph_edges WHERE from_id IN ({placeholders}) OR to_id IN ({placeholders})",
                    tuple(chunk) + tuple(chunk),
                )
                for edge in edges:
                    edge_rows += 1
                    if edge_rows > retrieval_limits.MAX_EDGE_ROWS:
                        raise ValueError('retrieval edge row budget exceeded; no partial context returned')
                    for parent, neighbour in ((edge['from_id'], edge['to_id']), (edge['to_id'], edge['from_id'])):
                        if parent not in frontier or neighbour not in nodes or neighbour in active:
                            continue
                        weight = float(edge['weight'])
                        if not 0 <= weight <= 1:
                            raise ValueError('graph edge weight must be finite and between zero and one')
                        score = active[parent][0] * weight * 0.7
                        # The strongest same-depth path wins, independent of
                        # SQL insertion order or set/hash iteration order.
                        next_scores[neighbour] = max(next_scores.get(neighbour, 0.0), score)
            for node_id, score in next_scores.items():
                active[node_id] = (score, depth)
            frontier = set(next_scores)

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

    def remove_memories(self, memory_ids: list[int], *, commit: bool = True) -> None:
        for memory_id in memory_ids:
            node_id = f"memory:{memory_id}"
            self._connection.execute("DELETE FROM graph_edges WHERE from_id = ? OR to_id = ?", (node_id, node_id))
            self._connection.execute("DELETE FROM graph_nodes WHERE node_id = ? AND immutable = 0", (node_id,))
        if commit:
            self._connection.commit()

    def remove_legacy_orphans(self, user_id: str, *, commit: bool = True) -> int:
        """Remove old orphan nodes only when their exact legacy owner is known.

        Historical nodes used the generated title "Memory for <user_id>". Do
        not infer ownership from partial matches or remove a node linked to an
        active memory belonging to another user, even if its title is wrong.
        """
        rows = self._connection.execute(
            "SELECT g.node_id FROM graph_nodes g WHERE g.node_type = 'memory' "
            "AND g.immutable = 0 AND g.title = ? AND NOT EXISTS "
            "(SELECT 1 FROM memories m WHERE g.node_id = 'memory:' || m.id)",
            (f"Memory for {user_id}",),
        ).fetchall()
        for row in rows:
            node_id = row["node_id"]
            self._connection.execute("DELETE FROM graph_edges WHERE from_id = ? OR to_id = ?", (node_id, node_id))
            self._connection.execute("DELETE FROM graph_nodes WHERE node_id = ? AND immutable = 0", (node_id,))
        if commit:
            self._connection.commit()
        return len(rows)

    def close(self) -> None:
        if self._owns_connection:
            self._connection.close()
