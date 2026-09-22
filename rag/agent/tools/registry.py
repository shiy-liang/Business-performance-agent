"""Central tool registry enforcing per-agent capability boundaries."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from langchain_core.tools import BaseTool

from rag.agent.state import AgentName
from rag.agent.tools.common.knowledge import search_knowledge
from rag.agent.tools.finance import (
    execute_finance_sql,
    resolve_finance_entity,
    search_finance_schema,
)
from rag.agent.tools.operations import (
    execute_operations_sql,
    resolve_operations_entity,
    search_customer_reviews,
    search_operations_schema,
)
from rag.agent.tools.supervisor.delegation import (
    delegate_finance,
    delegate_operations,
)


@dataclass(frozen=True, slots=True)
class ToolRegistration:
    tool: BaseTool
    allowed_agents: frozenset[AgentName]


class ToolRegistry:
    """Register tools once and expose only the whitelist for each agent."""

    def __init__(self, registrations: Iterable[ToolRegistration] = ()) -> None:
        self._registrations: dict[str, ToolRegistration] = {}
        for registration in registrations:
            self.register(registration.tool, registration.allowed_agents)

    def register(
        self,
        tool: BaseTool,
        allowed_agents: Iterable[AgentName],
    ) -> None:
        if tool.name in self._registrations:
            raise ValueError(f"Tool already registered: {tool.name}")
        agents = frozenset(allowed_agents)
        if not agents:
            raise ValueError(f"Tool must have at least one allowed agent: {tool.name}")
        self._registrations[tool.name] = ToolRegistration(tool, agents)

    def tools_for(self, agent: AgentName) -> list[BaseTool]:
        return [
            registration.tool
            for registration in self._registrations.values()
            if agent in registration.allowed_agents
        ]

    def tool_names_for(self, agent: AgentName) -> list[str]:
        return [tool.name for tool in self.tools_for(agent)]

    def describe_for(self, agent: AgentName) -> str:
        return "\n".join(
            f"- `{tool.name}`: {tool.description}"
            for tool in self.tools_for(agent)
        )

    def all_tool_names(self) -> list[str]:
        """Return every registered tool name for public lifecycle filtering."""

        return list(self._registrations)


default_tool_registry = ToolRegistry(
    (
        ToolRegistration(search_knowledge, frozenset({"supervisor"})),
        ToolRegistration(delegate_finance, frozenset({"supervisor"})),
        ToolRegistration(delegate_operations, frozenset({"supervisor"})),
        ToolRegistration(search_finance_schema, frozenset({"finance"})),
        ToolRegistration(resolve_finance_entity, frozenset({"finance"})),
        ToolRegistration(execute_finance_sql, frozenset({"finance"})),
        ToolRegistration(search_operations_schema, frozenset({"operations"})),
        ToolRegistration(resolve_operations_entity, frozenset({"operations"})),
        ToolRegistration(execute_operations_sql, frozenset({"operations"})),
        ToolRegistration(search_customer_reviews, frozenset({"operations"})),
    )
)


__all__ = ["ToolRegistration", "ToolRegistry", "default_tool_registry"]
