"""Deterministic checks applied to specialist evidence before synthesis."""

from __future__ import annotations

import re
from typing import Any, Literal

from rag.agent.workflows import (
    load_finance_skill_config,
    load_operations_skill_config,
)


SpecialistName = Literal["finance", "operations"]
REVIEW_TOOL_NAMES = frozenset(
    {
        "search_customer_reviews",
        "find_other_comment_product",
        "find_other_comment_category",
    }
)
TICKET_PROBLEM_TOOL_NAMES = frozenset({"check_concrete_problem"})
FINANCE_METRIC_TOOL_NAMES = frozenset(
    {"calculate_net_sales", "calculate_gross_profit", "calculate_gross_margin"}
)
PRODUCT_RESOLUTION_TOOL_NAMES = frozenset({"find_real_name"})
CAMPAIGN_RESOLUTION_TOOL_NAMES = frozenset({"find_real_campaign_name"})
SUBTASK_STATUS_TOOL_NAMES = frozenset({"update_sub_task_status"})
GENERIC_OPERATIONS_TOOL_NAMES = frozenset(
    {
        "search_operations_schema",
        "resolve_operations_entity",
        "execute_operations_sql",
    }
)
ARTIFACT_ONLY_TOOL_NAMES = frozenset(
    {
        "check_less_like",
        "check_less_purchase",
        "check_most_interact",
    }
)
DEDICATED_OPERATIONS_TOOL_TO_SKILL = {
    "check_concrete_problem": "support_ticket_problem_retrieval",
    "search_customer_reviews": "product_review_retrieval",
    "find_other_comment_product": "product_review_retrieval",
    "find_other_comment_category": "product_review_retrieval",
    "check_purchase_rate": "product_purchase_rate",
    "check_like_rate": "product_like_rate",
    "check_less_like": "product_bottom_rates",
    "check_less_purchase": "product_bottom_rates",
    "check_most_interact": "product_interaction_duration",
}
DEDICATED_FINANCE_TOOL_TO_SKILL = {
    "calculate_net_sales": "net_sales",
    "calculate_gross_profit": "gross_profit_margin",
    "calculate_gross_margin": "gross_profit_margin",
    "check_less_purchase": "product_bottom_purchase_rate",
}
GENERIC_FINANCE_TOOL_NAMES = frozenset(
    {
        "search_finance_schema",
        "resolve_finance_entity",
        "execute_finance_sql",
    }
)


def validate_specialist_evidence(
    agent_name: SpecialistName,
    answer: str,
    tool_payloads: list[dict[str, Any]],
    sources: list[dict[str, Any]],
    *,
    assigned_sub_tasks: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    """Validate that a specialist conclusion is backed by successful tools."""

    errors: list[str] = []
    warnings: list[str] = []
    successful_queries = [
        payload
        for payload in tool_payloads
        if payload.get("success") is True
        and payload.get("agent") == agent_name
        and isinstance(payload.get("citation"), str)
    ]
    failed_queries = [
        payload
        for payload in tool_payloads
        if payload.get("success") is False
        and payload.get("agent") == agent_name
        and payload.get("tool") not in REVIEW_TOOL_NAMES
        and payload.get("tool") not in TICKET_PROBLEM_TOOL_NAMES
        and payload.get("tool") not in FINANCE_METRIC_TOOL_NAMES
        and payload.get("tool") not in PRODUCT_RESOLUTION_TOOL_NAMES
        and payload.get("tool") not in CAMPAIGN_RESOLUTION_TOOL_NAMES
        and payload.get("tool") not in SUBTASK_STATUS_TOOL_NAMES
        and payload.get("error_type")
        not in {
            None,
            "already_succeeded",
            "attempt_limit",
            "concurrent_query_blocked",
        }
    ]
    review_payloads = [
        payload
        for payload in tool_payloads
        if payload.get("tool") in REVIEW_TOOL_NAMES
    ]
    successful_review_retrievals = [
        payload for payload in review_payloads if payload.get("success") is True
    ]
    failed_review_searches = [
        payload for payload in review_payloads if payload.get("success") is False
    ]
    ticket_problem_payloads = [
        payload
        for payload in tool_payloads
        if payload.get("tool") in TICKET_PROBLEM_TOOL_NAMES
    ]
    successful_ticket_problem_retrievals = [
        payload
        for payload in ticket_problem_payloads
        if payload.get("success") is True
    ]
    failed_ticket_problem_retrievals = [
        payload
        for payload in ticket_problem_payloads
        if payload.get("success") is False
    ]
    terminal_product_resolution = next(
        (
            payload
            for payload in tool_payloads
            if payload.get("tool") in PRODUCT_RESOLUTION_TOOL_NAMES
            and payload.get("error_type") == "canonical_product_not_found"
            and payload.get("terminal") is True
        ),
        None,
    )
    terminal_campaign_resolution = next(
        (
            payload
            for payload in tool_payloads
            if payload.get("tool") in CAMPAIGN_RESOLUTION_TOOL_NAMES
            and payload.get("error_type") == "canonical_campaign_not_found"
            and payload.get("terminal") is True
        ),
        None,
    )
    uses_review_skill = agent_name == "operations" and bool(review_payloads)
    generic_operations_calls = [
        payload
        for payload in tool_payloads
        if payload.get("tool") in GENERIC_OPERATIONS_TOOL_NAMES
    ]
    dedicated_operations_calls = [
        payload
        for payload in tool_payloads
        if payload.get("tool") in DEDICATED_OPERATIONS_TOOL_TO_SKILL
    ]
    generic_finance_calls = [
        payload
        for payload in tool_payloads
        if payload.get("tool") in GENERIC_FINANCE_TOOL_NAMES
    ]
    dedicated_finance_calls = [
        payload
        for payload in tool_payloads
        if payload.get("tool") in DEDICATED_FINANCE_TOOL_TO_SKILL
    ]
    if agent_name == "finance":
        skill_names = {
            DEDICATED_FINANCE_TOOL_TO_SKILL[str(payload.get("tool"))]
            for payload in dedicated_finance_calls
        }
        loader_name = "load_finance_skills"
    else:
        skill_names = {
            DEDICATED_OPERATIONS_TOOL_TO_SKILL[str(payload.get("tool"))]
            for payload in dedicated_operations_calls
        }
        loader_name = "load_operations_skills"
    loaded_skills: set[str] = set()
    for payload in tool_payloads:
        if (
            payload.get("tool") == loader_name
            and payload.get("success") is True
            and isinstance(payload.get("selected_skills"), list)
        ):
            selected = {str(name) for name in payload["selected_skills"]}
            loaded_skills.update(selected)
    if generic_operations_calls:
        skill_names.add("sql_query")
    if generic_finance_calls:
        skill_names.add("sql_query")
    invoked_skill_names = set(skill_names)
    skill_names.update(loaded_skills)

    if not answer.strip():
        errors.append("The specialist returned no final analysis.")

    if uses_review_skill:
        semantic_searches = [
            payload
            for payload in review_payloads
            if payload.get("tool") == "search_customer_reviews"
        ]
        if review_payloads[0].get("tool") != "search_customer_reviews":
            errors.append(
                "The product-review skill did not call semantic review search first."
            )
        if not any(payload.get("success") is True for payload in semantic_searches):
            if successful_queries:
                warnings.append(
                    "No successful customer-review evidence was returned; other "
                    "skill evidence remains available."
                )
            else:
                errors.append("No successful semantic customer-review search was returned.")
    if agent_name == "operations":
        maximum = load_operations_skill_config().max_skills_per_task
        if len(skill_names) > maximum:
            errors.append(
                f"Operations used {len(skill_names)} skills, exceeding the "
                f"configured maximum of {maximum}."
            )
    if agent_name == "finance":
        maximum = load_finance_skill_config().max_skills_per_task
        if len(skill_names) > maximum:
            errors.append(
                f"Finance used {len(skill_names)} skills, exceeding the "
                f"configured maximum of {maximum}."
            )

    assigned = list(assigned_sub_tasks or [])
    subtask_statuses: dict[str, str] = {}
    if assigned:
        expected_skills = {str(item.get("skill") or "") for item in assigned}
        loader_indices = [
            index
            for index, payload in enumerate(tool_payloads)
            if payload.get("tool") == loader_name
        ]
        if len(loader_indices) != 1:
            errors.append(
                "The specialist must call its skill loader exactly once before "
                "using evidence tools."
            )
        elif any(
            payload.get("tool") != loader_name
            for payload in tool_payloads[: loader_indices[0]]
        ):
            errors.append(
                "The specialist used an evidence tool before loading its assigned skills."
            )
        missing_loaded_skills = sorted(expected_skills - loaded_skills)
        unexpected_loaded_skills = sorted(loaded_skills - expected_skills)
        if missing_loaded_skills:
            errors.append(
                "The specialist did not load every Supervisor-assigned skill: "
                + ", ".join(missing_loaded_skills)
                + "."
            )
        if unexpected_loaded_skills:
            errors.append(
                "The specialist loaded unassigned skills: "
                + ", ".join(unexpected_loaded_skills)
                + "."
            )
        unexpected_skills = sorted(invoked_skill_names - expected_skills)
        if unexpected_skills:
            errors.append(
                "The specialist invoked evidence from unassigned skills: "
                + ", ".join(unexpected_skills)
                + "."
            )
        status_history: dict[str, list[str]] = {
            str(item.get("id") or ""): [] for item in assigned
        }
        for payload in tool_payloads:
            if (
                payload.get("tool") == "update_sub_task_status"
                and payload.get("success") is True
            ):
                task_id = str(payload.get("subtask_id") or "")
                if task_id in status_history:
                    status_history[task_id].append(str(payload.get("status") or ""))
        invalid_transitions: list[str] = []
        for task_id, history in status_history.items():
            if (
                len(history) != 2
                or history[0] != "running"
                or history[1] not in {"completed", "blocked", "empty"}
            ):
                invalid_transitions.append(task_id)
            else:
                subtask_statuses[task_id] = history[1]
        if invalid_transitions:
            errors.append(
                "Every subtask must publish exactly one running transition followed "
                "by exactly one terminal transition: "
                + ", ".join(invalid_transitions)
                + "."
            )
        invalid_sections: list[str] = []
        for item in assigned:
            task_id = str(item.get("id") or "")
            matches = re.findall(
                rf"^### Subtask {re.escape(task_id)} — (completed|blocked|empty)$",
                answer,
                flags=re.MULTILINE,
            )
            if len(matches) != 1:
                invalid_sections.append(task_id)
            elif subtask_statuses.get(task_id) != matches[0]:
                invalid_sections.append(task_id)
        if invalid_sections:
            errors.append(
                "Each assigned subtask must have exactly one valid status section: "
                + ", ".join(invalid_sections)
                + "."
            )
    if (
        not successful_queries
        and not successful_review_retrievals
        and not successful_ticket_problem_retrievals
        and terminal_product_resolution is None
        and terminal_campaign_resolution is None
    ):
        errors.append("No successful specialist evidence was returned.")

    expected_prefix = f"[db:{agent_name}:"
    source_citations = {
        str(source.get("citation"))
        for source in sources
        if isinstance(source, dict) and source.get("citation")
    }
    invalid_sources = sorted(
        citation
        for citation in source_citations
        if citation.startswith("[db:") and not citation.startswith(expected_prefix)
    )
    if invalid_sources:
        errors.append("Specialist evidence contains a citation from another domain.")

    successful_citations = {
        str(payload["citation"]) for payload in successful_queries
    }
    missing_sources = sorted(successful_citations - source_citations)
    if missing_sources:
        errors.append("Successful SQL evidence was not propagated to the source list.")

    citations_required_in_answer = {
        str(payload["citation"])
        for payload in successful_queries
        if payload.get("tool") not in ARTIFACT_ONLY_TOOL_NAMES
    }
    uncited = sorted(
        citation for citation in citations_required_in_answer if citation not in answer
    )
    if uncited:
        errors.append("The specialist conclusion omitted its database citation.")

    review_citations = {
        citation for citation in source_citations if citation.startswith("[review:")
    }
    if review_citations and not any(citation in answer for citation in review_citations):
        errors.append("Customer-review evidence was retrieved but not cited in the conclusion.")

    ticket_citations = {
        citation for citation in source_citations if citation.startswith("[ticket:")
    }
    if ticket_citations and not any(citation in answer for citation in ticket_citations):
        errors.append(
            "Support-ticket problem evidence was retrieved but not cited in the conclusion."
        )

    answer_citations = set(
        re.findall(r"\[(?:db|review|ticket):[^\]\r\n]+\]", answer)
    )
    unsupported_citations = sorted(answer_citations - source_citations)
    if unsupported_citations:
        errors.append("The specialist conclusion contains a citation with no tool evidence.")

    if any(payload.get("truncated") for payload in successful_queries):
        warnings.append("At least one SQL result was truncated by the runtime limit.")
    if any(int(payload.get("row_count") or 0) == 0 for payload in successful_queries):
        warnings.append("At least one successful SQL query returned zero rows.")
    if failed_queries:
        warnings.append(
            f"The specialist corrected {len(failed_queries)} failed SQL attempt(s) before completion."
        )
    if failed_review_searches:
        warnings.append("At least one customer-review retrieval was unavailable or blocked.")
    if failed_ticket_problem_retrievals:
        warnings.append(
            "At least one concrete support-ticket retrieval was unavailable or blocked."
        )
    failed_finance_metrics = [
        payload
        for payload in tool_payloads
        if payload.get("tool") in FINANCE_METRIC_TOOL_NAMES
        and payload.get("success") is False
    ]
    if failed_finance_metrics:
        warnings.append(
            "At least one dedicated Finance metric retrieval was unavailable or blocked."
        )

    return {
        "valid": not errors,
        "errors": errors,
        "warnings": warnings,
        "successful_query_count": len(successful_queries),
        "successful_review_tool_count": len(successful_review_retrievals),
        "successful_ticket_tool_count": len(successful_ticket_problem_retrievals),
        "terminal_product_resolution": terminal_product_resolution is not None,
        "terminal_campaign_resolution": terminal_campaign_resolution is not None,
        "skill_count": len(skill_names),
        "skills": sorted(skill_names),
        "assigned_subtask_count": len(assigned),
        "subtask_statuses": subtask_statuses,
        "evidence_count": len(source_citations),
    }


__all__ = ["validate_specialist_evidence"]
