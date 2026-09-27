"""PostgreSQL-backed conversation sessions."""

from __future__ import annotations

from threading import RLock
from typing import Literal, TypedDict
from uuid import uuid4


from backend.database import connect
from config.settings import load_application_settings


MAX_CONTEXT_MESSAGES = load_application_settings().conversation.max_context_messages
MessageRole = Literal["user", "assistant"]


class ConversationMessage(TypedDict):
    """One user-visible message retained in a chat session."""

    role: MessageRole
    content: str


class SessionNotFoundError(KeyError):
    """Raised when a caller references a missing or expired session."""


class SessionManager:
    """Manage isolated conversation histories in process memory."""

    def __init__(self) -> None:
        self._lock = RLock()

    def create_session(self) -> str:
        session_id = str(uuid4())
        with connect() as connection, connection.transaction(), connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO chat_sessions (session_id) VALUES (%s)",
                (session_id,),
            )
        return session_id

    def session_exists(self, session_id: str) -> bool:
        with connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT 1 FROM chat_sessions WHERE session_id = %s",
                (session_id,),
            )
            return cursor.fetchone() is not None

    def add_message(
        self,
        session_id: str,
        role: MessageRole,
        content: str,
    ) -> None:
        if role not in {"user", "assistant"}:
            raise ValueError("role must be 'user' or 'assistant'")
        clean_content = content.strip()
        if not clean_content:
            raise ValueError("message content must not be empty")
        with connect() as connection, connection.transaction(), connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO chat_messages (session_id, role, content)
                SELECT %s, %s, %s
                WHERE EXISTS (SELECT 1 FROM chat_sessions WHERE session_id = %s)
                """,
                (session_id, role, clean_content, session_id),
            )
            if cursor.rowcount == 0:
                raise SessionNotFoundError(session_id)
            cursor.execute(
                """
                UPDATE chat_sessions
                SET updated_at = NOW(), message_count = message_count + 1,
                    last_message_preview = LEFT(%s, 160)
                WHERE session_id = %s
                """,
                (clean_content, session_id),
            )

    def get_history(self, session_id: str) -> list[ConversationMessage]:
        """Return a copy so callers cannot mutate stored history directly."""

        with connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT role, content FROM chat_messages WHERE session_id = %s "
                "ORDER BY created_at, message_id",
                (session_id,),
            )
            rows = cursor.fetchall()
            if not rows and not self.session_exists(session_id):
                raise SessionNotFoundError(session_id)
            return [{"role": row[0], "content": row[1]} for row in rows]

    def get_session(self, session_id: str) -> dict[str, object]:
        with connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """SELECT session_id, title, summary, created_at, updated_at,
                          message_count, last_message_preview
                   FROM chat_sessions WHERE session_id = %s""",
                (session_id,),
            )
            row = cursor.fetchone()
        if row is None:
            raise SessionNotFoundError(session_id)
        return dict(zip(
            ("session_id", "title", "summary", "created_at", "updated_at",
             "message_count", "last_message_preview"), row
        ))

    def list_sessions(self) -> list[dict[str, object]]:
        with connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """SELECT session_id, title, summary, created_at, updated_at,
                          message_count, last_message_preview
                   FROM chat_sessions ORDER BY updated_at DESC"""
            )
            columns = ("session_id", "title", "summary", "created_at", "updated_at",
                       "message_count", "last_message_preview")
            return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def update_title(self, session_id: str, title: str) -> None:
        with connect() as connection, connection.transaction(), connection.cursor() as cursor:
            cursor.execute(
                "UPDATE chat_sessions SET title = %s, updated_at = NOW() WHERE session_id = %s",
                (title.strip()[:80] or "New Chat", session_id),
            )

    def get_context(
        self,
        session_id: str,
        max_messages: int = MAX_CONTEXT_MESSAGES,
    ) -> list[ConversationMessage]:
        if max_messages <= 0:
            raise ValueError("max_messages must be positive")
        return self.get_history(session_id)[-max_messages:]

    def delete_session(self, session_id: str) -> bool:
        with connect() as connection, connection.transaction(), connection.cursor() as cursor:
            cursor.execute("DELETE FROM chat_sessions WHERE session_id = %s", (session_id,))
            return cursor.rowcount > 0

    def clear_all(self) -> None:
        with connect() as connection, connection.transaction(), connection.cursor() as cursor:
            cursor.execute("DELETE FROM chat_sessions")


session_manager = SessionManager()
