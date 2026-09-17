"""LangGraph state and public event contracts for the agent runtime."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages
from typing_extensions import TypedDict


AgentName = Literal["supervisor", "finance", "operations"]


class SupervisorState(TypedDict, total=False):
    """State shared by the supervisor model and its tool loop."""

    run_id: str
    user_question: str
    messages: Annotated[list[AnyMessage], add_messages]


class SpecialistState(TypedDict, total=False):
    """State shared by one domain specialist and its SQL tool loop."""

    run_id: str
    task: str
    agent_name: Literal["finance", "operations"]
    messages: Annotated[list[AnyMessage], add_messages]


class PublicAgentEvent(TypedDict):
    """One safe, user-visible event emitted by the agent runtime."""

    event: str
    data: dict[str, Any]


__all__ = [
    "AgentName",
    "PublicAgentEvent",
    "SpecialistState",
    "SupervisorState",
]
