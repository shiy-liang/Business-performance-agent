"""Build the extensible LangGraph supervisor and tool-call loop."""

from __future__ import annotations

from typing import Any

from langchain_core.messages import SystemMessage
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
    active_model = model or create_supervisor_model()
    model_with_tools = active_model.bind_tools(tools)
    tool_descriptions = active_registry.describe_for("supervisor")

    async def call_supervisor(state: SupervisorState) -> dict[str, Any]:
        system_prompt = build_supervisor_prompt(
            user_question=state["user_question"],
            available_tools=tool_descriptions,
        )
        response = await model_with_tools.ainvoke(
            [SystemMessage(content=system_prompt), *state["messages"]],
            config={
                "run_name": "supervisor_model",
                "tags": ["supervisor", "public-answer"],
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


__all__ = ["build_supervisor_graph"]
