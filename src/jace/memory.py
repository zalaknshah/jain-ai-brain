from __future__ import annotations

import sqlite3
from pathlib import Path

from .ethics import sanitise_memory
from .models import Memory, utc_now


class MemoryStore:
    """User-scoped continuous memory with an audit log and deletion support."""

    def __init__(self, db_path: str | Path = "data/jace.sqlite3") -> None:
        self.db_path = str(db_path)
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(self.db_path, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._connection.executescript(
            """
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS memories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL,
                source TEXT NOT NULL DEFAULT 'user'
            );
            CREATE INDEX IF NOT EXISTS memories_user_id ON memories(user_id);
            CREATE TABLE IF NOT EXISTS memory_audit (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                content TEXT,
                accepted INTEGER NOT NULL,
                reason TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            """
        )
        self._connection.commit()

    def add(self, user_id: str, content: str, source: str = "user") -> tuple[Memory | None, list[str]]:
        clean, notes = sanitise_memory(content)
        accepted = clean is not None
        reason = "; ".join(notes) if notes else "Memory accepted after alignment filter."
        now = utc_now()
        self._connection.execute(
            "INSERT INTO memory_audit(user_id, content, accepted, reason, created_at) VALUES (?, ?, ?, ?, ?)",
            (user_id, clean, int(accepted), reason, now),
        )
        if not accepted:
            self._connection.commit()
            return None, notes

        cursor = self._connection.execute(
            "INSERT INTO memories(user_id, content, created_at, source) VALUES (?, ?, ?, ?)",
            (user_id, clean, now, source),
        )
        self._connection.commit()
        return Memory(cursor.lastrowid, user_id, clean, now, source), notes

    def list(self, user_id: str, limit: int = 20) -> list[Memory]:
        rows = self._connection.execute(
            "SELECT id, user_id, content, created_at, source FROM memories WHERE user_id = ? ORDER BY id DESC LIMIT ?",
            (user_id, limit),
        ).fetchall()
        return [Memory(row["id"], row["user_id"], row["content"], row["created_at"], row["source"]) for row in rows]

    def search(self, user_id: str, query: str, limit: int = 5) -> list[Memory]:
        terms = [term for term in query.lower().split() if len(term) > 2]
        memories = self.list(user_id, 100)
        if not terms:
            return memories[:limit]
        ranked = sorted(memories, key=lambda item: sum(term in item.content.lower() for term in terms), reverse=True)
        return [memory for memory in ranked if any(term in memory.content.lower() for term in terms)][:limit]

    def delete_user(self, user_id: str) -> int:
        cursor = self._connection.execute("DELETE FROM memories WHERE user_id = ?", (user_id,))
        self._connection.commit()
        return cursor.rowcount

    def close(self) -> None:
        self._connection.close()
