"""Process-local conversation sessions.

This module intentionally has no database, cache, file, or Agent dependencies.
All sessions disappear when the FastAPI process stops.
"""

from __future__ import annotations

import os
from threading import RLock
from typing import Literal, TypedDict
from uuid import uuid4


def _max_context_messages() -> int:
    raw_value = os.getenv("MAX_CONTEXT_MESSAGES", "20").strip()
    try:
        value = int(raw_value)
    except ValueError:
        return 20
    return value if value > 0 else 20


MAX_CONTEXT_MESSAGES = _max_context_messages()
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
        self._sessions: dict[str, list[ConversationMessage]] = {}
        self._lock = RLock()

    def create_session(self) -> str:
        session_id = str(uuid4())
        with self._lock:
            self._sessions[session_id] = []
        return session_id

    def session_exists(self, session_id: str) -> bool:
        with self._lock:
            return session_id in self._sessions

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
        with self._lock:
            history = self._sessions.get(session_id)
            if history is None:
                raise SessionNotFoundError(session_id)
            history.append({"role": role, "content": clean_content})

    def get_history(self, session_id: str) -> list[ConversationMessage]:
        """Return a copy so callers cannot mutate stored history directly."""

        with self._lock:
            history = self._sessions.get(session_id)
            if history is None:
                raise SessionNotFoundError(session_id)
            return [message.copy() for message in history]

    def get_context(
        self,
        session_id: str,
        max_messages: int = MAX_CONTEXT_MESSAGES,
    ) -> list[ConversationMessage]:
        if max_messages <= 0:
            raise ValueError("max_messages must be positive")
        return self.get_history(session_id)[-max_messages:]

    def delete_session(self, session_id: str) -> bool:
        with self._lock:
            return self._sessions.pop(session_id, None) is not None

    def clear_all(self) -> None:
        with self._lock:
            self._sessions.clear()


session_manager = SessionManager()
