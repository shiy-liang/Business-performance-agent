"""HTTP lifecycle endpoints for process-local chat sessions."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Response, status

from rag.history_management import session_manager


router = APIRouter(prefix="/api/sessions", tags=["assistant"])

def _serialize_session(session: dict[str, object]) -> dict[str, object]:
    return {**session, "session_id": str(session["session_id"]),
            "created_at": session["created_at"].isoformat(),
            "updated_at": session["updated_at"].isoformat()}


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_session() -> dict[str, str]:
    return {"session_id": session_manager.create_session()}

@router.get("")
async def list_sessions() -> list[dict[str, object]]:
    return [
        _serialize_session(item)
        for item in session_manager.list_sessions()
        if int(item.get("message_count") or 0) >= 2
    ]

@router.get("/{session_id}")
async def get_session(session_id: str) -> dict[str, object]:
    try:
        session = session_manager.get_session(session_id)
        session["messages"] = session_manager.get_history(session_id)
        return _serialize_session(session)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Session not found") from exc


@router.delete("/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_session(session_id: str) -> Response:
    if not session_manager.delete_session(session_id):
        raise HTTPException(status_code=404, detail="Session not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
