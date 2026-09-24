"""Deterministic checks applied to specialist evidence before synthesis."""

from __future__ import annotations

import re
from typing import Any, Literal

from rag.agent.workflows import load_operations_workflow_config


SpecialistName = Literal["finance", "operations"]
REVIEW_TOOL_NAMES = frozenset(
    {
        "search_customer_reviews",
        "find_other_comment_product",
        "find_other_comment_category",
    }
)
TICKET_PROBLEM_TOOL_NAMES = frozenset({"check_concrete_problem"})
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
DEDICATED_OPERATIONS_TOOL_TO_WORKFLOW = {
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


def validate_specialist_evidence(
    agent_name: SpecialistName,
    answer: str,
    tool_payloads: list[dict[str, Any]],
    sources: list[dict[str, Any]],
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
    uses_review_workflow = agent_name == "operations" and bool(review_payloads)
    generic_operations_calls = [
        payload
        for payload in tool_payloads
        if payload.get("tool") in GENERIC_OPERATIONS_TOOL_NAMES
    ]
    dedicated_operations_calls = [
        payload
        for payload in tool_payloads
        if payload.get("tool") in DEDICATED_OPERATIONS_TOOL_TO_WORKFLOW
    ]
    workflow_names = {
        DEDICATED_OPERATIONS_TOOL_TO_WORKFLOW[str(payload.get("tool"))]
        for payload in dedicated_operations_calls
    }
    for payload in tool_payloads:
        if (
            payload.get("tool") == "load_operations_skills"
            and payload.get("success") is True
            and isinstance(payload.get("selected_skills"), list)
        ):
            workflow_names.update(str(name) for name in payload["selected_skills"])
    if generic_operations_calls:
        workflow_names.add("sql_query")

    if not answer.strip():
        errors.append("The specialist returned no final analysis.")

    if uses_review_workflow:
        semantic_searches = [
            payload
            for payload in review_payloads
            if payload.get("tool") == "search_customer_reviews"
        ]
        if review_payloads[0].get("tool") != "search_customer_reviews":
            errors.append(
                "The dedicated product-review workflow did not call semantic review search first."
            )
        if not any(payload.get("success") is True for payload in semantic_searches):
            if successful_queries:
                warnings.append(
                    "No successful customer-review evidence was returned; other "
                    "workflow evidence remains available."
                )
            else:
                errors.append("No successful semantic customer-review search was returned.")
    if "sql_query" in workflow_names and len(workflow_names) > 1:
        errors.append(
            "Dedicated Operations workflows cannot be mixed with the generic SQL fallback."
        )
    if agent_name == "operations":
        maximum = load_operations_workflow_config().max_workflows_per_task
        if len(workflow_names) > maximum:
            errors.append(
                f"Operations used {len(workflow_names)} workflows, exceeding the "
                f"configured maximum of {maximum}."
            )
    if (
        not successful_queries
        and not successful_review_retrievals
        and not successful_ticket_problem_retrievals
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

    return {
        "valid": not errors,
        "errors": errors,
        "warnings": warnings,
        "successful_query_count": len(successful_queries),
        "successful_review_tool_count": len(successful_review_retrievals),
        "successful_ticket_tool_count": len(successful_ticket_problem_retrievals),
        "workflow_count": len(workflow_names),
        "workflows": sorted(workflow_names),
        "evidence_count": len(source_citations),
    }


__all__ = ["validate_specialist_evidence"]
