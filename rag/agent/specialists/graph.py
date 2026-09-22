"""Reusable LangGraph tool loop for structured-data specialists."""

from __future__ import annotations

from typing import Any, Literal

from langchain_core.messages import SystemMessage
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition

from rag.agent.model import create_specialist_model
from rag.agent.prompts import build_specialist_prompt
from rag.agent.state import SpecialistState
from rag.agent.tools.registry import ToolRegistry, default_tool_registry


SpecialistName = Literal["finance", "operations"]


def build_specialist_graph(
    agent_name: SpecialistName,
    *,
    model: Any | None = None,
    tool_registry: ToolRegistry | None = None,
):
    """Compile a specialist that can call only its authorized SQL tools."""

    active_registry = tool_registry or default_tool_registry
    tools = active_registry.tools_for(agent_name)
    if not tools:
        raise RuntimeError(f"No tools are registered for {agent_name}")
    active_model = model or create_specialist_model(agent_name)
    model_with_tools = active_model.bind_tools(tools)
    tool_descriptions = active_registry.describe_for(agent_name)

    async def call_specialist(state: SpecialistState) -> dict[str, Any]:
        prompt = build_specialist_prompt(
            agent_name=agent_name,
            task=state["task"],
            available_tools=tool_descriptions,
        )
        response = await model_with_tools.ainvoke(
            [SystemMessage(content=prompt), *state["messages"]],
            config={
                "run_name": f"{agent_name}_model",
                "tags": [agent_name, "specialist-analysis"],
            },
        )
        return {"messages": [response]}

    builder = StateGraph(SpecialistState)
    builder.add_node(agent_name, call_specialist)
    builder.add_node(f"{agent_name}_tools", ToolNode(tools=tools, handle_tool_errors=True))
    builder.add_edge(START, agent_name)
    builder.add_conditional_edges(
        agent_name,
        tools_condition,
        {"tools": f"{agent_name}_tools", END: END},
    )
    builder.add_edge(f"{agent_name}_tools", agent_name)
    return builder.compile(name=f"{agent_name}-agent")


__all__ = ["SpecialistName", "build_specialist_graph"]
