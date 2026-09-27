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


def _column_detail(
    data_type: str,
    description: str,
    examples: tuple[object, ...] = (),
    categories: tuple[object, ...] = (),
) -> dict[str, object]:
    detail: dict[str, object] = {
        "type": data_type,
        "description": description,
        "examples": list(examples),
        "categories": list(categories) or None,
    }
    return detail


COLUMN_DETAILS: Final[dict[str, dict[str, dict[str, object]]]] = {
    "campaigns": {
        "campaign_id": _column_detail("TEXT", "Stable campaign identifier", ("camp-001",)),
        "campaign_name": _column_detail("TEXT", "Campaign display name", ("Summer Sale",)),
        "campaign_type": _column_detail(
            "TEXT",
            "Marketing campaign type",
            ("Email Marketing", "Social Media"),
            (
                "Email Marketing", "In-Store Promotion", "Influencer Marketing",
                "Online Display Ads", "Print Advertisement", "Radio Advertisement",
                "Search Engine Marketing", "SMS Marketing", "Social Media",
                "TV Advertisement", "Unknown",
            ),
        ),
        "start_date": _column_detail("DATE", "Campaign start date", ("2026-01-01",)),
        "end_date": _column_detail("DATE", "Campaign end date", ("2026-01-31",)),
        "target_segment": _column_detail(
            "TEXT",
            "Intended customer segment",
            ("New Customers",),
            (
                "Adults (26-40)", "All Customers", "East Coast",
                "High-Value Customers", "Home Improvement", "In-Store Shoppers",
                "Inactive Customers", "Kitchen Enthusiasts", "Loyal Customers",
                "Middle-aged (41-60)", "Midwest", "New Customers",
                "Online Shoppers", "Seniors (60+)", "Southern States",
                "Technology Enthusiasts", "West Coast", "Young Adults (18-25)",
            ),
        ),
        "budget": _column_detail("NUMERIC(14,2)", "Campaign budget in currency", (10000.0,)),
        "impressions": _column_detail("BIGINT", "Campaign impressions", (1000,)),
        "clicks": _column_detail("BIGINT", "Campaign clicks", (100,)),
        "conversions": _column_detail("BIGINT", "Recorded campaign conversions", (10,)),
        "conversion_rate": _column_detail("NUMERIC(8,2)", "Recorded conversion rate as a percentage", (10.0,)),
        "roi": _column_detail("NUMERIC(14,2)", "Recorded campaign return on investment percentage", (25.0,)),
    },
    "campaign_attribution": {
        "attribution_id": _column_detail("TEXT", "Stable attribution identifier", ("attr-001",)),
        "transaction_id": _column_detail("TEXT", "Attributed transaction identifier", ("txn-001",)),
        "campaign_id": _column_detail("TEXT", "Attributed campaign identifier", ("camp-001",)),
        "attribution_date": _column_detail("DATE", "Date attribution was recorded", ("2026-01-15",)),
        "attribution_method": _column_detail(
            "TEXT",
            "Method used to associate revenue with a campaign",
            ("synthetic_last_touch",),
            ("synthetic_last_touch",),
        ),
        "attributed_revenue": _column_detail("NUMERIC(16,2)", "Synthetic revenue associated with a campaign", (120.5,)),
        "is_synthetic": _column_detail("BOOLEAN", "Whether the attribution value is synthetic", (True, False), (True, False)),
    },
    "transactions": {
        "transaction_id": _column_detail("TEXT", "Stable transaction identifier", ("txn-001",)),
        "customer_id": _column_detail("TEXT", "Customer identifier for the transaction", ("cust-001",)),
        "product_id": _column_detail("TEXT", "Product identifier", ("prod-001",)),
        "product_name": _column_detail("TEXT", "Product name recorded on the transaction", ("iPad Pro",)),
        "product_category": _column_detail(
            "TEXT", "Product category recorded on the transaction", ("Tablets",),
            (
                "Audio Equipment", "Bedding", "Computer Accessories", "Cookware",
                "Desktop Computers", "Furniture", "Gaming Consoles", "Home Decor",
                "Kitchen Appliances", "Laptops", "Small Kitchen Appliances",
                "Smart Home Devices", "Smartphones", "Tablets", "TVs",
            ),
        ),
        "quantity": _column_detail("INTEGER", "Number of units sold", (1, 3)),
        "price": _column_detail("NUMERIC(14,2)", "Unit selling price in currency", (999.0,)),
        "transaction_date": _column_detail("DATE", "Date of the transaction", ("2026-01-15",)),
        "store_id": _column_detail("TEXT", "Store identifier", ("store-001",)),
        "store_location": _column_detail("TEXT", "Store or sales location", ("Singapore",)),
        "payment_method": _column_detail(
            "TEXT", "Payment method used for the transaction", ("Credit Card", "Cash"),
            ("Apple Pay", "Cash", "Credit Card", "Debit Card", "Gift Card", "Google Pay", "PayPal"),
        ),
        "discount_applied": _column_detail("NUMERIC(6,2)", "Discount percentage applied", (0.0, 10.0)),
        "gross_sales": _column_detail("NUMERIC(16,2)", "Sales amount before discount", (999.0,)),
        "discount_amount": _column_detail("NUMERIC(16,2)", "Discount amount in currency", (99.9,)),
        "net_sales": _column_detail("NUMERIC(16,2)", "Post-discount sales before refunds", (899.1,)),
    },
    "transaction_profitability": {
        "transaction_id": _column_detail("TEXT", "Transaction identifier", ("txn-001",)),
        "customer_id": _column_detail("TEXT", "Customer identifier", ("cust-001",)),
        "product_id": _column_detail("TEXT", "Product identifier", ("prod-001",)),
        "product_name": _column_detail("TEXT", "Product name", ("iPad Pro",)),
        "product_category": _column_detail(
            "TEXT", "Product category", ("Tablets",),
            (
                "Audio Equipment", "Bedding", "Computer Accessories", "Cookware",
                "Desktop Computers", "Furniture", "Gaming Consoles", "Home Decor",
                "Kitchen Appliances", "Laptops", "Small Kitchen Appliances",
                "Smart Home Devices", "Smartphones", "Tablets", "TVs",
            ),
        ),
        "quantity": _column_detail("INTEGER", "Units sold in the transaction", (1,)),
        "transaction_date": _column_detail("DATE", "Transaction date", ("2026-01-15",)),
        "store_id": _column_detail("TEXT", "Store identifier", ("store-001",)),
        "store_location": _column_detail("TEXT", "Store location", ("Singapore",)),
        "net_sales": _column_detail("NUMERIC(16,2)", "Post-discount sales before refunds", (899.1,)),
        "estimated_unit_cost": _column_detail("NUMERIC(14,2)", "Estimated product cost per unit", (700.0,)),
        "cost_method": _column_detail(
            "TEXT",
            "Method or availability status for estimated cost",
            ("product_average_ratio", "missing_product"),
            ("product_average_ratio", "missing_product"),
        ),
        "completed_refund_amount": _column_detail("NUMERIC(16,2)", "Completed refund amount for the transaction", (50.0,)),
        "recognized_revenue": _column_detail("NUMERIC(16,2)", "Net sales less completed refunds", (849.1,)),
        "cost_of_goods_sold": _column_detail("NUMERIC(16,2)", "Estimated cost for units sold", (700.0,)),
        "gross_profit": _column_detail("NUMERIC(16,2)", "Recognized revenue less estimated cost", (149.1,)),
        "gross_margin_percent": _column_detail("NUMERIC", "Estimated gross profit as a percentage of recognized revenue", (17.56,)),
    },
    "business_profit_summary": {
        "net_sales_before_refunds": _column_detail("NUMERIC", "Total net sales before refunds", (100000.0,)),
        "completed_refunds": _column_detail("NUMERIC", "Total completed refunds", (5000.0,)),
        "refund_adjusted_revenue": _column_detail("NUMERIC", "Net sales less completed refunds", (95000.0,)),
        "cost_coverage_percent": _column_detail("NUMERIC", "Share of recognized revenue with estimated cost coverage", (98.5,)),
        "cost_of_goods_sold": _column_detail("NUMERIC", "Estimated cost of goods sold", (60000.0,)),
        "estimated_gross_profit_on_costed_sales": _column_detail("NUMERIC", "Estimated gross profit for cost-covered sales", (35000.0,)),
        "operating_expenses": _column_detail("NUMERIC", "Total operating expenses", (10000.0,)),
        "campaign_spend": _column_detail("NUMERIC", "Total campaign budget", (5000.0,)),
        "estimated_operating_profit_on_costed_sales": _column_detail("NUMERIC", "Estimated gross profit less expenses and campaign spend", (20000.0,)),
    },
    "expenses": {
        "expense_id": _column_detail("TEXT", "Stable expense identifier", ("exp-001",)),
        "expense_date": _column_detail("DATE", "Date the expense is recorded", ("2026-01-15",)),
        "store_id": _column_detail("TEXT", "Store identifier", ("store-001",)),
        "expense_category": _column_detail(
            "TEXT", "Operating expense category", ("rent", "utilities"),
            ("logistics", "other", "payroll", "rent", "utilities"),
        ),
        "amount": _column_detail("NUMERIC(16,2)", "Expense amount in currency", (1200.0,)),
        "is_synthetic": _column_detail("BOOLEAN", "Whether the expense is synthetic", (True, False), (True, False)),
    },
    "returns_refunds": {
        "return_id": _column_detail("TEXT", "Stable return identifier", ("ret-001",)),
        "transaction_id": _column_detail("TEXT", "Returned transaction identifier", ("txn-001",)),
        "customer_id": _column_detail("TEXT", "Customer identifier", ("cust-001",)),
        "return_date": _column_detail("DATE", "Date the return was recorded", ("2026-01-20",)),
        "return_quantity": _column_detail("INTEGER", "Number of returned units", (1,)),
        "return_reason": _column_detail(
            "TEXT", "Reason given for the return", ("damaged", "changed_mind"),
            ("changed_mind", "damaged", "defective", "not_as_expected", "wrong_item"),
        ),
        "refund_status": _column_detail(
            "TEXT", "Refund processing status", ("pending", "completed"),
            ("completed", "pending"),
        ),
        "requested_refund_amount": _column_detail("NUMERIC(16,2)", "Refund amount requested", (100.0,)),
        "refund_amount": _column_detail("NUMERIC(16,2)", "Refund amount completed", (100.0,)),
        "is_synthetic": _column_detail("BOOLEAN", "Whether return or refund data is synthetic", (True, False), (True, False)),
    },
    "products": {
        "product_id": _column_detail("TEXT", "Stable product identifier", ("prod-001",)),
        "product_name": _column_detail("TEXT", "Canonical product name", ("iPad Pro",)),
        "product_category": _column_detail(
            "TEXT", "Product category", ("Tablets",),
            (
                "Audio Equipment", "Bedding", "Computer Accessories", "Cookware",
                "Desktop Computers", "Furniture", "Gaming Consoles", "Home Decor",
                "Kitchen Appliances", "Laptops", "Small Kitchen Appliances",
                "Smart Home Devices", "Smartphones", "Tablets", "TVs",
            ),
        ),
        "average_selling_price": _column_detail("NUMERIC(14,2)", "Average selling price in currency", (999.0,)),
        "cost_ratio": _column_detail("NUMERIC(6,4)", "Estimated unit cost as a ratio of selling price", (0.7,)),
        "unit_cost": _column_detail("NUMERIC(14,2)", "Estimated cost per unit", (700.0,)),
        "is_cost_synthetic": _column_detail("BOOLEAN", "Whether unit cost is synthetic", (True, False), (True, False)),
    },
    "stores": {
        "store_id": _column_detail("TEXT", "Stable store identifier", ("store-001",)),
        "store_location": _column_detail("TEXT", "Store or channel location", ("Singapore",)),
        "store_type": _column_detail("TEXT", "Store channel type", ("online", "physical"), ("online", "physical")),
    },
    "customers": {
        "customer_id": _column_detail("TEXT", "Stable customer identifier", ("cust-001",)),
        "full_name": _column_detail("TEXT", "Customer display name", ("Alex Tan",)),
        "age": _column_detail("INTEGER", "Customer age", (30,)),
        "gender": _column_detail(
            "TEXT", "Customer gender category", ("Female", "Male"),
            ("Female", "Male", "Non-binary", "Prefer not to say"),
        ),
        "city": _column_detail("TEXT", "Customer city", ("Singapore",)),
        "state": _column_detail("TEXT", "Customer state or region", ("Central",)),
        "registration_date": _column_detail("DATE", "Customer registration date", ("2025-01-01",)),
        "preferred_channel": _column_detail(
            "TEXT", "Customer preferred sales or service channel", ("online", "in-store"),
            ("both", "in-store", "online"),
        ),
    },
    "interactions": {
        "interaction_id": _column_detail("TEXT", "Stable interaction identifier", ("int-001",)),
        "customer_id": _column_detail("TEXT", "Customer identifier", ("cust-001",)),
        "channel": _column_detail(
            "TEXT", "Interaction channel", ("web", "mobile_app"),
            ("in_store_kiosk", "mobile_app", "web"),
        ),
        "interaction_type": _column_detail(
            "TEXT", "Interaction event type",
            ("product_view", "add_to_cart", "wishlist_add"),
            (
                "add_to_cart", "app_open", "checkout", "inventory_check",
                "notification_click", "page_view", "product_lookup", "product_view",
                "purchase", "review", "search", "session_start", "store_map_view",
                "wishlist_add",
            ),
        ),
        "interaction_date": _column_detail("DATE", "Date of the interaction", ("2026-01-15",)),
        "duration": _column_detail("NUMERIC(12,2)", "Interaction duration", (45.5,)),
        "page_or_product": _column_detail("TEXT", "Page or product involved in the interaction", ("iPad Pro",)),
        "session_id": _column_detail("TEXT", "User session identifier", ("session-001",)),
    },
    "support_tickets": {
        "ticket_id": _column_detail("TEXT", "Stable support ticket identifier", ("ticket-001",)),
        "customer_id": _column_detail("TEXT", "Customer identifier", ("cust-001",)),
        "issue_category": _column_detail(
            "TEXT", "Support issue category", ("shipping", "technical"),
            (
                "account_issue", "billing", "product_inquiry", "returns",
                "shipping", "technical", "unknown", "website_issue",
            ),
        ),
        "priority": _column_detail(
            "TEXT", "Ticket priority", ("low", "medium", "high"),
            ("low", "medium", "high", "unknown"),
        ),
        "submission_date": _column_detail("DATE", "Ticket submission date", ("2026-01-15",)),
        "resolution_date": _column_detail("DATE", "Ticket resolution date", ("2026-01-16",)),
        "resolution_status": _column_detail(
            "TEXT", "Ticket resolution status", ("pending", "escalated", "resolved"),
            ("pending", "escalated", "resolved", "closed_without_resolution", "unknown"),
        ),
        "resolution_time_hours": _column_detail("NUMERIC(12,2)", "Recorded hours from submission to resolution", (24.5,)),
        "customer_satisfaction_score": _column_detail("INTEGER", "Customer satisfaction score from 1 to 5", (4,), (1, 2, 3, 4, 5)),
        "notes": _column_detail("TEXT", "Support ticket notes", ("Delivery arrived late",)),
    },
    "customer_reviews": {
        "review_id": _column_detail("TEXT", "Stable review identifier", ("review-001",)),
        "customer_id": _column_detail("TEXT", "Customer identifier", ("cust-001",)),
        "product_name": _column_detail("TEXT", "Product name associated with the review", ("iPad Pro",)),
        "product_category": _column_detail(
            "TEXT", "Product category associated with the review", ("Tablets",),
            (
                "Audio Equipment", "Bedding", "Computer Accessories", "Cookware",
                "Desktop Computers", "Furniture", "Gaming Consoles", "Home Decor",
                "Kitchen Appliances", "Laptops", "Small Kitchen Appliances",
                "Smart Home Devices", "Smartphones", "Tablets", "TVs",
            ),
        ),
        "full_name": _column_detail("TEXT", "Reviewer display name", ("Alex Tan",)),
        "transaction_date": _column_detail("DATE", "Date of the reviewed transaction", ("2026-01-10",)),
        "review_date": _column_detail("DATE", "Date the review was submitted", ("2026-01-15",)),
        "rating": _column_detail("INTEGER", "Review rating from 1 to 5", (2, 5), (1, 2, 3, 4, 5)),
        "review_title": _column_detail("TEXT", "Review title", ("Good screen",)),
        "review_text": _column_detail("TEXT", "Review body text", ("The screen is excellent.",)),
    },
    "inventory": {
        "inventory_id": _column_detail("TEXT", "Stable inventory snapshot identifier", ("inv-001",)),
        "product_id": _column_detail("TEXT", "Product identifier", ("prod-001",)),
        "store_id": _column_detail("TEXT", "Store identifier", ("store-001",)),
        "stock_quantity": _column_detail("INTEGER", "Units in stock at the snapshot", (0, 25, 100)),
        "reorder_level": _column_detail("INTEGER", "Stock level that triggers replenishment", (20,)),
        "last_restock_date": _column_detail("DATE", "Date of the latest restock", ("2026-01-10",)),
        "snapshot_date": _column_detail("DATE", "Date represented by the inventory snapshot", ("2026-01-15",)),
        "needs_reorder": _column_detail("BOOLEAN", "Whether stock needs replenishment", (True, False), (True, False)),
        "is_synthetic": _column_detail("BOOLEAN", "Whether inventory data is synthetic", (True, False), (True, False)),
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
    {
        # Customer personally identifiable information.
        "full_name",
        "email",
        "phone",
        "street_address",
        "zip_code",
        # Internal vector data must never be exposed to the model.
        "embedding",
    }
)


__all__ = [
    "AGENT_TABLES",
    "ENTITY_FIELDS",
    "PROHIBITED_COLUMNS",
    "SCHEMA_CATALOG",
    "SqlAgentName",
]
