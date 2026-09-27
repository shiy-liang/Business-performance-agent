"""Customer privacy checks for identity lookup requests."""

from __future__ import annotations

import re


IDENTITY_PATTERNS = (
    r"\bwho\b",
    r"\bwhose\b",
    r"\bwhich customer\b",
    r"\bwhat customer\b",
    r"\bcustomer name\b",
    r"\bfull name\b",
    r"\bidentify the customer\b",
    r"\bcontact details\b",
)

LOOKUP_PATTERNS = (
    r"\bbought\b",
    r"\bpurchased\b",
    r"\border\b",
    r"\btransaction\b",
    r"\bcustomer who\b",
    r"\bon\s+\d{4}[-/]\d{1,2}[-/]\d{1,2}\b",
)


def check_customer_privacy(question: str) -> tuple[bool, str | None]:
    """Block attempts to identify a customer from business activity."""

    normalized = question.casefold()
    asks_for_identity = any(
        re.search(pattern, normalized) for pattern in IDENTITY_PATTERNS
    )
    asks_for_specific_customer = bool(
        re.search(r"\b(which|what) customer\b", normalized)
    )
    uses_lookup_context = any(
        re.search(pattern, normalized) for pattern in LOOKUP_PATTERNS
    )
    if asks_for_identity and (uses_lookup_context or asks_for_specific_customer):
        return (
            False,
            "I cannot identify or reveal a customer from purchase, order, or "
            "transaction details. I can provide aggregated business information instead.",
        )
    return True, None


__all__ = ["check_customer_privacy"]
