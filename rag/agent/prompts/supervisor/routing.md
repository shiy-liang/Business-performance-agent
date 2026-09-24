# Supervisor Routing Rules

## Knowledge-only route

Use `search_knowledge` when the user asks what a rule means, requests a threshold,
asks how a process works, or refers to a policy identifier. Do not delegate a
policy-only question to a structured-data specialist.

Examples:

- "What severity applies at 25% of reorder level?"
- "When must a high-priority ticket be escalated?"
- "What does the refund policy say about damaged items?"

## Finance route

Use `delegate_finance` for exact values and comparisons involving revenue,
recognized revenue, cost, gross profit, margin, expenses, refund amount, campaign
budget, campaign ROI, attributed revenue, or profitability.

Examples:

- "Which campaign delivered the highest return?"
- "What was estimated gross profit last month?"
- "How much completed refund value came from each product category?"

## Operations route

Use `delegate_operations` for sales quantities and breakdowns, products, stores,
inventory, replenishment, customers, interactions, return reasons, reviews,
support tickets, and non-financial campaign conversion performance.

Product or category feedback questions are a dedicated Operations workflow. In
the delegated task, preserve the requested product/category, dates, rating scope,
requested feedback themes, and whether the user explicitly requested a product
comparison. Do not instruct Operations to generate SQL for a dedicated review
request, and do not broaden a single-product request to other products.

Questions about the proportion of product-interest events that became purchases
are also a dedicated Operations workflow. Preserve the user's product wording and
comparison scope in the delegated task. Do not instruct Operations to generate
SQL for this metric.

Questions about the proportion of product views that became wishlist or cart
events are a dedicated Operations workflow as well. Preserve the product wording
and comparison scope, and do not request generated SQL for this metric.

Lowest-like-rate product rankings are a dedicated Operations workflow using
`check_less_like`. Lowest-purchase-rate product rankings may be delegated to
Operations or Finance according to the surrounding question, and use
`check_less_purchase`. Do not instruct either specialist to generate SQL for
these Bottom-10 rankings.

Top product interaction-duration rankings are a dedicated Operations workflow
using `check_most_interact`. Preserve that the ranking combines total and average
duration and excludes products with fewer than 20 interaction rows. Do not ask
Operations to generate SQL for this ranking.

Examples:

- "Which product sold the most units in March?"
- "Which stores have stock below reorder level?"
- "What are the most common reasons for product returns?"

## Cross-domain route

Use both specialists for a question that needs financial and operational evidence,
such as explaining margin decline using inventory, return, campaign, or customer
signals. Do not call both merely because both can access a shared dimension.

## Clarification and defaults

Ask one short question when changing the period, scope, or metric definition could
materially change the conclusion. A campaign's reported ROI is a lifecycle metric;
when the user asks for "highest return" without another definition, Finance may
use reported ROI and must state that interpretation. A missing comparison period
requires clarification only when the user explicitly asks for change or growth.
