"""Deterministic checks applied to specialist evidence before synthesis."""

from __future__ import annotations

import re
import re
from typing import Any, Literal


SpecialistName = Literal["finance", "operations"]


def validate_specialist_evidence(
    agent_name: SpecialistName,
    answer: str,
    tool_payloads: list[dict[str, Any]],
    sources: list[dict[str, Any]],
) -> dict[str, Any]:
    """Validate that a specialist conclusion is backed by successful tools.

    This intentionally validates evidence integrity rather than trying to judge
    business truth with another language model. SQL correctness remains the
    responsibility of the governed views, SQL policy, and metric tests.
    """

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
        and payload.get("error_type")
        not in {
            None,
            "already_succeeded",
            "attempt_limit",
            "concurrent_query_blocked",
        }
    ]
    failed_review_searches = [
        payload
        for payload in tool_payloads
        if payload.get("tool") == "search_customer_reviews"
        and payload.get("success") is False
    ]

    if not answer.strip():
        errors.append("The specialist returned no final analysis.")
    if not successful_queries:
        errors.append("No successful specialist SQL evidence was returned.")

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

    uncited = sorted(citation for citation in successful_citations if citation not in answer)
    if uncited:
        errors.append("The specialist conclusion omitted its database citation.")

    review_citations = {
        citation for citation in source_citations if citation.startswith("[review:")
    }
    if review_citations and not any(citation in answer for citation in review_citations):
        errors.append("Customer-review evidence was retrieved but not cited in the conclusion.")

    answer_citations = set(re.findall(r"\[(?:db|review):[^\]\r\n]+\]", answer))
    unsupported_citations = sorted(answer_citations - source_citations)
    if unsupported_citations:
        errors.append("The specialist conclusion contains a citation with no tool evidence.")

    review_citations = {
        citation for citation in source_citations if citation.startswith("[review:")
    }
    if review_citations and not any(citation in answer for citation in review_citations):
        errors.append("Customer-review evidence was retrieved but not cited in the conclusion.")

    answer_citations = set(re.findall(r"\[(?:db|review):[^\]\r\n]+\]", answer))
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
        warnings.append("Customer-review semantic evidence was unavailable.")

    return {
        "valid": not errors,
        "errors": errors,
        "warnings": warnings,
        "successful_query_count": len(successful_queries),
        "evidence_count": len(source_citations),
    }


__all__ = ["validate_specialist_evidence"]
