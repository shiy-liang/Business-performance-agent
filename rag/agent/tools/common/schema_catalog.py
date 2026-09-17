"""Curated, agent-scoped schema metadata for text-to-SQL generation."""

from __future__ import annotations

from typing import Final, Literal


SqlAgentName = Literal["finance", "operations"]


SCHEMA_CATALOG: Final[dict[str, dict[str, object]]] = {
    "campaigns": {
        "purpose": "Campaign lifecycle, spend, reach, conversions, conversion rate, and reported ROI.",
        "columns": [
            "campaign_id", "campaign_name", "campaign_type", "start_date",
            "end_date", "target_segment", "budget", "impressions", "clicks",
            "conversions", "conversion_rate", "roi",
        ],
        "relationships": ["campaigns.campaign_id -> campaign_attribution.campaign_id"],
        "keywords": "marketing advertising return roi spend budget conversion campaign",
    },
    "campaign_attribution": {
        "purpose": "Synthetic association between a transaction and a campaign, including attributed revenue.",
        "columns": [
            "attribution_id", "transaction_id", "campaign_id", "attribution_date",
            "attribution_method", "attributed_revenue", "is_synthetic",
        ],
        "relationships": [
            "campaign_attribution.transaction_id -> transactions.transaction_id",
            "campaign_attribution.campaign_id -> campaigns.campaign_id",
        ],
        "keywords": "campaign attribution attributed revenue marketing conversion synthetic",
    },
    "transactions": {
        "purpose": "Transaction-level sales facts, quantity, price, discounts, net sales, date, product, customer, and store.",
        "columns": [
            "transaction_id", "customer_id", "product_id", "product_name",
            "product_category", "quantity", "price", "transaction_date",
            "store_id", "store_location", "payment_method", "discount_applied",
            "gross_sales", "discount_amount", "net_sales",
        ],
        "relationships": [
            "transactions.customer_id -> customers.customer_id",
            "transactions.product_id -> products.product_id",
            "transactions.store_id -> stores.store_id",
        ],
        "keywords": "sales revenue orders transaction quantity units product store channel discount payment",
    },
    "transaction_profitability": {
        "purpose": "Read-only transaction profitability view with completed refunds, recognized revenue, estimated cost, gross profit, and margin.",
        "columns": [
            "transaction_id", "customer_id", "product_id", "product_name",
            "product_category", "quantity", "transaction_date", "store_id",
            "store_location", "net_sales", "estimated_unit_cost", "cost_method",
            "completed_refund_amount", "recognized_revenue", "cost_of_goods_sold",
            "gross_profit", "gross_margin_percent",
        ],
        "relationships": [],
        "keywords": "profit profitability margin cost cogs recognized revenue refund adjusted transaction",
    },
    "business_profit_summary": {
        "purpose": "Read-only all-data summary of sales, refunds, estimated costs, operating expenses, campaign spend, and estimated operating profit.",
        "columns": [
            "net_sales_before_refunds", "completed_refunds", "refund_adjusted_revenue",
            "cost_coverage_percent", "cost_of_goods_sold",
            "estimated_gross_profit_on_costed_sales", "operating_expenses",
            "campaign_spend", "estimated_operating_profit_on_costed_sales",
        ],
        "relationships": [],
        "keywords": "business total profit margin costs expenses campaign spend refund adjusted",
    },
    "expenses": {
        "purpose": "Synthetic operating expenses by date, store, and expense category.",
        "columns": [
            "expense_id", "expense_date", "store_id", "expense_category",
            "amount", "is_synthetic",
        ],
        "relationships": ["expenses.store_id -> stores.store_id"],
        "keywords": "expense operating cost category store synthetic",
    },
    "returns_refunds": {
        "purpose": "Returns and refund requests, status, reason, quantity, requested amount, and completed refund amount.",
        "columns": [
            "return_id", "transaction_id", "customer_id", "return_date",
            "return_quantity", "return_reason", "refund_status",
            "requested_refund_amount", "refund_amount", "is_synthetic",
        ],
        "relationships": [
            "returns_refunds.transaction_id -> transactions.transaction_id",
            "returns_refunds.customer_id -> customers.customer_id",
        ],
        "keywords": "return refund reason quantity amount status customer financial impact",
    },
    "products": {
        "purpose": "Product master with product name, category, selling price, and synthetic estimated unit cost.",
        "columns": [
            "product_id", "product_name", "product_category",
            "average_selling_price", "cost_ratio", "unit_cost", "is_cost_synthetic",
        ],
        "relationships": ["products.product_id -> transactions.product_id"],
        "keywords": "product sku category price unit cost merchandise",
    },
    "stores": {
        "purpose": "Store and channel locations, including online and physical store type.",
        "columns": ["store_id", "store_location", "store_type"],
        "relationships": ["stores.store_id -> transactions.store_id"],
        "keywords": "store location channel online physical region",
    },
    "customers": {
        "purpose": "Customer identity and non-sensitive profile fields for customer-level operations analysis.",
        "columns": [
            "customer_id", "full_name", "age", "gender", "city", "state",
            "registration_date", "preferred_channel",
        ],
        "relationships": ["customers.customer_id -> transactions.customer_id"],
        "keywords": "customer buyer profile segment city state registration preference",
    },
    "interactions": {
        "purpose": "Customer interactions by channel, type, date, duration, page or product, and session.",
        "columns": [
            "interaction_id", "customer_id", "channel", "interaction_type",
            "interaction_date", "duration", "page_or_product", "session_id",
        ],
        "relationships": ["interactions.customer_id -> customers.customer_id"],
        "keywords": "customer interaction session channel page engagement behavior",
    },
    "support_tickets": {
        "purpose": "Customer support tickets, issue category, priority, resolution status, resolution time, satisfaction, and notes.",
        "columns": [
            "ticket_id", "customer_id", "issue_category", "priority",
            "submission_date", "resolution_date", "resolution_status",
            "resolution_time_hours", "customer_satisfaction_score", "notes",
        ],
        "relationships": ["support_tickets.customer_id -> customers.customer_id"],
        "keywords": "support ticket complaint issue resolution satisfaction service priority",
    },
    "customer_reviews": {
        "purpose": "Product reviews with rating, title, text, customer, product, transaction date, and review date. Embeddings are intentionally hidden from SQL generation.",
        "columns": [
            "review_id", "customer_id", "product_name", "product_category",
            "full_name", "transaction_date", "review_date", "rating",
            "review_title", "review_text",
        ],
        "relationships": ["customer_reviews.customer_id -> customers.customer_id"],
        "keywords": "review rating complaint feedback sentiment product customer text",
    },
    "inventory": {
        "purpose": "Synthetic inventory snapshots by product and store with stock, reorder level, restock date, and reorder flag.",
        "columns": [
            "inventory_id", "product_id", "store_id", "stock_quantity",
            "reorder_level", "last_restock_date", "snapshot_date",
            "needs_reorder", "is_synthetic",
        ],
        "relationships": [
            "inventory.product_id -> products.product_id",
            "inventory.store_id -> stores.store_id",
        ],
        "keywords": "inventory stock reorder replenishment snapshot restock shortage product store",
    },
}


AGENT_TABLES: Final[dict[SqlAgentName, frozenset[str]]] = {
    "finance": frozenset(
        {
            "campaigns",
            "campaign_attribution",
            "transactions",
            "transaction_profitability",
            "business_profit_summary",
            "expenses",
            "returns_refunds",
            "products",
            "stores",
        }
    ),
    "operations": frozenset(
        {
            "campaigns",
            "campaign_attribution",
            "transactions",
            "returns_refunds",
            "products",
            "stores",
            "customers",
            "interactions",
            "support_tickets",
            "customer_reviews",
            "inventory",
        }
    ),
}


ENTITY_FIELDS: Final[dict[str, tuple[str, str, frozenset[SqlAgentName]]]] = {
    "product": ("products", "product_name", frozenset({"finance", "operations"})),
    "product_category": (
        "products", "product_category", frozenset({"finance", "operations"})
    ),
    "store": ("stores", "store_location", frozenset({"finance", "operations"})),
    "campaign": (
        "campaigns", "campaign_name", frozenset({"finance", "operations"})
    ),
    "customer": ("customers", "full_name", frozenset({"operations"})),
    "support_issue": (
        "support_tickets", "issue_category", frozenset({"operations"})
    ),
    "return_reason": (
        "returns_refunds", "return_reason", frozenset({"finance", "operations"})
    ),
    "payment_method": (
        "transactions", "payment_method", frozenset({"finance", "operations"})
    ),
}


PROHIBITED_COLUMNS: Final[frozenset[str]] = frozenset(
    {"email", "phone", "street_address", "zip_code", "embedding"}
)


__all__ = [
    "AGENT_TABLES",
    "ENTITY_FIELDS",
    "PROHIBITED_COLUMNS",
    "SCHEMA_CATALOG",
    "SqlAgentName",
]
