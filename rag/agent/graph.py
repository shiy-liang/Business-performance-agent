"""Build the extensible LangGraph supervisor and tool-call loop."""

from __future__ import annotations

import json
from functools import lru_cache
from typing import Any

from langchain_core.messages import SystemMessage, ToolMessage
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode

from config.settings import load_agent_settings
from rag.agent.model import create_supervisor_model
from rag.agent.prompts import build_supervisor_prompt
from rag.agent.state import SupervisorState
from rag.agent.tools.registry import ToolRegistry, default_tool_registry


_PLANNING_SETTINGS = load_agent_settings().planning


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
    tools_by_name = {tool.name: tool for tool in tools}
    planning_tool = tools_by_name.get("format_sub_task")
    if planning_tool is None:
        raise RuntimeError("Supervisor tool registry must include format_sub_task")
    dispatch_tools = [tool for tool in tools if tool.name != "format_sub_task"]
    routing_model = model or create_supervisor_model(phase="routing")
    synthesis_model = model or create_supervisor_model(phase="synthesis")
    planning_model_with_tools = routing_model.bind_tools([planning_tool])
    dispatch_model_with_tools = routing_model.bind_tools(dispatch_tools)
    tool_descriptions = active_registry.describe_for("supervisor")

    def successful_plan(messages: list[Any]) -> dict[str, Any] | None:
        for message in reversed(messages):
            if not isinstance(message, ToolMessage):
                continue
            if getattr(message, "name", None) != "format_sub_task":
                continue
            try:
                payload = json.loads(str(message.content))
            except json.JSONDecodeError:
                return None
            if isinstance(payload, dict) and payload.get("success") is True:
                return payload
            return None
        return None

    def required_dispatch_tools(plan: dict[str, Any]) -> set[str]:
        groups = plan.get("groups")
        if not isinstance(groups, dict):
            return set()
        mapping = {
            "operations": "delegate_operations",
            "finance": "delegate_finance",
            "supervisor": "search_knowledge",
        }
        return {
            tool_name
            for group_name, tool_name in mapping.items()
            if isinstance(groups.get(group_name), list) and groups[group_name]
        }

    def completed_dispatch_tools(messages: list[Any]) -> set[str]:
        plan_index = -1
        for index, message in enumerate(messages):
            if (
                isinstance(message, ToolMessage)
                and getattr(message, "name", None) == "format_sub_task"
            ):
                plan_index = index
        return {
            str(getattr(message, "name", ""))
            for message in messages[plan_index + 1 :]
            if isinstance(message, ToolMessage)
            and getattr(message, "name", None) != "format_sub_task"
        }

    async def call_supervisor(state: SupervisorState) -> dict[str, Any]:
        messages = list(state["messages"])
        plan = successful_plan(messages)
        completed_tool_names = completed_dispatch_tools(messages)
        required_tools = required_dispatch_tools(plan) if plan else set()
        dispatch_complete = bool(plan) and required_tools.issubset(
            completed_tool_names
        )
        system_prompt = build_supervisor_prompt(
            user_question=state["user_question"],
            available_tools=tool_descriptions,
        )
        if dispatch_complete:
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
        elif plan is not None:
            system_prompt += (
                "\n\n## Current execution phase\n\n"
                "The subtask plan is fixed. Dispatch every non-empty group now in one "
                "tool-call turn. Call each required specialist no more than "
                f"{_PLANNING_SETTINGS.max_delegations_per_specialist} time(s) using the "
                "exact ordered task IDs in the formatter's groups. For the optional "
                "supervisor group, call search_knowledge with its exact question. Emit "
                "no prose and do not change the plan."
            )
            active_model = dispatch_model_with_tools
            run_name = "supervisor_dispatch_model"
            tags = ["supervisor", "supervisor-dispatch"]
        else:
            system_prompt += (
                "\n\n## Current execution phase\n\n"
                "Decide whether external evidence is required. If it is, decompose the "
                "complete request and call format_sub_task as the only tool in this turn. "
                "If no external evidence is needed, answer the user directly."
            )
            active_model = planning_model_with_tools
            run_name = "supervisor_planning_model"
            tags = ["supervisor", "supervisor-planning"]
        response = await active_model.ainvoke(
            [SystemMessage(content=system_prompt), *state["messages"]],
            config={
                "run_name": run_name,
                "tags": tags,
            },
        )
        return {"messages": [response]}

    def route_after_supervisor(state: SupervisorState) -> str:
        messages = list(state["messages"])
        last_message = messages[-1]
        if getattr(last_message, "tool_calls", None):
            return "tools"
        plan = successful_plan(messages)
        if plan is not None:
            completed = completed_dispatch_tools(messages)
            if not required_dispatch_tools(plan).issubset(completed):
                return "supervisor"
        return END

    builder = StateGraph(SupervisorState)
    builder.add_node("supervisor", call_supervisor)
    builder.add_node("tools", ToolNode(tools=tools, handle_tool_errors=True))
    builder.add_edge(START, "supervisor")
    builder.add_conditional_edges(
        "supervisor",
        route_after_supervisor,
        {"tools": "tools", "supervisor": "supervisor", END: END},
    )
    builder.add_edge("tools", "supervisor")
    return builder.compile(name="business-supervisor")


@lru_cache(maxsize=1)
def get_default_supervisor_graph():
    """Return the process-wide Supervisor graph built during application startup."""

    return build_supervisor_graph(tool_registry=default_tool_registry)


__all__ = ["build_supervisor_graph", "get_default_supervisor_graph"]
