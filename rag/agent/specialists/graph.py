"""Reusable LangGraph tool loop for structured-data specialists."""

from __future__ import annotations

import json
from functools import lru_cache
from typing import Any, Literal

from langchain_core.messages import AIMessage, SystemMessage, ToolMessage
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
    """Compile a specialist that can call only its authorized domain tools."""

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

    def route_after_tools(state: SpecialistState) -> str:
        for message in reversed(state["messages"]):
            if not isinstance(message, ToolMessage):
                break
            try:
                payload = json.loads(str(message.content))
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict) and payload.get("error_type") in {
                "user_rejected",
                "approval_timeout",
            }:
                return "sql_cancelled"
            if (
                isinstance(payload, dict)
                and payload.get("error_type") == "canonical_product_not_found"
                and payload.get("terminal") is True
            ):
                return "product_resolution_failed"
        return agent_name

    async def finish_cancelled_sql(state: SpecialistState) -> dict[str, Any]:
        error_type = "user_rejected"
        for message in reversed(state["messages"]):
            if not isinstance(message, ToolMessage):
                break
            try:
                payload = json.loads(str(message.content))
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict) and payload.get("error_type") in {
                "user_rejected",
                "approval_timeout",
            }:
                error_type = str(payload["error_type"])
                break
        reason = (
            "SQL approval timed out"
            if error_type == "approval_timeout"
            else "The user rejected the generated SQL"
        )
        return {
            "messages": [
                AIMessage(
                    content=(
                        f"{reason}. The database query was not executed, so no "
                        "database result or citation is available."
                    )
                )
            ]
        }

    async def finish_unresolved_product(state: SpecialistState) -> dict[str, Any]:
        return {
            "messages": [
                AIMessage(
                    content=(
                        "No canonical product name matched after three sequential "
                        "resolution attempts. No product metric query was executed. "
                        "Ask the user for the exact product name or model; never "
                        "guess or invent one."
                    )
                )
            ]
        }

    builder = StateGraph(SpecialistState)
    builder.add_node(agent_name, call_specialist)
    builder.add_node(f"{agent_name}_tools", ToolNode(tools=tools, handle_tool_errors=True))
    builder.add_node("sql_cancelled", finish_cancelled_sql)
    builder.add_node("product_resolution_failed", finish_unresolved_product)
    builder.add_edge(START, agent_name)
    builder.add_conditional_edges(
        agent_name,
        tools_condition,
        {"tools": f"{agent_name}_tools", END: END},
    )
    builder.add_conditional_edges(
        f"{agent_name}_tools",
        route_after_tools,
        {
            agent_name: agent_name,
            "sql_cancelled": "sql_cancelled",
            "product_resolution_failed": "product_resolution_failed",
        },
    )
    builder.add_edge("sql_cancelled", END)
    builder.add_edge("product_resolution_failed", END)
    return builder.compile(name=f"{agent_name}-agent")


@lru_cache(maxsize=2)
def get_default_specialist_graph(agent_name: SpecialistName):
    """Return one process-wide specialist graph with a reused model client."""

    return build_specialist_graph(agent_name, tool_registry=default_tool_registry)


__all__ = [
    "SpecialistName",
    "build_specialist_graph",
    "get_default_specialist_graph",
]
