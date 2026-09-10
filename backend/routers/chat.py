"""Placeholder endpoint for the future pgvector-backed business assistant."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field


router = APIRouter(prefix="/api", tags=["assistant"])


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=500)


@router.post("/chat")
def chat(request: ChatRequest) -> dict[str, str]:
    """Keep the UI contract stable while the retrieval pipeline is being built."""

    return {
        "status": "placeholder",
        "answer": (
            "这个问题已经收到。Dashboard 数据接口可以正常使用；"
            "等 pgvector 中的评价和工单向量生成后，这里会返回带数据依据的分析。"
        ),
    }
