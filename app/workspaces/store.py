from __future__ import annotations

import json
import shutil
import re
import sqlite3
from contextlib import contextmanager
from collections.abc import Iterator
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

from app.core.exceptions import IngestionError, RAGApplicationError


_SAFE_NAME = re.compile(r"[^A-Za-z0-9._ -]+")


class WorkspaceNotFoundError(RAGApplicationError):
    """Raised when a requested workspace does not exist."""


class ConversationNotFoundError(RAGApplicationError):
    """Raised when a requested conversation does not exist."""


class WorkspaceStore:
    """Persist workspaces, conversations, messages, and document metadata in SQLite."""

    def __init__(self, db_path: Path, workspace_root: Path) -> None:
        self.db_path = db_path
        self.workspace_root = workspace_root
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.workspace_root.mkdir(parents=True, exist_ok=True)
        self._initialize()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        """Yield a configured SQLite connection and always close it after use."""
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            yield connection
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._connect() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS workspaces (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS conversations (
                    id TEXT PRIMARY KEY,
                    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
                    title TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS messages (
                    id TEXT PRIMARY KEY,
                    conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
                    role TEXT NOT NULL CHECK(role IN ('user', 'assistant')),
                    content TEXT NOT NULL,
                    response_json TEXT,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS documents (
                    id TEXT PRIMARY KEY,
                    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
                    file_name TEXT NOT NULL,
                    size_bytes INTEGER NOT NULL,
                    chunk_count INTEGER NOT NULL,
                    indexed_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_conversations_workspace
                    ON conversations(workspace_id, updated_at DESC);
                CREATE INDEX IF NOT EXISTS idx_messages_conversation
                    ON messages(conversation_id, created_at ASC);
                CREATE INDEX IF NOT EXISTS idx_documents_workspace
                    ON documents(workspace_id, indexed_at DESC);
                """
            )

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def create_workspace(self, name: str) -> dict[str, str]:
        clean_name = name.strip()[:80]
        if not clean_name:
            raise RAGApplicationError("workspace name cannot be empty")
        workspace_id = str(uuid4())
        now = self._now()
        with self._connect() as db:
            db.execute(
                "INSERT INTO workspaces(id, name, created_at, updated_at) VALUES (?, ?, ?, ?)",
                (workspace_id, clean_name, now, now),
            )
            db.execute(
                "INSERT INTO conversations(id, workspace_id, title, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                (str(uuid4()), workspace_id, "New conversation", now, now),
            )
        self._workspace_dir(workspace_id)
        return {"id": workspace_id, "name": clean_name}

    def list_workspaces(self) -> list[dict]:
        with self._connect() as db:
            rows = db.execute(
                """
                SELECT w.id, w.name, w.created_at, w.updated_at,
                       COUNT(DISTINCT d.id) AS document_count,
                       (SELECT COUNT(*) FROM conversations c WHERE c.workspace_id = w.id) AS conversation_count
                FROM workspaces w
                LEFT JOIN documents d ON d.workspace_id = w.id
                GROUP BY w.id
                ORDER BY w.updated_at DESC
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def rename_workspace(self, workspace_id: str, name: str) -> dict[str, str]:
        self.require_workspace(workspace_id)
        clean_name = name.strip()[:80]
        if not clean_name:
            raise RAGApplicationError("workspace name cannot be empty")
        now = self._now()
        with self._connect() as db:
            db.execute("UPDATE workspaces SET name = ?, updated_at = ? WHERE id = ?", (clean_name, now, workspace_id))
        return {"id": workspace_id, "name": clean_name}

    def delete_workspace(self, workspace_id: str) -> None:
        self.require_workspace(workspace_id)
        with self._connect() as db:
            db.execute("DELETE FROM workspaces WHERE id = ?", (workspace_id,))
        directory = self._workspace_dir(workspace_id)
        if directory.exists():
            import shutil
            shutil.rmtree(directory)

    def require_workspace(self, workspace_id: str) -> sqlite3.Row:
        try:
            UUID(workspace_id)
        except ValueError as exc:
            raise WorkspaceNotFoundError("invalid workspace id") from exc
        with self._connect() as db:
            row = db.execute("SELECT * FROM workspaces WHERE id = ?", (workspace_id,)).fetchone()
        if row is None:
            raise WorkspaceNotFoundError("workspace not found")
        self._workspace_dir(workspace_id)
        return row

    def _workspace_dir(self, workspace_id: str) -> Path:
        return self.workspace_root / workspace_id

    def raw_dir(self, workspace_id: str) -> Path:
        self.require_workspace(workspace_id)
        path = self._workspace_dir(workspace_id) / "raw"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def processed_dir(self, workspace_id: str) -> Path:
        self.require_workspace(workspace_id)
        path = self._workspace_dir(workspace_id) / "processed"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def vector_dir(self, workspace_id: str) -> Path:
        self.require_workspace(workspace_id)
        path = self._workspace_dir(workspace_id) / "vector"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def conversation_dir(self, workspace_id: str) -> Path:
        path = self._workspace_dir(workspace_id) / "conversation"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def create_conversation(self, workspace_id: str, title: str = "New conversation") -> dict:
        self.require_workspace(workspace_id)
        conversation_id = str(uuid4())
        clean_title = (title.strip() or "New conversation")[:120]
        now = self._now()
        with self._connect() as db:
            db.execute(
                "INSERT INTO conversations(id, workspace_id, title, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                (conversation_id, workspace_id, clean_title, now, now),
            )
            db.execute("UPDATE workspaces SET updated_at = ? WHERE id = ?", (now, workspace_id))
        return {"id": conversation_id, "workspace_id": workspace_id, "title": clean_title, "created_at": now, "updated_at": now}

    def delete_conversation(self, workspace_id: str, conversation_id: str) -> None:
        """Delete one conversation and its cascaded chat messages."""
        self.require_conversation(workspace_id, conversation_id)
        with self._connect() as db:
            db.execute(
                "DELETE FROM conversations WHERE id = ? AND workspace_id = ?",
                (conversation_id, workspace_id),
            )
            db.execute(
                "UPDATE workspaces SET updated_at = ? WHERE id = ?",
                (self._now(), workspace_id),
            )

    def reset_conversation(self, workspace_id: str, conversation_id: str) -> None:
        """Clear a conversation's messages while preserving the conversation record."""
        self.require_conversation(workspace_id, conversation_id)
        with self._connect() as db:
            db.execute(
                "DELETE FROM messages WHERE conversation_id = ?",
                (conversation_id,),
            )
            db.execute(
                "UPDATE conversations SET updated_at = ? WHERE id = ? AND workspace_id = ?",
                (self._now(), conversation_id, workspace_id),
            )
            db.execute(
                "UPDATE workspaces SET updated_at = ? WHERE id = ?",
                (self._now(), workspace_id),
            )

    def list_conversations(self, workspace_id: str) -> list[dict]:
        self.require_workspace(workspace_id)
        with self._connect() as db:
            rows = db.execute(
                "SELECT id, workspace_id, title, created_at, updated_at FROM conversations WHERE workspace_id = ? ORDER BY updated_at DESC",
                (workspace_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def require_conversation(self, workspace_id: str, conversation_id: str) -> sqlite3.Row:
        self.require_workspace(workspace_id)
        with self._connect() as db:
            row = db.execute(
                "SELECT * FROM conversations WHERE id = ? AND workspace_id = ?",
                (conversation_id, workspace_id),
            ).fetchone()
        if row is None:
            raise ConversationNotFoundError("conversation not found")
        return row

    def list_messages(self, workspace_id: str, conversation_id: str, limit: int = 20) -> list[dict]:
        self.require_conversation(workspace_id, conversation_id)
        with self._connect() as db:
            rows = db.execute(
                "SELECT id, role, content, response_json, created_at FROM messages WHERE conversation_id = ? ORDER BY created_at DESC LIMIT ?",
                (conversation_id, max(1, min(limit, 100))),
            ).fetchall()
        rows = list(reversed(rows))
        messages = []
        for row in rows:
            payload = dict(row)
            payload["response"] = json.loads(payload.pop("response_json")) if payload.get("response_json") else None
            messages.append(payload)
        return messages

    def add_turn(self, workspace_id: str, conversation_id: str, user_content: str, response: dict) -> None:
        self.require_conversation(workspace_id, conversation_id)
        now = self._now()
        with self._connect() as db:
            db.execute(
                "INSERT INTO messages(id, conversation_id, role, content, response_json, created_at) VALUES (?, ?, 'user', ?, NULL, ?)",
                (str(uuid4()), conversation_id, user_content, now),
            )
            db.execute(
                "INSERT INTO messages(id, conversation_id, role, content, response_json, created_at) VALUES (?, ?, 'assistant', ?, ?, ?)",
                (str(uuid4()), conversation_id, response["answer"], json.dumps(response), now),
            )
            title = user_content.strip().replace("\n", " ")[:60] or "New conversation"
            db.execute("UPDATE conversations SET title = ?, updated_at = ? WHERE id = ?", (title, now, conversation_id))
            db.execute("UPDATE workspaces SET updated_at = ? WHERE id = ?", (now, workspace_id))

    def document_count(self, workspace_id: str) -> int:
        self.require_workspace(workspace_id)
        with self._connect() as db:
            return int(db.execute("SELECT COUNT(*) FROM documents WHERE workspace_id = ?", (workspace_id,)).fetchone()[0])

    def list_documents(self, workspace_id: str) -> list[dict]:
        self.require_workspace(workspace_id)
        with self._connect() as db:
            rows = db.execute(
                "SELECT id, file_name, size_bytes, chunk_count, indexed_at FROM documents WHERE workspace_id = ? ORDER BY indexed_at DESC",
                (workspace_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def get_documents_by_ids(self, workspace_id: str, document_ids: list[str]) -> list[dict]:
        """Return selected document metadata while enforcing workspace ownership."""
        self.require_workspace(workspace_id)
        clean_ids = [item.strip() for item in document_ids if item and item.strip()]
        if not clean_ids:
            raise RAGApplicationError("at least one document id is required")

        placeholders = ",".join("?" for _ in clean_ids)
        with self._connect() as db:
            rows = db.execute(
                f"SELECT id, file_name, size_bytes, chunk_count, indexed_at FROM documents "
                f"WHERE workspace_id = ? AND id IN ({placeholders})",
                [workspace_id, *clean_ids],
            ).fetchall()

        documents = [dict(row) for row in rows]
        found_ids = {item["id"] for item in documents}
        missing = [item for item in clean_ids if item not in found_ids]
        if missing:
            raise RAGApplicationError("one or more selected documents no longer exist")
        return documents

    def clear_documents(self, workspace_id: str) -> None:
        """Remove all persisted document metadata for a workspace."""
        self.require_workspace(workspace_id)
        now = self._now()
        with self._connect() as db:
            db.execute("DELETE FROM documents WHERE workspace_id = ?", (workspace_id,))
            db.execute("UPDATE workspaces SET updated_at = ? WHERE id = ?", (now, workspace_id))

    def replace_documents(self, workspace_id: str, documents: list[dict]) -> None:
        """Replace a workspace's document metadata while preserving IDs by filename."""
        self.require_workspace(workspace_id)
        now = self._now()
        with self._connect() as db:
            existing_rows = db.execute(
                "SELECT file_name, id FROM documents WHERE workspace_id = ?",
                (workspace_id,),
            ).fetchall()
            existing_ids = {row["file_name"]: row["id"] for row in existing_rows}
            db.execute("DELETE FROM documents WHERE workspace_id = ?", (workspace_id,))
            for document in documents:
                file_name = document["file_name"]
                document_id = existing_ids.get(file_name, str(uuid4()))
                db.execute(
                    "INSERT INTO documents(id, workspace_id, file_name, size_bytes, chunk_count, indexed_at) VALUES (?, ?, ?, ?, ?, ?)",
                    (document_id, workspace_id, file_name, document["size_bytes"], document["chunk_count"], now),
                )
            db.execute("UPDATE workspaces SET updated_at = ? WHERE id = ?", (now, workspace_id))

    def sanitize_filename(self, filename: str) -> str:
        name = Path(filename or "document").name
        name = _SAFE_NAME.sub("_", name).strip(" .")
        if not name:
            raise IngestionError("invalid filename")
        return name[:180]
