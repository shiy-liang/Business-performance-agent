"""Finance specialist entry point."""

from __future__ import annotations

from langchain_core.runnables import RunnableConfig

from rag.agent.specialists.runtime import run_specialist_agent


async def run_finance_agent(
    task: str,
    config: RunnableConfig | None = None,
) -> dict[str, object]:
    """Answer a finance task using Finance-authorized SQL tools."""

    return await run_specialist_agent("finance", task, config=config)


__all__ = ["run_finance_agent"]
