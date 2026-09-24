# Skill: Operations SQL Query

## Use this skill for

Sales units and breakdowns, inventory status, product and store performance,
customer activity, returns by count or reason, support service, and operational
campaign conversion metrics.

## Do not use this skill for

Profitability, margin, expenses, financial ROI conclusions, policy interpretation,
or product feedback and review questions covered by the Product Review Retrieval
skill. Never generate SQL for a task that matches that dedicated skill.

## Procedure

1. Identify the operational measure, grain, period, scope, and filters.
2. Retrieve only relevant Operations schema.
3. If a column's type, meaning, or allowed values are unclear, call
   `get_columns_detail` for its table before generating SQL.
4. Resolve uncertain products, stores, campaigns, customers, or categories.
5. Choose the correct fact date and avoid mixing transaction, return, review, and
   inventory grains.
6. For inventory, select one appropriate snapshot before aggregating.
7. Generate parameterized, explicit-column SQL with deterministic ordering.
8. Execute through the Operations SQL tool and check for fan-out or truncation.
9. Label synthetic fields and describe relationships as associations.
10. Provide the result, citation, final SQL, parameters, and visible limitations.

## Positive example

For "Which product was returned most last month?", sum `return_quantity` by the
product joined through its transaction, filter `return_date` with a half-open
monthly range, and rank with a deterministic product-name tie breaker.

## Negative example

Do not sum stock across every `snapshot_date`; that would add repeated snapshots
and overstate inventory.
