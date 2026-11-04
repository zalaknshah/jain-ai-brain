from __future__ import annotations

import sqlite3
import heapq
from pathlib import Path

from .ethics import sanitise_memory
from .models import Memory, utc_now
from .text import lexical_terms
from .retrieval_limits import ScanBudget, query_terms, result_limit
from .memory_scope import DEFAULT_SCOPE, validate_memory_scope
from .temporal import eligible_for_recall, normalize_expiration, recall_time


class MemoryDeletionConsentRequired(ValueError):
    def __init__(self, count: int) -> None:
        self.unattributed_audit_entries = count
        super().__init__(f'Deletion also removes all {count} unattributed audit entries for this owner across all memory scopes, including legacy entries. Explicit cleanup confirmation is required; other active memories and attributable audits are preserved.')


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
                source TEXT NOT NULL DEFAULT 'user',
                updated_at TEXT,
                expires_at TEXT,
                memory_scope TEXT NOT NULL DEFAULT 'default'
            );
            CREATE INDEX IF NOT EXISTS memories_user_id ON memories(user_id);
            CREATE TABLE IF NOT EXISTS memory_audit (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                content TEXT,
                accepted INTEGER NOT NULL,
                reason TEXT NOT NULL,
                created_at TEXT NOT NULL,
                memory_id INTEGER
            );
            """
        )
        with self._connection:
            self._connection.execute("BEGIN IMMEDIATE")
            columns = {row["name"] for row in self._connection.execute("PRAGMA table_info(memories)")}
            if "updated_at" not in columns:
                self._connection.execute("ALTER TABLE memories ADD COLUMN updated_at TEXT")
            if "expires_at" not in columns:
                self._connection.execute("ALTER TABLE memories ADD COLUMN expires_at TEXT")
            if "memory_scope" not in columns:
                self._connection.execute("ALTER TABLE memories ADD COLUMN memory_scope TEXT NOT NULL DEFAULT 'default'")
            self._connection.execute("CREATE INDEX IF NOT EXISTS memories_owner_scope_id ON memories(user_id, memory_scope, id)")
            audit_columns = {row["name"] for row in self._connection.execute("PRAGMA table_info(memory_audit)")}
            if "memory_id" not in audit_columns:
                self._connection.execute("ALTER TABLE memory_audit ADD COLUMN memory_id INTEGER")
            self._connection.execute("CREATE INDEX IF NOT EXISTS memory_audit_owner_item ON memory_audit(user_id, memory_id)")

    def add(self, user_id: str, content: str, source: str = "user", *, expires_at: str | None = None, memory_scope: str = DEFAULT_SCOPE, commit: bool = True) -> tuple[Memory | None, list[str]]:
        if not isinstance(content, str) or len(content) > 10_000:
            raise ValueError("memory content must be text of at most 10,000 characters")
        memory_scope = validate_memory_scope(memory_scope)
        expires_at = normalize_expiration(expires_at)
        clean, notes = sanitise_memory(content)
        accepted = clean is not None
        reason = "; ".join(notes) if notes else "Memory accepted after alignment filter."
        now = utc_now()
        audit = self._connection.execute(
            "INSERT INTO memory_audit(user_id, content, accepted, reason, created_at) VALUES (?, ?, ?, ?, ?)",
            (user_id, None, int(accepted), reason, now),
        )
        if not accepted:
            if commit:
                self._connection.commit()
            return None, notes

        cursor = self._connection.execute(
            "INSERT INTO memories(user_id, content, created_at, source, updated_at, expires_at, memory_scope) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (user_id, clean, now, source, now, expires_at, memory_scope),
        )
        self._connection.execute("UPDATE memory_audit SET memory_id = ? WHERE id = ?", (cursor.lastrowid, audit.lastrowid))
        if commit:
            self._connection.commit()
        return Memory(cursor.lastrowid, user_id, clean, now, source, now, expires_at, memory_scope), notes

    def list(self, user_id: str, limit: int | None = 20, *, memory_scope: str | None = None) -> list[Memory]:
        # None is an explicit internal owner-wide review/deletion operation.
        if memory_scope is not None:
            validate_memory_scope(memory_scope)
        rows = self._connection.execute(
            "SELECT id, user_id, content, created_at, source, updated_at, expires_at, memory_scope FROM memories WHERE user_id = ?"
            + (" AND memory_scope = ?" if memory_scope is not None else "") + " ORDER BY id DESC LIMIT ?",
            (user_id, memory_scope, -1 if limit is None else limit) if memory_scope is not None else (user_id, -1 if limit is None else limit),
        ).fetchall()
        return [Memory(row["id"], row["user_id"], row["content"], row["created_at"], row["source"], row["updated_at"], row["expires_at"], row["memory_scope"]) for row in rows]

    def scopes(self, user_id: str) -> list[str]:
        rows = self._connection.execute("SELECT DISTINCT memory_scope FROM memories WHERE user_id = ? ORDER BY memory_scope", (user_id,))
        scopes = {DEFAULT_SCOPE}
        for row in rows:
            try:
                scopes.add(validate_memory_scope(row['memory_scope']))
            except ValueError:
                continue  # Malformed stored namespaces never become valid recall selectors.
        return sorted(scopes)

    def replace(self, user_id: str, memory_id: int, content: str, *, commit: bool = True) -> tuple[Memory | None, list[str]]:
        if not isinstance(content, str) or len(content) > 10_000:
            raise ValueError("memory content must be text of at most 10,000 characters")
        row = self._connection.execute(
            "SELECT id, user_id, content, created_at, source, updated_at, expires_at, memory_scope FROM memories WHERE user_id = ? AND id = ?",
            (user_id, memory_id),
        ).fetchone()
        if row is None:
            raise LookupError("memory not found")
        clean, notes = sanitise_memory(content)
        now = utc_now()
        self._connection.execute(
            "INSERT INTO memory_audit(user_id, content, accepted, reason, created_at, memory_id) VALUES (?, NULL, ?, ?, ?, ?)",
            (user_id, int(clean is not None), "; ".join(notes) or "Memory corrected after alignment filter.", now, memory_id),
        )
        if clean is None:
            if commit:
                self._connection.commit()
            return None, notes
        self._connection.execute("UPDATE memories SET content = ?, updated_at = ? WHERE user_id = ? AND id = ?",
                                 (clean, now, user_id, memory_id))
        if commit:
            self._connection.commit()
        return Memory(memory_id, user_id, clean, row["created_at"], row["source"], now, row["expires_at"], row["memory_scope"]), notes

    def active(self, user_id: str, limit: int = 100, *, at: str | None = None, memory_scope: str = DEFAULT_SCOPE) -> list[Memory]:
        memory_scope = validate_memory_scope(memory_scope)
        if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
            raise ValueError('active memory limit must be a positive integer')
        at = recall_time() if at is None else normalize_expiration(at)
        result = []
        rows = self._connection.execute(
            "SELECT id, user_id, content, created_at, source, updated_at, expires_at, memory_scope FROM memories WHERE user_id = ? AND memory_scope = ? ORDER BY id DESC",
            (user_id, memory_scope),
        )
        for row in rows:
            if eligible_for_recall(row["expires_at"], at):
                result.append(Memory(row["id"], row["user_id"], row["content"], row["created_at"], row["source"], row["updated_at"], row["expires_at"], row["memory_scope"]))
                if len(result) >= limit:
                    break
        return result

    def set_expiration(self, user_id: str, memory_id: int, expires_at: str | None, *, commit: bool = True) -> Memory:
        expires_at = normalize_expiration(expires_at)
        row = self._connection.execute(
            "SELECT id, user_id, content, created_at, source, memory_scope FROM memories WHERE user_id = ? AND id = ?",
            (user_id, memory_id),
        ).fetchone()
        if row is None:
            raise LookupError('memory not found')
        now = utc_now()
        self._connection.execute("UPDATE memories SET expires_at = ?, updated_at = ? WHERE user_id = ? AND id = ?",
                                 (expires_at, now, user_id, memory_id))
        self._connection.execute(
            "INSERT INTO memory_audit(user_id, content, accepted, reason, created_at, memory_id) VALUES (?, NULL, 1, ?, ?, ?)",
            (user_id, "Owner explicitly changed memory expiration.", now, memory_id),
        )
        if commit:
            self._connection.commit()
        return Memory(memory_id, user_id, row['content'], row['created_at'], row['source'], now, expires_at, row['memory_scope'])

    def search(self, user_id: str, query: str, limit: int = 5, *, at: str | None = None, memory_scope: str = DEFAULT_SCOPE) -> list[Memory]:
        terms = query_terms(query)
        limit = result_limit(limit)
        memory_scope = validate_memory_scope(memory_scope)
        at = recall_time() if at is None else normalize_expiration(at)
        budget, ranked = ScanBudget(), []
        rows = self._connection.execute(
            "SELECT id, user_id, content, created_at, source, updated_at, expires_at, memory_scope FROM memories WHERE user_id = ? AND memory_scope = ? ORDER BY id DESC",
            (user_id, memory_scope),
        )
        # Stream candidates, keeping only k ranked objects, instead of silently
        # discarding every eligible memory older than the latest 100 records.
        for row in rows:
            budget.include(row['content'])
            if not eligible_for_recall(row['expires_at'], at):
                continue
            score = len(terms & lexical_terms(row['content'])) if terms else 1
            if not score:
                continue
            memory = Memory(row['id'], row['user_id'], row['content'], row['created_at'], row['source'],
                            row['updated_at'], row['expires_at'], row['memory_scope'])
            item = (score, memory.memory_id, memory)
            if len(ranked) < limit:
                heapq.heappush(ranked, item)
            elif item[:2] > ranked[0][:2]:
                heapq.heapreplace(ranked, item)
            if not terms and len(ranked) >= limit:
                break  # Explicit no-term recent-memory behavior is unchanged.
        return [item[2] for item in sorted(ranked, reverse=True)]

    def selected(self, user_id: str, memory_ids: list[int], *, at: str | None = None,
                 memory_scope: str = DEFAULT_SCOPE) -> list[Memory]:
        """Rehydrate ranked graph IDs against authoritative owner/scope/expiry."""
        memory_scope = validate_memory_scope(memory_scope)
        if not isinstance(memory_ids, list) or len(memory_ids) > 100 or any(
                type(item) is not int or not 1 <= item <= 2**63 - 1 for item in memory_ids):
            raise ValueError('selected memory IDs must be at most 100 positive 64-bit integers')
        at = recall_time() if at is None else normalize_expiration(at)
        ids = list(dict.fromkeys(memory_ids))
        if not ids:
            return []
        placeholders = ','.join('?' for _ in ids)
        rows = self._connection.execute(
            'SELECT id, user_id, content, created_at, source, updated_at, expires_at, memory_scope FROM memories '
            f'WHERE user_id = ? AND memory_scope = ? AND id IN ({placeholders})',
            (user_id, memory_scope, *ids))
        found, budget = {}, ScanBudget()
        for row in rows:
            budget.include(row['content'])
            if eligible_for_recall(row['expires_at'], at):
                found[row['id']] = Memory(row['id'], row['user_id'], row['content'], row['created_at'], row['source'],
                    row['updated_at'], row['expires_at'], row['memory_scope'])
        return [found[item] for item in ids if item in found]

    def delete_user(self, user_id: str, *, commit: bool = True) -> int:
        # Include historical audit rows, which older versions stored with text.
        # New audit events deliberately omit content entirely.
        cursor = self._connection.execute("DELETE FROM memories WHERE user_id = ?", (user_id,))
        self._connection.execute("DELETE FROM memory_audit WHERE user_id = ?", (user_id,))
        if commit:
            self._connection.commit()
        return cursor.rowcount

    def deletion_preview(self, user_id: str, memory_id: int) -> dict:
        row = self._connection.execute(
            "SELECT id, user_id, content, created_at, source, updated_at, expires_at, memory_scope FROM memories WHERE user_id = ? AND id = ?",
            (user_id, memory_id),
        ).fetchone()
        if row is None:
            raise LookupError('memory not found')
        count = self._connection.execute(
            "SELECT COUNT(*) FROM memory_audit WHERE user_id = ? AND memory_id IS NULL", (user_id,),
        ).fetchone()[0]
        memory = Memory(row['id'], row['user_id'], row['content'], row['created_at'], row['source'], row['updated_at'], row['expires_at'], row['memory_scope'])
        return {'memory': memory.to_dict(), 'unattributed_audit_entries': count,
                'requires_delete_confirmation': True,
                'requires_unattributed_audit_cleanup_confirmation': count > 0,
                'warning': str(MemoryDeletionConsentRequired(count)) if count else
                    'Deletes this active memory, its associated graph node/edges and attributable audit entries. Other active memories are preserved.'}

    def delete_one(self, user_id: str, memory_id: int, *, confirm_unattributed_audit_cleanup: bool = False,
                   commit: bool = True) -> int:
        preview = self.deletion_preview(user_id, memory_id)
        count = preview['unattributed_audit_entries']
        if count and confirm_unattributed_audit_cleanup is not True:
            raise MemoryDeletionConsentRequired(count)
        cursor = self._connection.execute("DELETE FROM memories WHERE user_id = ? AND id = ?", (user_id, memory_id))
        self._connection.execute("DELETE FROM memory_audit WHERE user_id = ? AND (memory_id = ? OR memory_id IS NULL)",
                                 (user_id, memory_id))
        if commit:
            self._connection.commit()
        return cursor.rowcount

    @property
    def connection(self) -> sqlite3.Connection:
        """Connection shared by the engine's atomic memory/graph operations."""
        return self._connection

    def close(self) -> None:
        self._connection.close()
