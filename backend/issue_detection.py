"""Deterministic candidate issue detection for Business Performance results."""

from __future__ import annotations


def detect_profit_deterioration(
    finance_result: dict[str, object],
) -> dict[str, object] | None:
    """Return a gross-profit month-over-month deterioration candidate, if any."""

    trend = finance_result.get("trend")
    scope = finance_result.get("scope")
    period = finance_result.get("period")
    if (
        not isinstance(trend, list)
        or len(trend) < 2
        or not isinstance(scope, dict)
        or not isinstance(period, dict)
        or period.get("is_complete") is not True
    ):
        return None

    previous = trend[-2]
    current = trend[-1]
    if not isinstance(previous, dict) or not isinstance(current, dict):
        return None

    previous_gross_profit = previous.get("estimated_gross_profit")
    current_gross_profit = current.get("estimated_gross_profit")
    transaction_count = current.get("transaction_count")
    current_month = current.get("month")
    previous_month = previous.get("month")

    if (
        not isinstance(previous_gross_profit, (int, float))
        or not isinstance(current_gross_profit, (int, float))
        or not isinstance(transaction_count, int)
        or isinstance(transaction_count, bool)
        or not isinstance(current_month, str)
        or not isinstance(previous_month, str)
    ):
        return None

    if transaction_count <= 0 or previous_gross_profit <= 0:
        return None

    change_pct = round(
        (current_gross_profit - previous_gross_profit)
        / abs(previous_gross_profit)
        * 100,
        2,
    )
    if change_pct > -10.0:
        return None

    severity = "high" if change_pct <= -20.0 else "medium"
    return {
        "rule_id": "FIN_GROSS_PROFIT_MOM_DROP",
        "issue_type": "profit_deterioration",
        "severity": severity,
        "scope": scope,
        "period": {"month": current_month},
        "title": "Gross profit deterioration",
        "evidence": {
            "metric": "estimated_gross_profit",
            "current_value": current_gross_profit,
            "baseline_value": previous_gross_profit,
            "baseline_period": previous_month,
            "change_pct": change_pct,
            "threshold_pct": -10.0,
        },
    }


def detect_refund_pressure(
    finance_result: dict[str, object],
) -> dict[str, object] | None:
    """Return a completed-refunds month-over-month pressure candidate, if any."""

    trend = finance_result.get("trend")
    scope = finance_result.get("scope")
    period = finance_result.get("period")
    if (
        not isinstance(trend, list)
        or len(trend) < 2
        or not isinstance(scope, dict)
        or scope.get("type") != "company"
        or not isinstance(period, dict)
        or period.get("is_complete") is not True
    ):
        return None

    previous = trend[-2]
    current = trend[-1]
    if not isinstance(previous, dict) or not isinstance(current, dict):
        return None

    previous_completed_refunds = previous.get("completed_refunds")
    current_completed_refunds = current.get("completed_refunds")
    current_month = current.get("month")
    previous_month = previous.get("month")
    if (
        not isinstance(previous_completed_refunds, (int, float))
        or isinstance(previous_completed_refunds, bool)
        or not isinstance(current_completed_refunds, (int, float))
        or isinstance(current_completed_refunds, bool)
        or not isinstance(current_month, str)
        or not isinstance(previous_month, str)
    ):
        return None

    if previous_completed_refunds <= 0:
        return None

    absolute_increase = round(
        current_completed_refunds - previous_completed_refunds,
        2,
    )
    change_pct = round(
        absolute_increase / previous_completed_refunds * 100,
        2,
    )
    if change_pct < 30.0 or absolute_increase < 5000.0:
        return None

    severity = (
        "high"
        if change_pct >= 50.0 and absolute_increase >= 10000.0
        else "medium"
    )
    return {
        "rule_id": "FIN_COMPLETED_REFUNDS_MOM_INCREASE",
        "issue_type": "refund_pressure",
        "severity": severity,
        "scope": scope,
        "period": {"month": current_month},
        "title": "Refund pressure",
        "evidence": {
            "metric": "completed_refunds",
            "current_value": current_completed_refunds,
            "baseline_value": previous_completed_refunds,
            "baseline_period": previous_month,
            "change_pct": change_pct,
            "absolute_increase": absolute_increase,
            "threshold_pct": 30.0,
            "threshold_absolute": 5000.0,
        },
    }


def detect_inventory_replenishment_risk(
    action_center_result: dict[str, object],
) -> dict[str, object] | None:
    """Return a latest-snapshot inventory replenishment candidate, if any."""

    if not isinstance(action_center_result, dict):
        return None

    inventory = action_center_result.get("inventory")
    if not isinstance(inventory, dict):
        return None

    scope = inventory.get("scope")
    snapshot_date = inventory.get("snapshot_date")
    total_inventory_count = inventory.get("total_inventory_count")
    critical_count = inventory.get("critical_count")
    additional_reorder_count = inventory.get("additional_reorder_count")
    affected_ratio = inventory.get("affected_ratio")
    is_synthetic = inventory.get("is_synthetic")
    representative_items = inventory.get("top_items")

    if (
        not isinstance(scope, dict)
        or not isinstance(snapshot_date, str)
        or not snapshot_date.strip()
        or not isinstance(total_inventory_count, int)
        or isinstance(total_inventory_count, bool)
        or total_inventory_count <= 0
        or not isinstance(critical_count, int)
        or isinstance(critical_count, bool)
        or critical_count < 0
        or not isinstance(additional_reorder_count, int)
        or isinstance(additional_reorder_count, bool)
        or additional_reorder_count < 0
        or not isinstance(affected_ratio, (int, float))
        or isinstance(affected_ratio, bool)
        or not isinstance(is_synthetic, bool)
        or not isinstance(representative_items, list)
    ):
        return None

    affected_inventory_count = critical_count + additional_reorder_count
    if affected_inventory_count < 5 or affected_ratio < 10.0:
        return None

    severity = (
        "high"
        if critical_count >= 3
        or (affected_ratio >= 15.0 and critical_count > 0)
        else "medium"
    )
    return {
        "rule_id": "OPS_INVENTORY_REPLENISHMENT_RISK",
        "issue_type": "inventory_replenishment_risk",
        "severity": severity,
        "scope": scope,
        "period": {"snapshot_date": snapshot_date},
        "title": "Inventory replenishment risk",
        "evidence": {
            "affected_inventory_count": affected_inventory_count,
            "total_inventory_count": total_inventory_count,
            "affected_ratio": affected_ratio,
            "critical_count": critical_count,
            "is_synthetic": is_synthetic,
            "representative_items": representative_items,
        },
    }


def detect_support_ticket_backlog(
    action_center_result: dict[str, object],
) -> dict[str, object] | None:
    """Return a high-priority unresolved support-ticket backlog candidate."""

    if not isinstance(action_center_result, dict):
        return None

    support_tickets = action_center_result.get("support_tickets")
    if not isinstance(support_tickets, dict):
        return None

    scope = support_tickets.get("scope")
    data_through = support_tickets.get("data_through")
    unresolved_count = support_tickets.get("unresolved_high_priority_count")
    oldest = support_tickets.get("oldest")
    if (
        not isinstance(scope, dict)
        or not isinstance(data_through, str)
        or not data_through.strip()
        or not isinstance(unresolved_count, int)
        or isinstance(unresolved_count, bool)
        or unresolved_count <= 0
        or not isinstance(oldest, list)
    ):
        return None

    oldest_open_days = 0
    if oldest and isinstance(oldest[0], dict):
        value = oldest[0].get("open_days")
        if isinstance(value, int) and not isinstance(value, bool):
            oldest_open_days = value

    severity = "high" if unresolved_count >= 10 or oldest_open_days >= 30 else "medium"
    return {
        "rule_id": "OPS_HIGH_PRIORITY_SUPPORT_BACKLOG",
        "issue_type": "support_ticket_backlog",
        "severity": severity,
        "scope": scope,
        "period": {"data_through": data_through},
        "title": "High-priority support backlog",
        "evidence": {
            "unresolved_high_priority_count": unresolved_count,
            "oldest_open_days": oldest_open_days,
            "data_through": data_through,
            "representative_tickets": oldest[:5],
        },
    }


def detect_campaign_inefficiency(
    marketing_result: dict[str, object],
) -> dict[str, object] | None:
    """Return a reported-lifecycle-ROI campaign candidate, if any."""

    if not isinstance(marketing_result, dict):
        return None

    scope = marketing_result.get("scope")
    period = marketing_result.get("period")
    risk_summary = marketing_result.get("risk_summary")
    if (
        not isinstance(scope, dict)
        or scope.get("type") != "company"
        or not isinstance(period, dict)
        or period.get("is_complete") is not True
        or not isinstance(risk_summary, dict)
    ):
        return None

    month = period.get("month")
    active_campaign_count = risk_summary.get("active_campaign_count")
    negative_roi_campaign_count = risk_summary.get(
        "negative_roi_campaign_count"
    )
    negative_roi_ratio = risk_summary.get("negative_roi_ratio")
    lowest_reported_roi = risk_summary.get("lowest_reported_roi")
    representative_campaigns = risk_summary.get("representative_campaigns")
    if (
        not isinstance(month, str)
        or not month.strip()
        or not isinstance(active_campaign_count, int)
        or isinstance(active_campaign_count, bool)
        or active_campaign_count < 0
        or not isinstance(negative_roi_campaign_count, int)
        or isinstance(negative_roi_campaign_count, bool)
        or negative_roi_campaign_count < 0
        or not isinstance(negative_roi_ratio, (int, float))
        or isinstance(negative_roi_ratio, bool)
        or (
            lowest_reported_roi is not None
            and (
                not isinstance(lowest_reported_roi, (int, float))
                or isinstance(lowest_reported_roi, bool)
            )
        )
        or not isinstance(representative_campaigns, list)
    ):
        return None

    if (
        active_campaign_count <= 0
        or negative_roi_campaign_count < 2
        or negative_roi_ratio < 30.0
    ):
        return None

    severity = (
        "high"
        if negative_roi_campaign_count >= 3 and negative_roi_ratio >= 40.0
        else "medium"
    )
    return {
        "rule_id": "MKT_CAMPAIGN_INEFFICIENCY",
        "issue_type": "campaign_inefficiency",
        "severity": severity,
        "scope": scope,
        "period": {"month": month},
        "title": "Campaign inefficiency",
        "evidence": {
            "metric": "reported_lifecycle_roi",
            "active_campaign_count": active_campaign_count,
            "negative_roi_campaign_count": negative_roi_campaign_count,
            "negative_roi_ratio": negative_roi_ratio,
            "lowest_reported_roi": lowest_reported_roi,
            "representative_campaigns": representative_campaigns,
        },
    }


def detect_customer_experience_deterioration(
    reviews_result: dict[str, object],
) -> dict[str, object] | None:
    """Return a company-level customer-experience candidate, if any."""

    if not isinstance(reviews_result, dict):
        return None

    scope = reviews_result.get("scope")
    period = reviews_result.get("period")
    baseline_period = reviews_result.get("baseline_period")
    current = reviews_result.get("current")
    previous = reviews_result.get("previous")
    if (
        not isinstance(scope, dict)
        or scope.get("type") != "company"
        or not isinstance(period, dict)
        or period.get("is_complete") is not True
        or not isinstance(baseline_period, dict)
        or baseline_period.get("is_complete") is not True
        or not isinstance(current, dict)
        or not isinstance(previous, dict)
    ):
        return None

    current_month = period.get("month")
    previous_month = baseline_period.get("month")
    current_review_count = current.get("review_count")
    previous_review_count = previous.get("review_count")
    current_average_rating = current.get("average_rating")
    previous_average_rating = previous.get("average_rating")
    current_low_rating_count = current.get("low_rating_count")
    current_low_rating_ratio = current.get("low_rating_ratio")
    previous_low_rating_ratio = previous.get("low_rating_ratio")
    if (
        not isinstance(current_month, str)
        or not current_month.strip()
        or not isinstance(previous_month, str)
        or not previous_month.strip()
        or not isinstance(current_review_count, int)
        or isinstance(current_review_count, bool)
        or current_review_count < 0
        or not isinstance(previous_review_count, int)
        or isinstance(previous_review_count, bool)
        or previous_review_count < 0
        or not isinstance(current_average_rating, (int, float))
        or isinstance(current_average_rating, bool)
        or not isinstance(previous_average_rating, (int, float))
        or isinstance(previous_average_rating, bool)
        or not isinstance(current_low_rating_count, int)
        or isinstance(current_low_rating_count, bool)
        or current_low_rating_count < 0
        or not isinstance(current_low_rating_ratio, (int, float))
        or isinstance(current_low_rating_ratio, bool)
        or not isinstance(previous_low_rating_ratio, (int, float))
        or isinstance(previous_low_rating_ratio, bool)
    ):
        return None

    if current_review_count < 20 or previous_review_count < 20:
        return None

    average_rating_change = round(
        current_average_rating - previous_average_rating,
        2,
    )
    low_rating_ratio_change_pp = round(
        current_low_rating_ratio - previous_low_rating_ratio,
        2,
    )
    if average_rating_change > -0.25 or low_rating_ratio_change_pp < 5.0:
        return None

    severity = (
        "high"
        if average_rating_change <= -0.50 and low_rating_ratio_change_pp >= 10.0
        else "medium"
    )
    return {
        "rule_id": "CX_CUSTOMER_EXPERIENCE_DETERIORATION",
        "issue_type": "customer_experience_deterioration",
        "severity": severity,
        "scope": scope,
        "period": {"month": current_month},
        "title": "Customer experience deterioration",
        "evidence": {
            "review_count": current_review_count,
            "previous_review_count": previous_review_count,
            "average_rating": current_average_rating,
            "previous_average_rating": previous_average_rating,
            "average_rating_change": average_rating_change,
            "low_rating_definition": "rating <= 2",
            "low_rating_count": current_low_rating_count,
            "low_rating_ratio": current_low_rating_ratio,
            "previous_low_rating_ratio": previous_low_rating_ratio,
            "low_rating_ratio_change_pp": low_rating_ratio_change_pp,
            "baseline_period": previous_month,
        },
    }


def detect_candidate_issues(
    finance_result: dict[str, object],
    action_center_result: dict[str, object],
    marketing_result: dict[str, object],
    reviews_result: dict[str, object],
) -> list[dict[str, object]]:
    """Return all deterministic candidate issues supported by current results."""

    issues = [
        detect_profit_deterioration(finance_result),
        detect_refund_pressure(finance_result),
        detect_inventory_replenishment_risk(action_center_result),
        detect_support_ticket_backlog(action_center_result),
        detect_campaign_inefficiency(marketing_result),
        detect_customer_experience_deterioration(reviews_result),
    ]
    return [issue for issue in issues if issue is not None]
