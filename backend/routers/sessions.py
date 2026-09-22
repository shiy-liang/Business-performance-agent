"""HTTP lifecycle endpoints for process-local chat sessions."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Response, status

from rag.history_management import session_manager


router = APIRouter(prefix="/api/sessions", tags=["assistant"])


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_session() -> dict[str, str]:
    return {"session_id": session_manager.create_session()}


@router.delete("/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_session(session_id: str) -> Response:
    if not session_manager.delete_session(session_id):
        raise HTTPException(status_code=404, detail="Session not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
