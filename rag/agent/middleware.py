"""Translate LangChain callbacks into safe public progress events."""

from __future__ import annotations

import json
from time import perf_counter
from typing import Any, Iterable
from uuid import UUID

from langchain_core.callbacks import AsyncCallbackHandler
from langchain_core.messages import AIMessage, AIMessageChunk, ToolMessage
from langchain_core.outputs import LLMResult

from observability import logger
from rag.agent.state import PublicAgentEvent


def content_text(content: Any) -> str:
    """Extract answer text while deliberately ignoring private reasoning blocks."""

    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    parts: list[str] = []
    for block in content:
        if not isinstance(block, dict):
            continue
        block_type = str(block.get("type", ""))
        if block_type not in {"text", "output_text"}:
            continue
        text = block.get("text")
        if isinstance(text, str):
            parts.append(text)
    return "".join(parts)


def _contains_reasoning(content: Any) -> bool:
    """Detect reasoning metadata without returning private reasoning text."""

    if not isinstance(content, list):
        return False
    return any(
        isinstance(block, dict)
        and str(block.get("type", "")) in {"reasoning", "reasoning_summary"}
        for block in content
    )


def _tool_payload(output: Any) -> dict[str, Any] | None:
    if isinstance(output, ToolMessage):
        output = output.content
    if isinstance(output, list) and len(output) == 1 and isinstance(output[0], ToolMessage):
        output = output[0].content
    if not isinstance(output, str):
        return None
    try:
        value = json.loads(output)
    except json.JSONDecodeError:
        return None
    if isinstance(value, dict):
        return value
    if isinstance(value, list):
        return {"items": value}
    return None


def _final_message(output: Any) -> AIMessage | None:
    if not isinstance(output, dict):
        return None
    messages = output.get("messages")
    if not isinstance(messages, list):
        return None
    for message in reversed(messages):
        if isinstance(message, AIMessage) and not message.tool_calls:
            return message
    return None


class PublicEventMiddleware:
    """A middleware-style adapter for UI-safe progress, tools, and citations."""

    def __init__(self, allowed_tools: Iterable[str]) -> None:
        self.allowed_tools = frozenset(allowed_tools)
        self.answer_parts: list[str] = []
        self.sources: list[dict[str, Any]] = []
        self._streamed_text = False
        self._reasoning_announced = False
        self._announced_specialists: set[str] = set()
        self._model_turns: dict[str, int] = {}

    def started(self, run_id: str) -> PublicAgentEvent:
        return {
            "event": "status",
            "data": {
                "run_id": run_id,
                "stage": "thinking",
                "message": "Understanding the question and selecting the right capability.",
            },
        }

    def translate(self, event: dict[str, Any]) -> list[PublicAgentEvent]:
        event_type = event.get("event")
        name = str(event.get("name", ""))
        data = event.get("data") or {}
        tags = set(event.get("tags") or [])
        translated: list[PublicAgentEvent] = []

        if event_type == "on_chat_model_start":
            progress = self._model_progress_message(name, tags)
            if progress:
                translated.append(
                    {
                        "event": "status",
                        "data": {
                            "stage": "reasoning",
                            "message": progress,
                        },
                    }
                )
        elif (
            event_type == "on_chain_start"
            and name in {"finance-agent", "operations-agent"}
            and name not in self._announced_specialists
        ):
            self._announced_specialists.add(name)
            label = "Finance" if name == "finance-agent" else "Operations"
            translated.append(
                {
                    "event": "status",
                    "data": {
                        "stage": "specialist",
                        "message": f"{label} Agent is analyzing structured business data.",
                    },
                }
            )
        elif event_type == "on_tool_start" and name in self.allowed_tools:
            translated.extend(
                [
                    {
                        "event": "status",
                        "data": {
                            "stage": "tool",
                            "message": self._tool_start_message(name),
                        },
                    },
                    {
                        "event": "tool_start",
                        "data": {"name": name, "message": f"{name} was called."},
                    },
                ]
            )
        elif event_type == "on_tool_end" and name in self.allowed_tools:
            payload = _tool_payload(data.get("output"))
            if payload:
                if name == "load_operations_skills" and payload.get("success") is True:
                    skill_items = payload.get("selected_skill_titles") or []
                    translated.append(
                        {
                            "event": "skills",
                            "data": {
                                "items": skill_items,
                                "message": f"{', '.join(skill_items)} skills were loaded.",
                            },
                        }
                    )
                sources = payload.get("sources")
                if isinstance(sources, list):
                    added: list[dict[str, Any]] = []
                    existing = {
                        str(item.get("citation") or item) for item in self.sources
                    }
                    for item in sources:
                        if not isinstance(item, dict):
                            continue
                        identity = str(item.get("citation") or item)
                        if identity in existing:
                            continue
                        existing.add(identity)
                        self.sources.append(item)
                        added.append(item)
                    if added:
                        translated.append(
                            {"event": "sources", "data": {"items": self.sources}}
                        )
                if name.startswith("delegate_"):
                    validation = payload.get("validation")
                    if isinstance(validation, dict):
                        valid = validation.get("valid") is True
                        translated.append(
                            {
                                "event": "validation",
                                "data": {
                                    "agent": name.removeprefix("delegate_"),
                                    "valid": valid,
                                    "successful_query_count": int(
                                        validation.get("successful_query_count") or 0
                                    ),
                                    "successful_review_tool_count": int(
                                        validation.get("successful_review_tool_count") or 0
                                    ),
                                    "workflow_count": int(
                                        validation.get("workflow_count") or 0
                                    ),
                                    "workflows": validation.get("workflows") or [],
                                    "evidence_count": int(
                                        validation.get("evidence_count") or 0
                                    ),
                                    "errors": validation.get("errors") or [],
                                    "warnings": validation.get("warnings") or [],
                                    "message": (
                                        "Specialist evidence passed deterministic validation."
                                        if valid
                                        else "Specialist evidence failed deterministic validation."
                                    ),
                                },
                            }
                        )
            translated.extend(
                [
                    {
                        "event": "tool_end",
                        "data": {"name": name, "message": self._tool_end_message(name, payload)},
                    },
                    {
                        "event": "status",
                        "data": self._status_after_tool(name, payload),
                    },
                ]
            )
        elif event_type == "on_chat_model_stream" and "public-answer" in tags:
            chunk = data.get("chunk")
            if isinstance(chunk, AIMessageChunk):
                if _contains_reasoning(chunk.content) and not self._reasoning_announced:
                    self._reasoning_announced = True
                    translated.append(
                        {
                            "event": "reasoning",
                            "data": {
                                "active": True,
                                "message": "The model is reasoning over the available context.",
                            },
                        }
                    )
                text = content_text(chunk.content)
                if text:
                    self._streamed_text = True
                    self.answer_parts.append(text)
                    translated.append({"event": "token", "data": {"text": text}})
        elif event_type == "on_chain_end" and name == "business-supervisor":
            if not self._streamed_text:
                message = _final_message(data.get("output"))
                if message is not None:
                    text = content_text(message.content)
                    if text:
                        self.answer_parts.append(text)
                        translated.append({"event": "token", "data": {"text": text}})

        return translated

    @property
    def answer(self) -> str:
        return "".join(self.answer_parts).strip()

    def _model_progress_message(self, name: str, tags: set[str]) -> str:
        """Return a safe phase summary, never model chain-of-thought text."""

        if "supervisor-routing" in tags or name == "supervisor_routing_model":
            return "Supervisor is identifying the period, metrics, and required evidence sources."
        if "supervisor-synthesis" in tags or name == "supervisor_synthesis_model":
            return "Supervisor is reconciling validated evidence and drafting the final answer."

        agent = "finance" if "finance" in tags else "operations" if "operations" in tags else ""
        if not agent:
            return ""
        turn = self._model_turns.get(agent, 0) + 1
        self._model_turns[agent] = turn
        label = "Finance" if agent == "finance" else "Operations"
        if turn == 1:
            if agent == "operations":
                return "Operations is selecting a dedicated workflow or the governed SQL fallback."
            return "Finance is identifying the required measures and authorized schema."
        if turn == 2:
            if agent == "operations":
                return "Operations is using the authorized evidence tools for the selected workflow."
            return "Finance is composing one governed read-only query."
        if turn == 3:
            return f"{label} is checking returned evidence and preparing its finding."
        return f"{label} is correcting an evidence gap using validator feedback."

    @staticmethod
    def _status_after_tool(
        name: str,
        payload: dict[str, Any] | None,
    ) -> dict[str, Any]:
        payload = payload or {}
        if name == "load_operations_skills":
            if payload.get("success") is True:
                return {
                    "stage": "workflow_execution",
                    "message": "Selected workflow instructions are loaded; Operations is collecting evidence.",
                }
            return {
                "stage": "workflow_selection",
                "message": "The workflow selection needs correction before evidence collection.",
            }
        if name.startswith("search_") and name.endswith("_schema"):
            return {
                "stage": "query_planning",
                "message": "Authorized schema is ready; the specialist is composing a read-only query.",
            }
        if name.startswith("resolve_") and name.endswith("_entity"):
            return {
                "stage": "query_planning",
                "message": "Entity candidates are ready; the specialist is applying the validated filter.",
            }
        if name.startswith("execute_") and name.endswith("_sql"):
            if payload.get("success") is True:
                return {
                    "stage": "evidence_validation",
                    "message": "The query succeeded; the specialist is validating the returned evidence.",
                }
            if payload.get("error_type") == "concurrent_query_blocked":
                return {
                    "stage": "query_guard",
                    "message": "A parallel SQL alternative was blocked; the active query remains authoritative.",
                }
            if payload.get("error_type") == "already_succeeded":
                return {
                    "stage": "query_guard",
                    "message": "An extra SQL call was blocked because successful evidence already exists.",
                }
            return {
                "stage": "query_revision",
                "message": "The query needs correction; the specialist is using validator feedback.",
            }
        if name.startswith("delegate_"):
            validation = payload.get("validation") or {}
            if payload.get("status") == "completed" and validation.get("valid") is True:
                return {
                    "stage": "answering",
                    "message": "Validated specialist evidence is ready for final synthesis.",
                }
            if payload.get("status") == "duplicate_blocked":
                return {
                    "stage": "delegation_guard",
                    "message": "A duplicate specialist delegation was blocked; existing evidence will be used.",
                }
            return {
                "stage": "evidence_gap",
                "message": "The specialist finished without validated evidence; the limitation will be reported.",
            }
        if name == "search_knowledge":
            return {
                "stage": "answering",
                "message": "Knowledge evidence is ready for final synthesis.",
            }
        if name == "find_real_name":
            return {
                "stage": "query_planning",
                "message": "Canonical product candidates are ready for the specialist.",
            }
        if name == "check_purchase_rate":
            if payload.get("result_status") == "ok":
                return {
                    "stage": "evidence_validation",
                    "message": "Purchase-rate evidence is ready for validation.",
                }
            return {
                "stage": "evidence_gap",
                "message": "The purchase rate was unavailable; the limitation will be reported.",
            }
        if name == "check_like_rate":
            if payload.get("result_status") == "ok":
                return {
                    "stage": "evidence_validation",
                    "message": "Like-rate evidence is ready for validation.",
                }
            return {
                "stage": "evidence_gap",
                "message": "The like rate was unavailable; the limitation will be reported.",
            }
        if name in {"check_less_like", "check_less_purchase"}:
            return {
                "stage": "evidence_validation",
                "message": "The Bottom-10 product ranking is ready for validation.",
            }
        if name == "check_most_interact":
            return {
                "stage": "evidence_validation",
                "message": "The interaction-duration product ranking is ready for validation.",
            }
        if name in {
            "search_customer_reviews",
            "find_other_comment_product",
            "find_other_comment_category",
        }:
            return {
                "stage": "evidence_validation",
                "message": "Review evidence is ready; Operations is checking the retrieved feedback.",
            }
        return {
            "stage": "working",
            "message": "The completed step is being incorporated into the analysis.",
        }

    @staticmethod
    def _tool_start_message(name: str) -> str:
        messages = {
            "search_knowledge": "Searching the uploaded knowledge base for supporting rules.",
            "delegate_finance": "Preparing a structured task for the Finance Agent.",
            "delegate_operations": "Preparing a structured task for the Operations Agent.",
            "load_operations_skills": "Loading instructions for the selected Operations workflows.",
            "find_real_name": "Matching the requested product to canonical database names.",
            "check_purchase_rate": "Calculating the product's interest-to-purchase event ratio.",
            "check_like_rate": "Calculating the product's view-to-like event ratio.",
            "check_less_like": "Reading the ten lowest like-rate products from the metrics view.",
            "check_less_purchase": "Reading the ten lowest purchase-rate products from the metrics view.",
            "check_most_interact": "Ranking products by total and average interaction duration.",
            "search_finance_schema": "Finance is selecting authorized tables and columns.",
            "resolve_finance_entity": "Finance is matching the requested entity to database values.",
            "execute_finance_sql": "Finance is validating and running a read-only SQL query.",
            "search_operations_schema": "Operations is selecting authorized tables and columns.",
            "resolve_operations_entity": "Operations is matching the requested entity to database values.",
            "execute_operations_sql": "Operations is validating and running a read-only SQL query.",
            "search_customer_reviews": "Operations is searching customer review themes with structured filters.",
            "find_other_comment_product": "Operations is retrieving additional unseen reviews for the selected product.",
            "find_other_comment_category": "Operations is retrieving additional unseen reviews for the selected category.",
        }
        return messages.get(name, f"Running {name}.")

    @staticmethod
    def _tool_end_message(name: str, payload: dict[str, Any] | None) -> str:
        if name == "load_operations_skills" and payload is not None:
            if payload.get("success") is True:
                count = len(payload.get("selected_skills") or [])
                return f"{name} loaded {count} workflow skill(s)."
            return f"{name} reported {payload.get('error_type', 'an error')}."
        if name == "find_real_name" and payload is not None:
            return f"{name} returned {len(payload.get('items') or [])} canonical product names."
        if name == "check_purchase_rate" and payload is not None:
            return f"{name} completed with status {payload.get('result_status', 'unknown')}."
        if name == "check_like_rate" and payload is not None:
            return f"{name} completed with status {payload.get('result_status', 'unknown')}."
        if name in {"check_less_like", "check_less_purchase"} and payload is not None:
            return f"{name} returned {len(payload.get('items') or [])} ranked products with metric values."
        if name == "check_most_interact" and payload is not None:
            return f"{name} returned {len(payload.get('items') or [])} ranked products with interaction metrics."
        if name == "search_knowledge" and payload:
            if payload.get("success") is False:
                return f"{name} could not retrieve knowledge evidence."
            count = len(payload.get("matches") or [])
            return f"{name} returned {count} relevant knowledge chunks."
        if name in {
            "search_customer_reviews",
            "find_other_comment_product",
            "find_other_comment_category",
        } and payload:
            if payload.get("success") is False:
                return f"{name} could not retrieve customer-review evidence."
            count = len(payload.get("matches") or [])
            return f"{name} returned {count} relevant customer reviews."
        if name.startswith("search_") and name.endswith("_schema") and payload:
            return f"{name} returned {len(payload.get('tables') or [])} authorized schemas."
        if name.startswith("resolve_") and name.endswith("_entity") and payload:
            return f"{name} returned {len(payload.get('candidates') or [])} candidates."
        if name.startswith("execute_") and name.endswith("_sql") and payload:
            if payload.get("success"):
                return f"{name} returned {payload.get('row_count', 0)} rows."
            return f"{name} reported {payload.get('error_type', 'an error')}; the specialist may revise the query."
        if name.startswith("delegate_") and payload:
            if payload.get("status") == "duplicate_blocked":
                return f"{name} duplicate call was blocked."
            validation = payload.get("validation") or {}
            if payload.get("status") == "completed" and validation.get("valid") is True:
                return f"{name} completed with validated evidence."
            return f"{name} completed without usable validated evidence."
        return f"{name} completed."


class AgentLoggingCallback(AsyncCallbackHandler):
    """Record model lifecycle metadata without prompts or private reasoning."""

    def __init__(self) -> None:
        self._started_at: dict[UUID, float] = {}
        self._first_token_at: dict[UUID, float] = {}
        self._models: dict[UUID, str] = {}
        self._phases: dict[UUID, str] = {}

    @staticmethod
    def _response_phase(kwargs: dict[str, Any]) -> str:
        tags = {str(tag) for tag in kwargs.get("tags") or []}
        name = str(kwargs.get("name") or "")
        if "supervisor-routing" in tags or name == "supervisor_routing_model":
            return "supervisor_routing"
        if "supervisor-synthesis" in tags or name == "supervisor_synthesis_model":
            return "supervisor_synthesis"
        if "finance" in tags or name == "finance_model":
            return "finance_specialist"
        if "operations" in tags or name == "operations_model":
            return "operations_specialist"
        return name or "unknown"

    @staticmethod
    def _usage_tokens(response: LLMResult) -> tuple[int | None, int | None]:
        candidates: list[Any] = []
        llm_output = response.llm_output or {}
        candidates.extend(
            [
                llm_output.get("token_usage"),
                llm_output.get("usage"),
            ]
        )
        for generation_group in response.generations:
            for generation in generation_group:
                message = getattr(generation, "message", None)
                if message is None:
                    continue
                candidates.append(getattr(message, "usage_metadata", None))
                response_metadata = getattr(message, "response_metadata", None) or {}
                if isinstance(response_metadata, dict):
                    candidates.extend(
                        [
                            response_metadata.get("token_usage"),
                            response_metadata.get("usage"),
                        ]
                    )
        for usage in candidates:
            if not isinstance(usage, dict):
                continue
            input_tokens = usage.get("prompt_tokens")
            if input_tokens is None:
                input_tokens = usage.get("input_tokens")
            output_tokens = usage.get("completion_tokens")
            if output_tokens is None:
                output_tokens = usage.get("output_tokens")
            if input_tokens is not None or output_tokens is not None:
                return input_tokens, output_tokens
        return None, None

    async def on_chat_model_start(
        self,
        serialized: dict[str, Any],
        messages: list[list[Any]],
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        invocation = kwargs.get("invocation_params") or {}
        model = str(
            invocation.get("model")
            or invocation.get("model_name")
            or serialized.get("name")
            or "unknown"
        )
        self._started_at[run_id] = perf_counter()
        self._models[run_id] = model
        phase = self._response_phase(kwargs)
        self._phases[run_id] = phase
        logger.model_event(
            status="started",
            model=model,
            operation="responses",
            response_phase=phase,
        )

    async def on_llm_new_token(
        self,
        token: str,
        *,
        run_id: UUID,
        chunk: Any | None = None,
        **kwargs: Any,
    ) -> None:
        if run_id in self._first_token_at:
            return
        chunk_content = getattr(chunk, "content", None)
        if not token and not content_text(chunk_content):
            return
        first_token_at = perf_counter()
        self._first_token_at[run_id] = first_token_at
        started_at = self._started_at.get(run_id, first_token_at)
        logger.model_event(
            status="first_token",
            model=self._models.get(run_id, "unknown"),
            operation="responses",
            duration_ms=round((first_token_at - started_at) * 1000, 2),
            response_phase=self._phases.get(run_id, self._response_phase(kwargs)),
        )

    async def on_llm_end(
        self,
        response: LLMResult,
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        started_at = self._started_at.pop(run_id, perf_counter())
        completed_at = perf_counter()
        first_token_at = self._first_token_at.pop(run_id, None)
        model = self._models.pop(run_id, "unknown")
        phase = self._phases.pop(run_id, "unknown")
        input_tokens, output_tokens = self._usage_tokens(response)
        logger.model_event(
            status="completed",
            model=model,
            operation="responses",
            duration_ms=round((completed_at - started_at) * 1000, 2),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            response_phase=phase,
            time_to_first_token_ms=(
                round((first_token_at - started_at) * 1000, 2)
                if first_token_at is not None
                else None
            ),
            generation_duration_ms=(
                round((completed_at - first_token_at) * 1000, 2)
                if first_token_at is not None
                else None
            ),
        )

    async def on_llm_error(
        self,
        error: BaseException,
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        started_at = self._started_at.pop(run_id, perf_counter())
        first_token_at = self._first_token_at.pop(run_id, None)
        model = self._models.pop(run_id, "unknown")
        phase = self._phases.pop(run_id, "unknown")
        logger.model_event(
            status="failed",
            model=model,
            operation="responses",
            duration_ms=round((perf_counter() - started_at) * 1000, 2),
            error_type=type(error).__name__,
            response_phase=phase,
            time_to_first_token_ms=(
                round((first_token_at - started_at) * 1000, 2)
                if first_token_at is not None
                else None
            ),
        )


__all__ = ["AgentLoggingCallback", "PublicEventMiddleware", "content_text"]
