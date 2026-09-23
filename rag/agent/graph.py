"""Build the extensible LangGraph supervisor and tool-call loop."""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from langchain_core.messages import SystemMessage, ToolMessage
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition

from rag.agent.model import create_supervisor_model
from rag.agent.prompts import build_supervisor_prompt
from rag.agent.state import SupervisorState
from rag.agent.tools.registry import ToolRegistry, default_tool_registry


def build_supervisor_graph(
    *,
    model: Any | None = None,
    tool_registry: ToolRegistry | None = None,
):
    """Compile a supervisor that can call only supervisor-authorized tools."""

    from rag.agent.specialists.runtime import ensure_default_specialists_registered

    ensure_default_specialists_registered()
    active_registry = tool_registry or default_tool_registry
    tools = active_registry.tools_for("supervisor")
    routing_model = model or create_supervisor_model(phase="routing")
    synthesis_model = model or create_supervisor_model(phase="synthesis")
    routing_model_with_tools = routing_model.bind_tools(tools)
    tool_descriptions = active_registry.describe_for("supervisor")

    async def call_supervisor(state: SupervisorState) -> dict[str, Any]:
        has_tool_evidence = any(
            isinstance(message, ToolMessage) for message in state["messages"]
        )
        system_prompt = build_supervisor_prompt(
            user_question=state["user_question"],
            available_tools=tool_descriptions,
        )
        if has_tool_evidence:
            system_prompt += (
                "\n\n## Current execution phase\n\n"
                "Tool execution is complete. Synthesize the final user answer from the "
                "available validated evidence. Do not request, call, or propose another "
                "tool or specialist in this turn. If evidence is incomplete, state the "
                "gap explicitly."
            )
            active_model = synthesis_model
            run_name = "supervisor_synthesis_model"
            tags = ["supervisor", "supervisor-synthesis", "public-answer"]
        else:
            system_prompt += (
                "\n\n## Current execution phase\n\n"
                "Plan the complete evidence request now. Call every independently required "
                "tool in this single turn, with at most one call per specialist. If no tool "
                "is needed, answer the user directly."
            )
            active_model = routing_model_with_tools
            run_name = "supervisor_routing_model"
            tags = ["supervisor", "supervisor-routing"]
        response = await active_model.ainvoke(
            [SystemMessage(content=system_prompt), *state["messages"]],
            config={
                "run_name": run_name,
                "tags": tags,
            },
        )
        return {"messages": [response]}

    builder = StateGraph(SupervisorState)
    builder.add_node("supervisor", call_supervisor)
    builder.add_node("tools", ToolNode(tools=tools, handle_tool_errors=True))
    builder.add_edge(START, "supervisor")
    builder.add_conditional_edges(
        "supervisor",
        tools_condition,
        {"tools": "tools", END: END},
    )
    builder.add_edge("tools", "supervisor")
    return builder.compile(name="business-supervisor")


@lru_cache(maxsize=1)
def get_default_supervisor_graph():
    """Return the process-wide Supervisor graph built during application startup."""

    return build_supervisor_graph(tool_registry=default_tool_registry)


__all__ = ["build_supervisor_graph", "get_default_supervisor_graph"]
