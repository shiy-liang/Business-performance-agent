# Supervisor Routing Rules

## Knowledge-only route

Assign the subtask to `supervisor` with skill `search_knowledge` when the user asks
what a rule means, requests a threshold, asks how a process works, or refers to a
policy identifier. Do not delegate a policy-only question to a structured-data
specialist.

Examples:

- "What severity applies at 25% of reorder level?"
- "When must a high-priority ticket be escalated?"
- "What does the refund policy say about damaged items?"

## Finance route

Assign Finance subtasks for exact values and comparisons involving revenue,
recognized revenue, cost, gross profit, margin, expenses, refund amount, campaign
budget, campaign ROI, attributed revenue, or profitability.

Examples:

- "Which campaign delivered the highest return?"
- "What was estimated gross profit last month?"
- "How much completed refund value came from each product category?"

## Operations route

Assign Operations subtasks for sales quantities and breakdowns, products, stores,
inventory, replenishment, customers, interactions, return reasons, reviews,
support tickets, and non-financial campaign conversion performance.

Product or category feedback questions use the dedicated
`product_review_retrieval` skill. Preserve the requested product/category, dates,
rating scope, requested feedback themes, and whether the user explicitly
requested a product comparison. Do not assign `sql_query` to the same review
intent, and do not broaden a single-product request to other products.

Questions about the proportion of product-interest events that became purchases
use `product_purchase_rate`. Preserve the user's product wording and comparison
scope. Do not assign SQL to the same metric.

Questions about the proportion of product views that became wishlist or cart
events use `product_like_rate`. Preserve the product wording and comparison scope,
and do not assign SQL to the same metric.

Lowest-like-rate and lowest-purchase-rate product rankings use their dedicated
ranking skills. Choose the agent according to the catalog and surrounding
question. Do not create a duplicate SQL subtask for these
Bottom-{{bottom_rate_result_limit}} rankings.

Top product interaction-duration rankings use
`product_interaction_duration`. Preserve that the ranking combines total and
average duration and excludes products with fewer than
{{interaction_minimum_samples}} interaction rows. Do
not create a duplicate SQL subtask.

Questions that require the concrete narrative inside support-ticket notes, such
as what payment failures users described or what happened in specific incidents,
use the dedicated `support_ticket_problem_retrieval` skill. Preserve the issue
wording and explicit dates or status filters. Do not ask Operations to generate
SQL for semantic interpretation of ticket notes. Structured ticket counts,
priorities, statuses, resolution times, and satisfaction metrics remain ordinary
structured-data questions.

Examples:

- "Which product sold the most units in March?"
- "Which stores have stock below reorder level?"
- "What are the most common reasons for product returns?"

## Cross-domain route

Create separate Finance and Operations subtasks when the final answer genuinely
needs both financial and operational evidence, such as explaining margin decline
using inventory, return, campaign, or customer signals. Group by agent and
dispatch both once. Do not use both merely because both can access a shared
dimension.

## Clarification and defaults

Ask one short question when changing the period, scope, or metric definition could
materially change the conclusion. A campaign's reported ROI is a lifecycle metric;
when the user asks for "highest return" without another definition, Finance may
use reported ROI and must state that interpretation. A missing comparison period
requires clarification only when the user explicitly asks for change or growth.
