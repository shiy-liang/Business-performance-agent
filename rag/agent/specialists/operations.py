"""Operations specialist entry point."""

from __future__ import annotations

from langchain_core.runnables import RunnableConfig

from rag.agent.specialists.runtime import run_specialist_agent


async def run_operations_agent(
    task: str,
    config: RunnableConfig | None = None,
) -> dict[str, object]:
    """Answer an operations task using Operations-authorized SQL tools."""

    return await run_specialist_agent("operations", task, config=config)


__all__ = ["run_operations_agent"]
