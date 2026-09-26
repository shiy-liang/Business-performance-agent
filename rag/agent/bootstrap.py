"""Initialize and retain the process-wide Agent runtime."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from observability import logger
from rag.agent.graph import get_default_supervisor_graph
from rag.agent.specialists.graph import get_default_specialist_graph
from rag.agent.specialists.runtime import ensure_default_specialists_registered
from rag.agent.tools.registry import ToolRegistry, default_tool_registry


@dataclass(frozen=True, slots=True)
class AgentRuntime:
    """Process-wide graphs and registry reused by every request."""

    tool_registry: ToolRegistry
    supervisor_graph: Any
    finance_graph: Any
    operations_graph: Any


@lru_cache(maxsize=1)
def initialize_agent_runtime() -> AgentRuntime:
    """Build all default Agent graphs and model clients exactly once."""

    ensure_default_specialists_registered()
    finance_graph = get_default_specialist_graph("finance")
    operations_graph = get_default_specialist_graph("operations")
    supervisor_graph = get_default_supervisor_graph()
    runtime = AgentRuntime(
        tool_registry=default_tool_registry,
        supervisor_graph=supervisor_graph,
        finance_graph=finance_graph,
        operations_graph=operations_graph,
    )
    logger.info(
        "agent.runtime_initialized",
        component="agent",
        graph_count=3,
        tool_count=len(default_tool_registry.all_tool_names()),
    )
    return runtime


__all__ = ["AgentRuntime", "initialize_agent_runtime"]
