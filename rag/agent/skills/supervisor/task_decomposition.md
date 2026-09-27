# Skill: Supervisor Task Decomposition

## Trigger

Use this skill for every user request that needs database, review, ticket, or
knowledge-base evidence. Do not use it for greetings, conversational replies, or
questions that can be answered completely from the current conversation.

## Goal

Convert the user's request into the smallest complete list of atomic business
questions. Every subtask must have exactly one evidence owner and one primary
skill. Tool prerequisites such as resolving a product name or inspecting schema
are execution steps inside a skill, not separate subtasks.

## Procedure

1. List the distinct conclusions the final answer must contain. Split only when
   the conclusions require a different metric, evidence source, specialist, or
   business scope.
2. Preserve every explicit product phrase, period, comparison, filter, and metric
   definition from the user. Do not invent a product model, date, comparison, or
   business intent.
3. Assign each subtask to exactly one owner:
   - `operations` for operational structured data, reviews, interactions, service,
     inventory, returns by quantity/reason, customers, and sales units;
   - `finance` for monetary results, refunds by value, revenue, costs, margins,
     expenses, ROI, and profitability;
   - `supervisor` only for policy or uploaded-knowledge retrieval.
4. Assign one exact primary skill from the owner's catalog. A dedicated skill has
   priority when it fully covers that subtask. Use `sql_query` only for an atomic
   structured-data subtask not covered by a dedicated skill.
5. Dedicated skills and `sql_query` may coexist in the same agent group only for
   different subtasks. Never create two subtasks that answer the same intent by
   different routes, and never use SQL to duplicate or verify a dedicated skill's
   result.
6. Keep the list minimal. Do not split one metric into product resolution, schema
   discovery, SQL execution, and interpretation tasks. Those are internal skill
   steps.
7. Number the complete plan sequentially as `t1`, `t2`, and so on. Call
   `format_sub_task` as the only tool in that model turn.
8. After the plan is accepted, call each required specialist at most
   {{max_delegations_per_specialist}} time(s) using
   the exact task IDs in its group. Independent Operations and Finance groups
   should be dispatched together. Do not rewrite, add, or remove subtasks after
   formatting.
9. Specialists must publish backend-governed `running` and terminal status
   transitions for every subtask. These status calls report execution progress;
   they do not replace evidence collection or the final evidence packet.

## Operations skill catalog

{{operations_skill_catalog}}

## Finance skill catalog

{{finance_skill_catalog}}

## Examples

For “用户喜欢哪些商品？苹果手机的评价如何？”, create two Operations
subtasks: a generic structured ranking assigned to `sql_query`, and an Apple-phone
review subtask assigned to `product_review_retrieval`. They share one Operations
delegation but retain separate evidence routes.

For “苹果手机的购买率和利润如何？”, create an Operations subtask assigned to
`product_purchase_rate` and, when “利润” is clarified as recorded gross profit, a
Finance subtask assigned to `gross_profit_margin`. Dispatch the two agent groups
in the same turn.

## Invalid plans

- A subtask with an invented product such as “iPhone 15 Pro” when the user only
  said “苹果手机”.
- Separate subtasks for `find_real_name`, schema search, or SQL execution.
- The same review question assigned once to `product_review_retrieval` and again
  to `sql_query`.
- One broad subtask containing unrelated operational and financial conclusions.
